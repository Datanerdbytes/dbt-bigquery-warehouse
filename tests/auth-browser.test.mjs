import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
const source = readFileSync("my-dash-app/auth_frontend/main.js", "utf8")
  .replace(
    /import \{ getSupabaseClient \} from [^;]+;/,
    "const getSupabaseClient=async()=>window.mockClient;",
  )
  .replaceAll("location.replace(", "window.navigate(");
const tick = () => new Promise((resolve) => setTimeout(resolve, 25));
async function fixture(
  mode = "login",
  session = null,
  status = 200,
  query = "",
) {
  const dom = new JSDOM(
    `<html ${mode ? `data-auth-page="${mode}"` : ""}><body><div id="auth-loading"></div><section id="auth-content" hidden><button data-provider="google"></button><button data-provider="github"></button><form id="auth-form"><input id="auth-email" type="email" required><span id="auth-email-error"></span><input id="auth-password" type="password" required><span id="auth-password-error"></span><button id="auth-show-password" type="button"></button></form></section><div id="auth-message" hidden tabindex="-1"></div><button id="auth-signout" hidden></button><a id="auth-back" hidden></a><div id="auth-session-loading"></div></body></html>`,
    {
      url: `https://analytics.example.com/${mode || "dashboard"}${query}`,
      runScripts: "outside-only",
    },
  );
  const w = dom.window,
    calls = [];
  let listener;
  w.Request = Request;
  w.AbortSignal = AbortSignal;
  w.navigate = (url) => calls.push(["navigate", url]);
  w.fetch = async (url, options) => {
    calls.push([url, options]);
    return {
      ok: status === 200,
      status,
      json: async () => ({
        error: status === 403 ? "approval_required" : "auth_unavailable",
      }),
    };
  };
  const auth = {
    getSession: async () => ({ data: { session } }),
    onAuthStateChange: (fn) => {
      listener = fn;
    },
    signInWithPassword: async () => ({
      data: { session: { access_token: "valid" } },
    }),
    signUp: async () => ({ data: { session: null } }),
    signInWithOAuth: async (options) => {
      calls.push(["oauth", options]);
      return { error: new Error("Provider unavailable") };
    },
    exchangeCodeForSession: async (code) => {
      calls.push(["exchange", code]);
      return { data: { session: { access_token: "valid" } } };
    },
    signOut: async () => ({}),
  };
  w.mockClient = { auth };
  w.eval(source);
  await tick();
  return {
    w,
    calls,
    auth,
    event: (...args) => listener(...args),
    close: () => w.close(),
  };
}
function submit(w) {
  w.document.getElementById("auth-email").value = "analyst@example.com";
  w.document.getElementById("auth-password").value = "long-password";
  w.document
    .getElementById("auth-form")
    .dispatchEvent(new w.Event("submit", { cancelable: true }));
}
test("anonymous login starts and shows field errors", async () => {
  const f = await fixture();
  assert.equal(f.w.document.getElementById("auth-content").hidden, false);
  f.w.document
    .getElementById("auth-form")
    .dispatchEvent(new f.w.Event("submit", { cancelable: true }));
  assert.equal(f.w.document.activeElement.id, "auth-message");
  assert.equal(f.w.document.querySelectorAll("#auth-message a").length, 2);
  f.close();
});
test("confirmed email login reaches dashboard", async () => {
  const f = await fixture();
  submit(f.w);
  await tick();
  assert.ok(
    f.calls.some(([name, url]) => name === "navigate" && url === "/dashboard"),
  );
  f.close();
});
test("signup asks for confirmation", async () => {
  const f = await fixture("signup");
  submit(f.w);
  await tick();
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /Check your email/,
  );
  f.close();
});
test("both OAuth providers use callback", async () => {
  const f = await fixture();
  for (const provider of ["google", "github"]) {
    f.w.document.querySelector(`[data-provider="${provider}"]`).click();
    await tick();
    assert.ok(
      f.calls.some(
        ([name, o]) =>
          name === "oauth" &&
          o.provider === provider &&
          o.options.redirectTo.endsWith("/auth/callback"),
      ),
    );
  }
  f.close();
});
test("unapproved user never sees dashboard", async () => {
  const f = await fixture("login", { access_token: "valid" }, 403);
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /administrator/,
  );
  assert.equal(f.w.document.getElementById("auth-signout").hidden, false);
  f.close();
});
test("dashboard gate releases requests and refreshes session", async () => {
  const f = await fixture("", { access_token: "initial" });
  assert.equal(f.w.document.documentElement.dataset.authReady, "true");
  await f.w.fetch("/_dash-layout");
  f.event("TOKEN_REFRESHED", { access_token: "refreshed" });
  await tick();
  assert.ok(f.calls.some(([, o]) => o?.body?.includes("refreshed")));
  f.event("SIGNED_OUT", null);
  await tick();
  assert.equal(f.w.document.documentElement.dataset.authReady, undefined);
  assert.ok(
    f.calls.some(([name, url]) => name === "navigate" && url === "/login"),
  );
  f.close();
});
test("service outage cannot deadlock Dash requests", async () => {
  const f = await fixture("", { access_token: "valid" }, 503);
  await assert.rejects(f.w.fetch("/_dash-layout"), /Authentication required/);
  assert.equal(f.w.document.documentElement.dataset.authReady, undefined);
  f.close();
});
test("callback exchanges once and clears URL code", async () => {
  const f = await fixture("callback", null, 200, "?code=test-code");
  assert.equal(f.calls.filter(([name]) => name === "exchange").length, 1);
  assert.equal(f.w.location.search, "");
  assert.ok(
    f.calls.some(([name, url]) => name === "navigate" && url === "/dashboard"),
  );
  f.close();
});
test("canceled confirmation link gives sign-in recovery", async () => {
  const f = await fixture("callback", null, 200, "?error=access_denied");
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /already confirmed/,
  );
  assert.equal(f.w.document.getElementById("auth-back").hidden, false);
  f.close();
});
