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
  showcase = false,
  reducedMotion = false,
) {
  const dom = new JSDOM(
    showcase
      ? readFileSync("my-dash-app/templates/auth.html", "utf8").replace(
          "</body>",
          readFileSync("my-dash-app/templates/showcase.html", "utf8") +
            "</body>",
        )
      : `<html ${mode ? `data-auth-page="${mode}"` : ""}><body><div id="auth-loading"></div><section id="auth-content" hidden><button data-provider="google"></button><button data-provider="github"></button><form id="auth-form"><input id="auth-email" type="email" required><span id="auth-email-error"></span><input id="auth-password" type="password" required><span id="auth-password-error"></span><button id="auth-show-password" type="button"></button></form></section><div id="auth-message" hidden tabindex="-1"></div><button id="auth-signout" hidden></button><a id="auth-back" hidden></a><div id="auth-session-loading"></div></body></html>`,
    {
      url: `https://analytics.example.com/${mode || "dashboard"}${query}`,
      runScripts: "outside-only",
    },
  );
  const w = dom.window,
    calls = [];
  let listener;
  if (showcase) w.document.documentElement.dataset.authPage = mode;
  let advanceSlide;
  let motionChanged;
  const motion = {
    matches: reducedMotion,
    addEventListener: (_name, fn) => {
      motionChanged = fn;
    },
  };
  w.matchMedia = () => motion;
  if (showcase) {
    Object.defineProperty(w.document, "hidden", {
      value: false,
      configurable: true,
    });
    w.setInterval = (fn) => {
      advanceSlide = fn;
      return 1;
    };
    w.clearInterval = () => {
      advanceSlide = null;
    };
  }
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
  if (showcase)
    w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  w.eval(source);
  await tick();
  return {
    w,
    calls,
    auth,
    event: (...args) => listener(...args),
    advanceSlide: () => advanceSlide?.(),
    setReducedMotion: () => {
      motion.matches = true;
      motionChanged?.();
    },
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

test("showcase starts with analytics, rotates, and manual navigation pauses", async () => {
  const f = await fixture("login", null, 200, "", true);
  const analytics = f.w.document.getElementById("auth-slide-analytics");
  const lineage = f.w.document.getElementById("auth-slide-lineage");
  assert.equal(analytics.hidden, false);
  assert.equal(lineage.hidden, true);
  f.advanceSlide();
  assert.equal(lineage.hidden, false);
  assert.equal(analytics.getAttribute("aria-hidden"), "true");
  f.w.document.querySelector('[data-carousel="next"]').click();
  assert.equal(analytics.hidden, false);
  f.advanceSlide();
  assert.equal(analytics.hidden, false);
  f.w.document.querySelector('[data-carousel="previous"]').click();
  assert.equal(lineage.hidden, false);
  f.w.document.querySelector('[data-slide="0"]').click();
  assert.equal(analytics.hidden, false);
  assert.equal(
    f.w.document.querySelector('[data-slide="0"]').getAttribute("aria-current"),
    "true",
  );
  f.close();
});
test("showcase pauses while signing in and honors reduced motion changes", async () => {
  const f = await fixture("login", null, 200, "", true);
  const analytics = f.w.document.getElementById("auth-slide-analytics");
  f.w.document.getElementById("auth-email").focus();
  f.advanceSlide();
  assert.equal(analytics.hidden, false);
  f.w.document.querySelector('[data-carousel="rotation"]').click();
  f.advanceSlide();
  assert.equal(analytics.hidden, true);
  f.setReducedMotion();
  f.advanceSlide();
  assert.equal(analytics.hidden, true);
  assert.equal(
    f.w.document.querySelector('[data-carousel="rotation"]').hidden,
    true,
  );
  f.close();
});
test("reduced motion keeps the first slide still and manual controls available", async () => {
  const f = await fixture("signup", null, 200, "", true, true);
  f.advanceSlide();
  assert.equal(
    f.w.document.getElementById("auth-slide-analytics").hidden,
    false,
  );
  f.w.document.querySelector('[data-slide="1"]').click();
  assert.equal(f.w.document.getElementById("auth-slide-lineage").hidden, false);
  f.close();
});

test("showcase stops on pointer interaction and when the page is hidden", async () => {
  const f = await fixture("login", null, 200, "", true);
  const analytics = f.w.document.getElementById("auth-slide-analytics");
  f.w.document
    .getElementById("auth-showcase")
    .dispatchEvent(new f.w.Event("pointerenter"));
  f.advanceSlide();
  assert.equal(analytics.hidden, false);
  f.w.document.querySelector('[data-carousel="rotation"]').click();
  Object.defineProperty(f.w.document, "hidden", {
    value: true,
    configurable: true,
  });
  f.w.document.dispatchEvent(new f.w.Event("visibilitychange"));
  f.advanceSlide();
  assert.equal(analytics.hidden, false);
  f.close();
});

test("public landing slideshow works without authentication and preserves focus", () => {
  const html = readFileSync(
    "my-dash-app/templates/landing.html",
    "utf8",
  ).replace(
    /\{% include 'showcase.html' %\}/,
    readFileSync("my-dash-app/templates/showcase.html", "utf8"),
  );
  const dom = new JSDOM(html, {
    url: "https://analytics.example.com/",
    runScripts: "outside-only",
  });
  const w = dom.window;
  w.matchMedia = () => ({ matches: true, addEventListener() {} });
  w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  assert.equal(w.document.getElementById("auth-form"), null);
  assert.equal(
    w.document.querySelector(".landing-login").getAttribute("href"),
    "/login",
  );
  const action = w.document.querySelector(
    "#auth-slide-analytics .landing-hero-actions button",
  );
  action.focus();
  action.click();
  assert.equal(w.document.getElementById("auth-slide-lineage").hidden, false);
  assert.equal(
    w.document.activeElement,
    w.document.querySelector('.auth-carousel-tabs [data-slide="1"]'),
  );
  w.document.querySelector('.landing-nav [data-slide="0"]').click();
  assert.equal(w.document.getElementById("auth-slide-analytics").hidden, false);
  dom.window.close();
});

test("throttled login page explains retry without starting auth requests", async () => {
  const { w, calls } = await fixture("rate_limited");
  assert.match(
    w.document.getElementById("auth-message").textContent,
    /Too many authentication requests/,
  );
  assert.equal(calls.length, 0);
  assert.equal(w.document.getElementById("auth-content").hidden, true);
  w.close();
});
