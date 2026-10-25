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
function stubVideos(window) {
  for (const video of window.document.querySelectorAll("video")) {
    Object.defineProperties(video, {
      paused: { configurable: true, writable: true, value: true },
      readyState: { configurable: true, value: 1 },
      currentTime: { configurable: true, writable: true, value: 0 },
    });
    video.pause = () => {
      video.paused = true;
    };
    video.play = () => {
      video.paused = false;
      return Promise.resolve();
    };
  }
}
async function fixture(
  mode = "login",
  session = null,
  status = 200,
  query = "",
  showcase = false,
  reducedMotion = false,
  authOverrides = {},
) {
  const dom = new JSDOM(
    showcase
      ? readFileSync("my-dash-app/templates/auth.html", "utf8").replace(
          "</body>",
          readFileSync("my-dash-app/templates/showcase.html", "utf8") +
            "</body>",
        )
      : `<html ${mode ? `data-auth-page="${mode}"` : ""}><body><div id="auth-loading"></div><section id="auth-content" hidden><button data-provider="google"></button><button data-provider="github"></button><form id="auth-form"><input id="auth-email" type="email" required><span id="auth-email-error"></span><input id="auth-password" type="password" required><span id="auth-password-error"></span><input id="auth-confirm-password" type="password"><span id="auth-confirm-password-error"></span><button id="auth-show-password" type="button"></button></form></section><div id="auth-message" hidden tabindex="-1"></div><button id="auth-signout" hidden></button><a id="auth-back" hidden></a><div id="auth-session-loading"></div></body></html>`,
    {
      url: `https://analytics.example.com/${mode || "dashboard"}${query}`,
      runScripts: "outside-only",
    },
  );
  const w = dom.window,
    calls = [];
  let listener;
  let currentSession = session;
  let responseStatus = status;
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
      ok: responseStatus === 200,
      status: responseStatus,
      json: async () =>
        url === "/auth/password"
          ? {
              access_token: "gateway-access",
              refresh_token: "gateway-refresh",
              error:
                responseStatus === 423
                  ? "account_locked"
                  : "invalid_credentials",
              retry_after: 900,
            }
          : {
              error:
                responseStatus === 403
                  ? "email_confirmation_required"
                  : "auth_unavailable",
            },
    };
  };
  const auth = {
    getSession: async () => ({ data: { session: currentSession } }),
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
      currentSession = { access_token: "valid", user: { id: "recovery-user" } };
      return {
        data: {
          session: currentSession,
          redirectType: mode === "reset" ? "PASSWORD_RECOVERY" : null,
        },
      };
    },
    resetPasswordForEmail: async (email, options) => {
      calls.push(["reset-email", email, options]);
      return {};
    },
    updateUser: async (attributes) => {
      calls.push(["update-password", attributes]);
      return {};
    },
    setSession: async (tokens) => {
      calls.push(["setSession", tokens]);
      return { data: { session: { access_token: "valid" } } };
    },
    signOut: async () => ({}),
  };
  Object.assign(auth, authOverrides);
  w.mockClient = { auth };
  if (showcase) {
    stubVideos(w);
    w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  }
  w.eval(source);
  await tick();
  return {
    w,
    calls,
    auth,
    event: (...args) => listener(...args),
    setStatus: (value) => {
      responseStatus = value;
    },
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
test("unconfirmed user never sees dashboard", async () => {
  const f = await fixture("login", { access_token: "valid" }, 403);
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /Confirm your email/,
  );
  assert.equal(f.w.document.getElementById("auth-signout").hidden, false);
  f.close();
});
test("dashboard gate releases requests and refreshes session", async () => {
  const f = await fixture("", { access_token: "initial" });
  assert.equal(f.w.document.documentElement.dataset.authReady, "true");
  await f.w.fetch("/_dash-layout");
  f.event("TOKEN_REFRESHED", {
    access_token: "refreshed",
    user: { id: "recovery-user" },
  });
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
  stubVideos(w);
  w.matchMedia = () => ({ matches: true, addEventListener() {} });
  w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  assert.ok([...w.document.querySelectorAll("video")].every((v) => v.paused));
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

test("landing preserves timing with playback control and pauses on hover or focus", async () => {
  const showcase = readFileSync(
    "my-dash-app/templates/showcase.html",
    "utf8",
  ).replace(/\{% if not landing_showcase %\}[\s\S]*?\{% endif %\}/, "");
  const dom = new JSDOM(
    `<body class="landing-page"><button id="test-nav" data-slide="1">Data pipeline</button>${showcase}</body>`,
    {
      runScripts: "outside-only",
    },
  );
  const w = dom.window;
  stubVideos(w);
  Object.defineProperty(w.document, "hidden", {
    value: false,
    configurable: true,
  });
  let advance, delay, motionChanged;
  const motion = {
    matches: false,
    addEventListener: (_event, callback) => {
      motionChanged = callback;
    },
  };
  w.matchMedia = () => motion;
  w.setInterval = (callback, milliseconds) => {
    advance = callback;
    delay = milliseconds;
    return 1;
  };
  w.clearInterval = () => {
    advance = null;
  };
  w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  const panel = w.document.querySelector(".auth-preview");
  const analytics = w.document.getElementById("auth-slide-analytics");
  assert.ok(w.document.querySelector('[data-carousel="rotation"]'));
  assert.equal(delay, 8000);
  const rotation = w.document.querySelector('[data-carousel="rotation"]');
  rotation.click();
  assert.equal(advance, null);
  panel.dispatchEvent(new w.Event("pointerleave"));
  w.dispatchEvent(new w.Event("pageshow"));
  assert.equal(
    advance,
    null,
    "explicit pause survives automatic resume events",
  );
  rotation.click();
  assert.equal(delay, 8000);

  const overviewVideo = w.document.querySelector(
    "#auth-slide-analytics video",
  );
  const lineageVideo = w.document.querySelector("#auth-slide-lineage video");
  assert.equal(overviewVideo.paused, false);
  assert.equal(lineageVideo.paused, true);

  advance();
  assert.equal(analytics.hidden, true);
  assert.equal(overviewVideo.paused, true);
  assert.equal(lineageVideo.paused, false);
  assert.equal(lineageVideo.currentTime, 0);
  panel.dispatchEvent(new w.Event("pointerenter"));
  assert.equal(advance, null);
  panel.dispatchEvent(new w.Event("pointerleave"));
  advance();
  assert.equal(analytics.hidden, false);
  const tab = w.document.querySelector('[data-slide="0"]');
  tab.focus();
  assert.equal(advance, null);
  panel.dispatchEvent(new w.Event("pointerenter"));
  panel.dispatchEvent(new w.Event("pointerleave"));
  assert.equal(advance, null);
  rotation.focus();
  await tick();
  assert.equal(advance, null, "focusing Play must not start rotation");
  rotation.click();
  assert.equal(
    typeof advance,
    "function",
    "activating Play may resume while focused",
  );
  rotation.blur();
  await tick();
  assert.equal(typeof advance, "function");
  motion.matches = true;
  motionChanged();
  panel.dispatchEvent(new w.Event("pointerleave"));
  assert.equal(advance, null);
  motion.matches = false;
  motionChanged();
  assert.equal(typeof advance, "function");
  Object.defineProperty(w.document, "hidden", {
    value: true,
    configurable: true,
  });
  w.document.dispatchEvent(new w.Event("visibilitychange"));
  assert.equal(advance, null);
  Object.defineProperty(w.document, "hidden", {
    value: false,
    configurable: true,
  });
  w.document.dispatchEvent(new w.Event("visibilitychange"));
  assert.equal(typeof advance, "function");
  w.dispatchEvent(new w.Event("pagehide"));
  assert.equal(advance, null);
  w.dispatchEvent(new w.Event("pageshow"));
  assert.equal(typeof advance, "function");
  const outside = w.document.createElement("button");
  w.document.body.append(outside);
  outside.focus();
  assert.equal(typeof advance, "function");
  // Existing slide selectors outside the showcase must resume autoplay.
  outside.click();
  w.document.getElementById("test-nav").click();
  assert.equal(typeof advance, "function");
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

test("repeated session events share one synchronization and refresh still works", async () => {
  const f = await fixture("", { access_token: "initial" });
  for (let i = 0; i < 15; i++)
    f.event("SIGNED_IN", { access_token: "initial" });
  await tick();
  assert.equal(
    f.calls.filter(([url, o]) => url === "/auth/session" && o.method === "POST")
      .length,
    1,
  );
  f.event("TOKEN_REFRESHED", { access_token: "new-token" });
  f.event("SIGNED_IN", { access_token: "new-token" });
  await tick();
  assert.equal(
    f.calls.filter(([url, o]) => url === "/auth/session" && o.method === "POST")
      .length,
    2,
  );
  await f.w.fetch("/_dash-layout");
  f.close();
});

test("sign-in event and form result do not duplicate the session POST", async () => {
  const f = await fixture();
  f.auth.signInWithPassword = async () => {
    const session = { access_token: "valid" };
    f.event("SIGNED_IN", session);
    return { data: { session } };
  };
  submit(f.w);
  await tick();
  assert.equal(
    f.calls.filter(([url, o]) => url === "/auth/session" && o.method === "POST")
      .length,
    1,
  );
  f.close();
});

test("rejected session events do not replay mutations; explicit sign-in can retry", async () => {
  const f = await fixture();
  f.setStatus(503);
  submit(f.w);
  await tick();
  for (let i = 0; i < 12; i++) f.event("SIGNED_IN", { access_token: "valid" });
  await tick();
  assert.equal(
    f.calls.filter(([url, o]) => url === "/auth/session" && o.method === "POST")
      .length,
    1,
  );
  submit(f.w);
  await tick();
  assert.equal(
    f.calls.filter(([url, o]) => url === "/auth/session" && o.method === "POST")
      .length,
    2,
  );
  assert.equal(f.w.document.documentElement.dataset.authReady, undefined);
  f.close();
});

test("signup password toggle preserves value and supports both states", async () => {
  const f = await fixture("signup");
  const input = f.w.document.getElementById("auth-password");
  const button = f.w.document.getElementById("auth-show-password");
  input.value = "synthetic-password";
  button.click();
  assert.equal(input.type, "text");
  assert.equal(button.getAttribute("aria-pressed"), "true");
  button.click();
  assert.equal(input.type, "password");
  assert.equal(input.value, "synthetic-password");
  assert.equal(button.getAttribute("aria-label"), "Show password");
  assert.equal(
    f.calls.some(([name]) => name === "navigate"),
    false,
  );
  f.close();
});
test("bare callback gives neutral recovery rather than claiming invalid confirmation", async () => {
  const f = await fixture("callback");
  const message = f.w.document.getElementById("auth-message");
  assert.match(message.textContent, /no active sign-in link/);
  assert.equal(message.dataset.tone, "info");
  assert.equal(
    f.calls.some(([name]) => name === "exchange" || name === "navigate"),
    false,
  );
  f.close();
});
test("refreshed callback resumes an existing session", async () => {
  const f = await fixture("callback", { access_token: "valid" });
  assert.ok(
    f.calls.some(([name, url]) => name === "navigate" && url === "/dashboard"),
  );
  f.close();
});
test("fragment tokens are removed and rejected without importing a session", async () => {
  const f = await fixture(
    "callback",
    null,
    200,
    "#access_token=synthetic-access&refresh_token=synthetic-refresh&type=signup",
  );
  assert.equal(f.w.location.hash, "");
  assert.equal(f.calls.filter(([name]) => name === "setSession").length, 0);
  assert.equal(
    f.calls.some(([name]) => ["navigate", "/auth/session"].includes(name)),
    false,
  );
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /unsupported sign-in format/,
  );
  f.close();
});
test("expired fragment confirmation errors never establish a session", async () => {
  const f = await fixture(
    "callback",
    null,
    200,
    "#error=access_denied&error_code=otp_expired&error_description=untrusted",
  );
  assert.equal(f.w.location.hash, "");
  assert.match(
    f.w.document.getElementById("auth-message").textContent,
    /expired or has already been used/,
  );
  assert.equal(
    f.calls.some(([name]) => name === "setSession" || name === "navigate"),
    false,
  );
  f.close();
});

test("password reset request sends a generic confirmation and no login cookie", async () => {
  const f = await fixture("forgot");
  try {
    submit(f.w);
    await tick();
    assert.deepEqual(
      JSON.parse(
        JSON.stringify(
          f.calls.find(([name]) => name === "reset-email").slice(1),
        ),
      ),
      [
        "analyst@example.com",
        { redirectTo: "https://analytics.example.com/reset-password" },
      ],
    );
    assert.match(
      f.w.document.getElementById("auth-message").textContent,
      /If an account exists/,
    );
    assert.equal(
      f.calls.some(([url]) => url === "/auth/session"),
      false,
    );
  } finally {
    f.close();
  }
});

test("recovery PKCE exchange stays on the form, validates confirmation, and updates password", async () => {
  const f = await fixture("reset", null, 200, "?code=recovery-code");
  try {
    assert.equal(f.w.location.search, "");
    assert.equal(f.w.document.getElementById("auth-content").hidden, false);
    assert.equal(
      f.calls.some(([name]) => name === "navigate"),
      false,
    );
    submit(f.w);
    await tick();
    assert.equal(
      f.calls.some(([name]) => name === "update-password"),
      false,
    );
    f.w.document.getElementById("auth-confirm-password").value =
      "long-password";
    submit(f.w);
    await tick();
    assert.equal(
      f.calls.filter(([name]) => name === "update-password").length,
      1,
    );
    assert.match(
      f.w.document.getElementById("auth-message").textContent,
      /Password updated/,
    );
    assert.equal(
      f.calls.some(
        ([url, options]) =>
          url === "/auth/session" && options.method === "POST",
      ),
      false,
    );
    assert.equal(
      f.w.document.getElementById("auth-back").getAttribute("href"),
      "/login",
    );
  } finally {
    f.close();
  }
});

test("reset rejects missing codes and fragment tokens without using a cached session", async () => {
  for (const query of [
    "",
    "#access_token=untrusted&refresh_token=untrusted",
    "?error=access_denied",
  ]) {
    const f = await fixture("reset", { access_token: "cached" }, 200, query);
    try {
      assert.equal(f.w.document.getElementById("auth-content").hidden, true);
      assert.match(
        f.w.document.getElementById("auth-message").textContent,
        /Request a new link/,
      );
      assert.equal(
        f.calls.some(([name]) =>
          ["setSession", "exchange", "/auth/session", "navigate"].includes(
            name,
          ),
        ),
        false,
      );
    } finally {
      f.close();
    }
  }
});

test("recovery auth events do not bypass the password form", async () => {
  const f = await fixture("reset", null, 200, "?code=recovery-code");
  try {
    f.event("SIGNED_IN", {
      access_token: "recovery",
      user: { id: "recovery-user" },
    });
    f.event("TOKEN_REFRESHED", { access_token: "refreshed" });
    await tick();
    assert.equal(
      f.calls.some(([name]) => ["/auth/session", "navigate"].includes(name)),
      false,
    );
  } finally {
    f.close();
  }
});

test("expired and non-recovery PKCE codes cannot open the reset form", async () => {
  for (const result of [
    { data: { session: null }, error: new Error("Expired") },
    { data: { session: { access_token: "ordinary" }, redirectType: null } },
  ]) {
    const f = await fixture("reset", null, 200, "?code=test", false, false, {
      exchangeCodeForSession: async () => result,
    });
    try {
      assert.equal(f.w.document.getElementById("auth-content").hidden, true);
      assert.match(
        f.w.document.getElementById("auth-message").textContent,
        /Unable to verify/,
      );
      assert.equal(
        f.calls.some(([name]) => name === "/auth/session"),
        false,
      );
    } finally {
      f.close();
    }
  }
});

test("recovery provider errors allow deliberate retry without success claims", async () => {
  const f = await fixture("forgot");
  try {
    f.auth.resetPasswordForEmail = async () => ({
      error: new Error("Email rate limit exceeded"),
    });
    submit(f.w);
    await tick();
    assert.match(
      f.w.document.getElementById("auth-message").textContent,
      /rate limit/,
    );
    assert.equal(f.w.document.getElementById("auth-email").disabled, false);
  } finally {
    f.close();
  }
  const r = await fixture("reset", null, 200, "?code=test");
  try {
    r.auth.updateUser = async () => ({
      error: new Error("Password does not meet policy"),
    });
    r.w.document.getElementById("auth-confirm-password").value =
      "long-password";
    submit(r.w);
    await tick();
    assert.match(
      r.w.document.getElementById("auth-message").textContent,
      /policy/,
    );
    assert.equal(r.w.document.getElementById("auth-content").hidden, false);
    assert.equal(r.w.document.getElementById("auth-password").disabled, false);
    assert.equal(
      r.calls.some(([name]) => name === "/auth/session"),
      false,
    );
  } finally {
    r.close();
  }
});

test("lockout-enabled sign-in uses the server gateway before session synchronization", async () => {
  const f = await fixture("login");
  try {
    f.w.mockClient.qePasswordLockoutEnabled = true;
    f.auth.signInWithPassword = async () => {
      throw new Error("Browser password sign-in must not run");
    };
    submit(f.w);
    await tick();
    assert.equal(
      f.calls.filter(([name]) => name === "/auth/password").length,
      1,
    );
    assert.equal(
      f.calls.find(([name]) => name === "setSession")[1].access_token,
      "gateway-access",
    );
    assert.ok(f.calls.some(([name]) => name === "/auth/session"));
  } finally {
    f.close();
  }
});

test("locked password attempts keep recovery available and never establish a session", async () => {
  const f = await fixture("login");
  try {
    f.w.mockClient.qePasswordLockoutEnabled = true;
    f.setStatus(423);
    submit(f.w);
    await tick();
    assert.match(
      f.w.document.getElementById("auth-message").textContent,
      /15 minute.*reset your password/,
    );
    assert.equal(
      f.calls.some(([name]) => ["setSession", "navigate"].includes(name)),
      false,
    );
    assert.equal(
      f.calls.filter(([name]) => name === "/auth/session").length,
      1,
    ); // Initial anonymous DELETE only.
    assert.equal(f.w.document.getElementById("auth-password").disabled, false);
  } finally {
    f.close();
  }
});

test("recovery account changes and sign-out invalidate the password form", async () => {
  for (const [event, session] of [
    ["SIGNED_IN", { user: { id: "other-user" }, access_token: "other" }],
    ["SIGNED_OUT", null],
  ]) {
    const f = await fixture("reset", null, 200, "?code=recovery-code");
    try {
      f.event(event, session);
      f.w.document.getElementById("auth-confirm-password").value =
        "long-password";
      submit(f.w);
      await tick();
      assert.equal(f.w.document.getElementById("auth-content").hidden, true);
      assert.equal(
        f.calls.some(([name]) => name === "update-password"),
        false,
      );
    } finally {
      f.close();
    }
  }
});

test("recovery rechecks identity immediately before changing a password", async () => {
  const f = await fixture("reset", null, 200, "?code=recovery-code");
  try {
    f.auth.getSession = async () => ({
      data: { session: { user: { id: "other-user" }, access_token: "other" } },
    });
    f.w.document.getElementById("auth-confirm-password").value =
      "long-password";
    submit(f.w);
    await tick();
    assert.equal(
      f.calls.some(([name]) => name === "update-password"),
      false,
    );
    assert.equal(f.w.document.getElementById("auth-content").hidden, true);
  } finally {
    f.close();
  }
});
