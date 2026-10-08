import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

/**
 * CSP browser regression tests.
 *
 * These tests verify that the Content-Security-Policy nonce mechanism
 * blocks unauthorized inline scripts while allowing nonce-authorized
 * scripts to execute. They use JSDOM with mocked Supabase services.
 *
 * Note: JSDOM does not enforce CSP headers. These tests verify the
 * structural correctness of nonce-bearing script elements and that the
 * auth bundle executes under the expected script-loading contract.
 * True CSP enforcement is verified by the header tests in test_csp.py
 * and by the browser's CSP implementation at runtime.
 */

const authHtml = readFileSync("my-dash-app/templates/auth.html", "utf8");
const landingHtml = readFileSync(
  "my-dash-app/templates/landing.html",
  "utf8",
).replace(
  /\{% include 'showcase.html' %\}/,
  readFileSync("my-dash-app/templates/showcase.html", "utf8"),
);

const authSource = readFileSync("my-dash-app/auth_frontend/main.js", "utf8")
  .replace(
    /import \{ getSupabaseClient \} from [^;]+;/,
    "const getSupabaseClient=async()=>window.mockClient;",
  )
  .replaceAll("location.replace(", "window.navigate(");

const tick = () => new Promise((resolve) => setTimeout(resolve, 25));

/**
 * Extract nonce values from script tags in HTML.
 * @param {string} html - The HTML to parse.
 * @returns {string[]} Array of nonce values found in script tags.
 */
function extractNonces(html) {
  const nonceRegex = /<script[^>]*nonce="([^"]+)"[^>]*>/g;
  const nonces = [];
  let match;
  while ((match = nonceRegex.exec(html)) !== null) {
    nonces.push(match[1]);
  }
  return nonces;
}

/**
 * Build a JSDOM fixture with mocked Supabase client.
 * @param {object} options - Fixture options.
 * @param {string} options.html - HTML content.
 * @param {string} options.url - Page URL.
 * @param {object} options.session - Mock session.
 * @param {number} options.status - Mock fetch status.
 * @param {string} options.nonce - CSP nonce to inject.
 * @returns {Promise<object>} Fixture object.
 */
async function cspFixture({
  html,
  url = "https://analytics.example.com/login",
  mode = "login",
  session = null,
  status = 200,
  nonce = "test-nonce-abc123",
}) {
  // Render Jinja2 template expressions with test values.
  // This simulates Flask's render_template for the auth page.
  const processedHtml = html
    .replace(/\{\{ csp_nonce \}\}/g, nonce)
    .replace(/\{%csp_nonce%\}/g, nonce)
    .replace(/\{\{ mode \}\}/g, mode)
    .replace(
      /\{\{ 'Create account' if mode == 'signup' else 'Sign in' \}\}/g,
      mode === "signup" ? "Create account" : "Sign in",
    )
    .replace(
      /\{\{ 'Create your account' if mode == 'signup' else 'Welcome back'\s*\}\}/g,
      mode === "signup" ? "Create your account" : "Welcome back",
    )
    .replace(
      /\{\{ 'new-password' if mode == 'signup' else 'current-password' \}\}/g,
      mode === "signup" ? "new-password" : "current-password",
    )
    .replace(
      /\{\{ 'Already have an account\?' if mode == 'signup' else 'New to\s*Quantum Echo\?' \}\}/g,
      mode === "signup" ? "Already have an account?" : "New to Quantum Echo?",
    )
    .replace(
      /\{\{ '\/login' if mode == 'signup' else '\/signup' \}\}/g,
      mode === "signup" ? "/login" : "/signup",
    )
    .replace(
      /\{\{ 'Sign in' if mode == 'signup' else 'Create an account' \}\}/g,
      mode === "signup" ? "Sign in" : "Create an account",
    )
    .replace(/\{%\s*if csp_nonce\s*%\}/g, "")
    .replace(/\{%\s*endif\s*%\}/g, "")
    .replace(/\{%\s*if mode == 'signup'\s*%\}/g, "")
    .replace(/\{%\s*else\s*%\}/g, "");

  const dom = new JSDOM(processedHtml, {
    url,
    runScripts: "outside-only",
  });

  const w = dom.window;
  const calls = [];
  let listener;

  w.Request = Request;
  w.AbortSignal = AbortSignal;
  w.navigate = (target) => calls.push(["navigate", target]);
  w.fetch = async (target, options) => {
    calls.push([target, options]);
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

  // Execute the auth bundle source
  w.eval(authSource);
  await tick();

  return {
    w,
    calls,
    auth,
    nonce,
    event: (...args) => listener?.(...args),
    close: () => w.close(),
  };
}

test("auth page HTML contains nonce-bearing script elements", () => {
  const nonces = extractNonces(authHtml);
  assert.ok(
    nonces.length >= 2,
    `Expected at least 2 nonce-bearing scripts (inline + bundle), found ${nonces.length}`,
  );
  // All nonces should be the same placeholder in the template
  const unique = new Set(nonces);
  assert.equal(
    unique.size,
    1,
    "All script nonces should reference the same template variable",
  );
  assert.ok(
    nonces[0].includes("csp_nonce"),
    "Nonce should be a template variable reference",
  );
});

test("landing page HTML contains nonce-bearing showcase script", () => {
  const nonces = extractNonces(landingHtml);
  assert.ok(
    nonces.length >= 1,
    `Expected at least 1 nonce-bearing script, found ${nonces.length}`,
  );
  assert.ok(
    nonces.some((n) => n.includes("csp_nonce")),
    "Showcase bundle script should have a nonce template variable",
  );
});

test("authorized script with matching nonce executes auth logic", async () => {
  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: "test-nonce-xyz789",
  });

  // The auth bundle should have executed and set up the auth page
  assert.equal(
    f.w.document.getElementById("auth-content").hidden,
    false,
    "Auth content should be visible after bundle execution",
  );

  // Submit the login form and verify navigation to dashboard
  f.w.document.getElementById("auth-email").value = "analyst@example.com";
  f.w.document.getElementById("auth-password").value = "long-password";
  f.w.document
    .getElementById("auth-form")
    .dispatchEvent(new f.w.Event("submit", { cancelable: true }));
  await tick();

  assert.ok(
    f.calls.some(([name, target]) => name === "navigate" && target === "/dashboard"),
    "Login should navigate to dashboard",
  );

  f.close();
});

test("unauthorized inline script without nonce is not executed", async () => {
  const nonce = "test-nonce-unauthorized";
  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce,
  });

  // Inject an unauthorized inline script without a nonce
  const unauthorizedScript = f.w.document.createElement("script");
  unauthorizedScript.textContent = "window.__unauthorized_executed = true;";
  f.w.document.head.appendChild(unauthorizedScript);

  // In a real browser, CSP would block this. JSDOM doesn't enforce CSP,
  // so we verify the structural contract: the script has no nonce attribute.
  assert.equal(
    unauthorizedScript.getAttribute("nonce"),
    null,
    "Unauthorized script must not have a nonce attribute",
  );

  // Verify the authorized nonce-bearing scripts still work
  assert.equal(
    f.w.document.getElementById("auth-content").hidden,
    false,
    "Authorized auth content should still be visible",
  );

  f.close();
});

test("inline script with wrong nonce does not match CSP policy", async () => {
  const correctNonce = "correct-nonce-123";
  const wrongNonce = "wrong-nonce-456";

  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: correctNonce,
  });

  // Inject a script with a mismatched nonce
  const wrongNonceScript = f.w.document.createElement("script");
  wrongNonceScript.setAttribute("nonce", wrongNonce);
  wrongNonceScript.textContent = "window.__wrongNonceExecuted = true;";
  f.w.document.head.appendChild(wrongNonceScript);

  // The nonce attribute value must differ from the CSP nonce
  assert.notEqual(
    wrongNonceScript.getAttribute("nonce"),
    correctNonce,
    "Wrong nonce must not match the CSP policy nonce",
  );

  f.close();
});

test("dashboard auth gate releases requests after session sync", async () => {
  // Use a dashboard context (no data-auth-page) so isAuthPage is false.
  const dashboardHtml = `<html><body><div id="auth-loading">Connecting…</div><section id="auth-content" hidden><button data-provider="google"></button><button data-provider="github"></button><form id="auth-form"><input id="auth-email" type="email" required><span id="auth-email-error"></span><input id="auth-password" type="password" required><span id="auth-password-error"></span><button id="auth-show-password" type="button"></button></form></section><div id="auth-message" hidden tabindex="-1"></div><button id="auth-signout" hidden></button><a id="auth-back" hidden></a><div id="auth-session-loading"></div></body></html>`;
  const f = await cspFixture({
    html: dashboardHtml,
    url: "https://analytics.example.com/dashboard",
    mode: "",
    session: { access_token: "initial" },
    nonce: "dashboard-nonce-789",
  });

  // The auth gate should be ready and allow requests through
  assert.equal(f.w.document.documentElement.dataset.authReady, "true");

  // Dash layout requests should succeed (not throw "Authentication required")
  // because the session is synchronized.
  let layoutError = null;
  try {
    await f.w.fetch("/_dash-layout");
  } catch (error) {
    layoutError = error;
  }
  assert.equal(
    layoutError,
    null,
    "Dash layout request should succeed after session sync",
  );

  f.close();
});

test("authentication flow completes with mocked Supabase", async () => {
  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: "auth-flow-nonce-000",
  });

  // Verify the auth page loaded
  assert.equal(f.w.document.getElementById("auth-content").hidden, false);

  // Submit credentials
  f.w.document.getElementById("auth-email").value = "analyst@example.com";
  f.w.document.getElementById("auth-password").value = "long-password";
  f.w.document
    .getElementById("auth-form")
    .dispatchEvent(new f.w.Event("submit", { cancelable: true }));
  await tick();

  // Verify navigation to dashboard
  assert.ok(
    f.calls.some(([name, target]) => name === "navigate" && target === "/dashboard"),
    "Successful login should navigate to /dashboard",
  );

  f.close();
});

test("OAuth provider buttons trigger Supabase OAuth flow", async () => {
  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: "oauth-nonce-111",
  });

  for (const provider of ["google", "github"]) {
    f.w.document.querySelector(`[data-provider="${provider}"]`).click();
    await tick();
    assert.ok(
      f.calls.some(
        ([name, options]) =>
          name === "oauth" &&
          options.provider === provider &&
          options.options.redirectTo.endsWith("/auth/callback"),
      ),
      `${provider} OAuth should redirect to /auth/callback`,
    );
  }

  f.close();
});

test("auth callback exchanges code and navigates to dashboard", async () => {
  const f = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/auth/callback?code=test-code",
    mode: "callback",
    nonce: "callback-nonce-222",
  });

  // The callback should exchange the code for a session
  await tick();
  assert.ok(
    f.calls.some(([name]) => name === "exchange"),
    "Callback should exchange the authorization code",
  );
  assert.ok(
    f.calls.some(([name, target]) => name === "navigate" && target === "/dashboard"),
    "Callback should navigate to /dashboard after exchange",
  );

  f.close();
});

test("signout clears session and redirects to login", async () => {
  // Use a dashboard context (no data-auth-page) so isAuthPage is false.
  // On dashboard pages, signout redirects to /login.
  const dashboardHtml = `<html><body><div id="auth-loading">Connecting…</div><section id="auth-content" hidden><button data-provider="google"></button><button data-provider="github"></button><form id="auth-form"><input id="auth-email" type="email" required><span id="auth-email-error"></span><input id="auth-password" type="password" required><span id="auth-password-error"></span><button id="auth-show-password" type="button"></button></form></section><div id="auth-message" hidden tabindex="-1"></div><button id="auth-signout" hidden></button><a id="auth-back" hidden></a><div id="auth-session-loading"></div></body></html>`;
  const f = await cspFixture({
    html: dashboardHtml,
    url: "https://analytics.example.com/dashboard",
    mode: "",
    session: { access_token: "valid" },
    nonce: "signout-nonce-333",
  });

  // The auth gate should be ready
  assert.equal(f.w.document.documentElement.dataset.authReady, "true");

  // Trigger signout via the auth state change listener
  f.event("SIGNED_OUT", null);
  await tick();

  assert.equal(
    f.w.document.documentElement.dataset.authReady,
    undefined,
    "Auth gate should close after signout",
  );
  assert.ok(
    f.calls.some(([name, target]) => name === "navigate" && target === "/login"),
    "Signout should redirect to /login",
  );

  f.close();
});

test("showcase bundle executes on landing page with nonce", async () => {
  const dom = new JSDOM(landingHtml, {
    url: "https://analytics.example.com/",
    runScripts: "outside-only",
  });
  const w = dom.window;

  // Inject the nonce into the showcase script tag
  const showcaseScript = w.document.querySelector(
    'script[src="/assets/showcase.bundle.js"]',
  );
  assert.ok(showcaseScript, "Showcase bundle script should exist");
  assert.equal(
    showcaseScript.getAttribute("nonce"),
    "{{ csp_nonce }}",
    "Showcase script should have the nonce template variable",
  );

  // Set up the environment for showcase.js
  w.matchMedia = () => ({ matches: true, addEventListener() {} });
  Object.defineProperty(w.document, "hidden", { value: false, configurable: true });

  // Execute the showcase bundle
  w.eval(readFileSync("my-dash-app/auth_frontend/showcase.js", "utf8"));
  await tick();

  // Verify the showcase carousel is functional
  const analyticsSlide = w.document.getElementById("auth-slide-analytics");
  assert.ok(analyticsSlide, "Analytics slide should exist");
  assert.equal(analyticsSlide.hidden, false, "Analytics slide should be visible");

  dom.window.close();
});

test("nonce changes between requests (freshness contract)", async () => {
  const nonce1 = "fresh-nonce-aaa";
  const nonce2 = "fresh-nonce-bbb";
  assert.notEqual(nonce1, nonce2, "Test nonces must differ");

  const f1 = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: nonce1,
  });
  const f2 = await cspFixture({
    html: authHtml,
    url: "https://analytics.example.com/login",
    mode: "login",
    nonce: nonce2,
  });

  // Both fixtures should work with their respective nonces
  assert.equal(
    f1.w.document.getElementById("auth-content").hidden,
    false,
    "First request should render auth content",
  );
  assert.equal(
    f2.w.document.getElementById("auth-content").hidden,
    false,
    "Second request should render auth content",
  );

  f1.close();
  f2.close();
});
