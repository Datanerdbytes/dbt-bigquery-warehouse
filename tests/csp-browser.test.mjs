/** Enforced CSP regression tests against the actual local Flask/Dash app.
 * Chromium loads built bundles; Supabase HTTP and all data are synthetic.
 * JSDOM tests remain in auth-browser.test.mjs for detailed auth unit coverage.
 */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createInterface } from "node:readline";
import { chromium } from "playwright";

let server, browser, fixture;
let serverErrors = "";
const mockOrigin = "https://csp-test.supabase.co";
const storageKey = "sb-csp-test-auth-token";
before(async () => {
  server = spawn(
    process.env.CSP_TEST_PYTHON || ".venv/bin/python",
    ["-B", "tests/csp_test_server.py"],
    {
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    },
  );
  server.stderr.on("data", (chunk) => {
    serverErrors += chunk;
  });
  const lines = createInterface({ input: server.stdout });
  fixture = await new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`Fixture startup timeout: ${serverErrors}`)),
      20000,
    );
    server.once("error", reject);
    server.once("exit", (code) =>
      reject(new Error(`Fixture exited ${code}: ${serverErrors}`)),
    );
    lines.on("line", (line) => {
      if (!line.startsWith('{"origin":')) return;
      clearTimeout(timer);
      resolve(JSON.parse(line));
    });
  });
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) {
    const exited = once(server, "exit");
    server.kill("SIGTERM");
    await exited;
  }
});

function session() {
  return {
    access_token: fixture.token,
    refresh_token: "synthetic-refresh",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: fixture.user,
  };
}
async function pageFixture(t, { signedIn = false, refresh = false } = {}) {
  const context = await browser.newContext();
  t.after(() => context.close());
  const requests = [],
    failures = [],
    errors = [],
    external = [];
  await context.route("**/*", async (route) => {
    const request = route.request(),
      url = new URL(request.url());
    requests.push({ url: request.url(), method: request.method() });
    if (url.origin === fixture.origin) return route.continue();
    if (url.origin === mockOrigin) {
      const headers = {
        "access-control-allow-origin": fixture.origin,
        "access-control-allow-headers": "*",
        "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
      };
      if (request.method() === "OPTIONS")
        return route.fulfill({ status: 204, headers });
      if (url.pathname === "/auth/v1/user")
        return route.fulfill({ json: fixture.user, headers });
      if (url.pathname === "/auth/v1/token")
        return route.fulfill({ json: session(), headers });
      if (url.pathname === "/auth/v1/logout")
        return route.fulfill({ status: 204, headers });
      if (url.pathname === "/auth/v1/signup")
        return route.fulfill({
          json: { user: fixture.user, session: null },
          headers,
        });
      if (url.pathname === "/auth/v1/authorize")
        return route.fulfill({
          body: "Synthetic OAuth provider",
          contentType: "text/html",
          headers,
        });
      throw new Error(`Unexpected mock auth request: ${url.pathname}`);
    }
    // External styles/fonts are replaced locally; no real network requests.
    if (
      [
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "cdn.jsdelivr.net",
      ].includes(url.hostname)
    ) {
      return route.fulfill({ body: "", contentType: "text/css" });
    }
    external.push(request.url());
    return route.abort();
  });
  if (signedIn || refresh) {
    const value = session();
    if (refresh) {
      value.expires_at = 1;
    }
    await context.addInitScript(
      ({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
      { key: storageKey, value },
    );
    await context.addCookies([
      {
        name: "qe_access_token",
        value: fixture.token,
        url: fixture.origin,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
  }
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      window.cspViolations.push({
        directive: e.effectiveDirective,
        blocked: e.blockedURI,
        disposition: e.disposition,
      });
    });
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().startsWith(fixture.origin) && response.status() >= 500)
      failures.push(`${response.status()} ${response.url()}`);
  });
  return { page, context, requests, failures, errors, external };
}
async function assertHealthy(f) {
  assert.deepEqual(f.failures, [], `Server errors: ${serverErrors}`);
  assert.deepEqual(f.errors, []);
  assert.deepEqual(f.external, []);
  assert.deepEqual(await f.page.evaluate(() => window.cspViolations), []);
}
async function dashboardReady(f) {
  await f.page.waitForFunction(
    () => document.documentElement.dataset.authReady === "true",
  );
  await f.page.locator("#overview-page-loaded").waitFor({ state: "attached" });
  await f.page.locator(".js-plotly-plot").first().waitFor();
  await f.page.waitForFunction(() =>
    [...document.querySelectorAll(".js-plotly-plot")].some(
      (el) => el._fullLayout,
    ),
  );
}

test("Chromium enforces nonce policy: approved scripts run; missing/wrong nonce and eval are blocked", async (t) => {
  const f = await pageFixture(t);
  // Inject through HTTP HTML: DevTools evaluation is privileged and can
  // bypass CSP even when constructing script elements.
  await f.page.route(`${fixture.origin}/login`, async (route) => {
    const original = await route.fetch();
    const nonce = original
      .headers()
      ["content-security-policy"].match(/'nonce-([^']+)'/)[1];
    const injection = `<script>window.missingNonce = true</script>
      <script nonce="wrong-nonce">window.wrongNonce = true</script>
      <script nonce="${nonce}">window.approvedNonce = true;
        try { eval('window.evalRan = true'); } catch { window.evalBlocked = true; }
      </script>`;
    await route.fulfill({
      response: original,
      body: (await original.text()).replace("</body>", `${injection}</body>`),
    });
  });
  const response = await f.page.goto(`${fixture.origin}/login`);
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  const csp = response.headers()["content-security-policy"];
  assert.match(csp, /script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  assert.equal(await f.page.evaluate(() => window.qeAuthStarted), true);
  await f.page.waitForFunction(() => window.cspViolations.length >= 3);
  assert.deepEqual(
    await f.page.evaluate(() => ({
      approved: window.approvedNonce,
      missing: !!window.missingNonce,
      wrong: !!window.wrongNonce,
      evalRan: !!window.evalRan,
      evalBlocked: window.evalBlocked,
    })),
    {
      approved: true,
      missing: false,
      wrong: false,
      evalRan: false,
      evalBlocked: true,
    },
  );
  const violations = await f.page.evaluate(() => window.cspViolations);
  assert.equal(violations.filter((v) => v.blocked === "inline").length, 2);
  assert.ok(violations.some((v) => v.blocked === "eval"));
  assert.ok(violations.every((v) => v.disposition === "enforce"));
});

test("HTML nonces match headers and change on reload; landing bundle runs", async (t) => {
  const f = await pageFixture(t);
  const first = await f.page.goto(fixture.origin);
  await f.page.locator("#auth-slide-analytics").waitFor();
  const readNonces = () =>
    f.page.evaluate(() =>
      [...document.querySelectorAll("script")].map((s) => s.nonce),
    );
  const nonces1 = await readNonces();
  assert.ok(
    nonces1.length &&
      nonces1.every(
        (n) =>
          n &&
          first.headers()["content-security-policy"].includes(`'nonce-${n}'`),
      ),
  );
  const second = await f.page.reload();
  const nonces2 = await readNonces();
  assert.notEqual(nonces1[0], nonces2[0]);
  assert.ok(
    nonces2.every((n) =>
      second.headers()["content-security-policy"].includes(`'nonce-${n}'`),
    ),
  );
  assert.match(second.headers()["cache-control"], /no-store/);
  await assertHealthy(f);
});

test("actual password login, Dash bootstrap/chunks, Plotly, client callbacks and navigation work under CSP", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(`${fixture.origin}/login`);
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  await f.page.locator("#auth-email").fill("test@example.com");
  await f.page.locator("#auth-password").fill("synthetic-password");
  await f.page.locator('#auth-form button[type="submit"]').click();
  await dashboardReady(f);
  await f.page.waitForFunction(() => {
    const graph = document.querySelector("#sales-trend-graph .js-plotly-plot");
    return graph?._fullData?.some((trace) =>
      trace.y?.some((value) => Number(value) > 0),
    );
  });
  await f.page.getByText("Fixture Bike", { exact: true }).first().waitFor();
  assert.ok(f.requests.some((r) => r.url.includes("grant_type=password")));
  assert.ok(
    f.requests.some((r) => /async-graph|plotly.*\.js/.test(r.url)),
    "Dash dynamic graph/Plotly chunk must load",
  );
  assert.ok(
    f.requests.some(
      (r) => r.url.includes("/_dash-update-component") && r.method === "POST",
    ),
  );
  // The sidebar toggle exercises a server callback after the Dash auth gate.
  const toggle = f.page.locator("#sidebar-toggle-btn");
  if (await toggle.count()) {
    const before = await f.page.locator("#app-wrapper").getAttribute("class");
    await toggle.click();
    await f.page.waitForFunction(
      (value) => document.getElementById("app-wrapper").className !== value,
      before,
    );
  } else {
    throw new Error("Expected sidebar toggle for real callback verification");
  }
  await f.page.locator('a[href="/customers"]').first().click();
  await f.page.locator("#c360-page-loaded").waitFor({ state: "attached" });
  await f.page.locator('a[href="/pipeline-health"]').first().click();
  await f.page.locator("#pipeline-tabs").waitFor();
  await assertHealthy(f);
  if (
    (await f.page.locator("#app-wrapper").getAttribute("class")).includes(
      "sidebar-closed",
    )
  ) {
    await f.page.locator("#sidebar-toggle-btn").click();
  }
  await f.page.locator("#sidebar-account summary").click();
  await f.page.locator("#dashboard-signout").click();
  await f.page.waitForURL("**/login");
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  assert.ok(
    !(await f.context.cookies()).some((c) => c.name === "qe_access_token"),
  );
  const denied = await f.context.request.get(`${fixture.origin}/_dash-layout`);
  assert.equal(denied.status(), 401);
  await assertHealthy(f);
});

test("session refresh reaches only configured Supabase origin and releases Dash auth gate", async (t) => {
  const f = await pageFixture(t, { refresh: true });
  await f.page.goto(`${fixture.origin}/dashboard`);
  await dashboardReady(f);
  assert.ok(f.requests.some((r) => r.url.includes("grant_type=refresh_token")));
  await assertHealthy(f);
});

test("OAuth callback exchange and canceled OAuth recovery work under CSP", async (t) => {
  const f = await pageFixture(t);
  await f.context.addInitScript(
    (key) =>
      localStorage.setItem(`${key}-code-verifier`, "synthetic-pkce-verifier"),
    storageKey,
  );
  await f.page.goto(`${fixture.origin}/auth/callback?code=synthetic-code`);
  await dashboardReady(f);
  assert.ok(f.requests.some((r) => r.url.includes("grant_type=pkce")));
  await assertHealthy(f);
  await f.context.clearCookies();
  await f.page.goto(`${fixture.origin}/auth/callback?error=access_denied`);
  await f.page.waitForFunction(() =>
    document
      .getElementById("auth-message")
      ?.textContent.includes("invalid or canceled"),
  );
  await assertHealthy(f);
});

test("signup confirmation and OAuth provider launch still work", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(`${fixture.origin}/signup`);
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  await f.page.locator("#auth-email").fill("test@example.com");
  await f.page.locator("#auth-password").fill("synthetic-password");
  await f.page.locator('#auth-form button[type="submit"]').click();
  await f.page.waitForFunction(() =>
    document
      .getElementById("auth-message")
      ?.textContent.includes("Check your email"),
  );
  await assertHealthy(f);
  await f.page.goto(`${fixture.origin}/login`);
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  await f.page.locator('[data-provider="google"]').click();
  await f.page.waitForURL("https://csp-test.supabase.co/**");
  assert.ok(
    f.requests.some(
      (r) => r.url.includes("/authorize?") && r.url.includes("provider=google"),
    ),
  );
});
