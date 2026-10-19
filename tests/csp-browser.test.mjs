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

function session(admin = false, manager = false) {
  return {
    access_token: manager
      ? fixture.managerToken
      : admin
        ? fixture.adminToken
        : fixture.token,
    refresh_token: "synthetic-refresh",
    token_type: "bearer",
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: manager
      ? fixture.managerUser
      : admin
        ? fixture.adminUser
        : fixture.user,
  };
}
async function pageFixture(
  t,
  { signedIn = false, refresh = false, admin = false, manager = false } = {},
) {
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
        "access-control-allow-methods": "GET,POST,PUT,DELETE,OPTIONS",
      };
      if (request.method() === "OPTIONS")
        return route.fulfill({ status: 204, headers });
      if (url.pathname === "/auth/v1/recover")
        return route.fulfill({ json: {}, headers });
      if (url.pathname === "/auth/v1/user")
        return route.fulfill({
          json: manager
            ? fixture.managerUser
            : admin
              ? fixture.adminUser
              : fixture.user,
          headers,
        });
      if (url.pathname === "/auth/v1/token")
        return route.fulfill({ json: session(admin, manager), headers });
      if (url.pathname === "/auth/v1/logout")
        return route.fulfill({ status: 204, headers });
      if (url.pathname === "/auth/v1/signup")
        return route.fulfill({
          json: {
            user: manager
              ? fixture.managerUser
              : admin
                ? fixture.adminUser
                : fixture.user,
            session: null,
          },
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
  if (signedIn || refresh || admin || manager) {
    const value = session(admin, manager);
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
        value: manager
          ? fixture.managerToken
          : admin
            ? fixture.adminToken
            : fixture.token,
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

test("landing autoplay resumes after tab return and pauses only while hovered", async (t) => {
  const f = await pageFixture(t);
  await f.page.clock.install();
  await f.page.goto(fixture.origin);
  await f.page.locator(".auth-carousel-controls:not([hidden])").waitFor();
  assert.equal(await f.page.locator('[data-carousel="rotation"]').count(), 1);
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  await f.page.locator(".auth-slide:not([hidden]) .auth-preview").hover();
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  await f.page.locator(".landing-header").hover();
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    false,
  );
  await f.page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    false,
  );
  await f.page.evaluate(() => {
    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  await f.page.locator('.landing-nav [data-slide="0"]').click();
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  const rotation = f.page.locator('[data-carousel="rotation"]');
  await rotation.click();
  await f.page.locator(".landing-header").hover();
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  assert.equal(
    await rotation.textContent().then((text) => text.trim()),
    "Play",
  );
  await rotation.focus();
  await rotation.press("Enter");
  await f.page.locator(".landing-header").hover();
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    false,
  );
  assert.equal(
    await f.page
      .locator("#auth-slide-analytics")
      .evaluate((el) => getComputedStyle(el).animationDuration),
    "0.45s",
  );
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
  await f.page.waitForFunction(() => {
    const graph = document.querySelector("#sales-trend-graph .js-plotly-plot");
    return (
      graph?._fullData?.[0]?.type === "bar" &&
      graph?._fullData?.[1]?.type === "scatter" &&
      graph._fullData[1].yaxis === "y2" &&
      graph._fullData[1].y.some((value) => value > 0)
    );
  });
  await f.page
    .locator("#sales-trend-graph")
    .screenshot({ path: "/tmp/sales-margin-chart.png" });
  await f.page.setViewportSize({ width: 375, height: 812 });
  await f.page.locator("#sales-trend-graph").scrollIntoViewIfNeeded();
  await f.page
    .locator("#sales-trend-graph")
    .screenshot({ path: "/tmp/sales-margin-mobile.png" });
  await f.page.setViewportSize({ width: 1280, height: 720 });
  await f.page.getByText("Fixture Bike", { exact: true }).first().waitFor();
  assert.ok(
    f.requests.some((r) => r.url === `${fixture.origin}/auth/password`),
  );
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
    assert.equal(await toggle.getAttribute("aria-expanded"), "true");
    assert.equal(await toggle.locator(".bi-chevron-double-left").count(), 1);
    const before = await f.page.locator("#app-wrapper").getAttribute("class");
    await toggle.click();
    await f.page.waitForFunction(
      (value) => document.getElementById("app-wrapper").className !== value,
      before,
    );
    assert.equal(await toggle.getAttribute("aria-expanded"), "false");
    assert.equal(await toggle.locator(".bi-chevron-double-right").count(), 1);
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
    await f.page
      .locator("#sidebar-toggle-btn .bi-chevron-double-left")
      .waitFor({ state: "attached" });
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
      ?.textContent.includes("Sign-in was canceled"),
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

test("revenue donut and country map render under enforced CSP", async (t) => {
  const f = await pageFixture(t, { signedIn: true });
  await f.page.goto(`${fixture.origin}/dashboard`);
  await dashboardReady(f);
  const donutReady = async () => {
    await f.page.waitForFunction(
      () =>
        document.querySelector("#category-pie-graph .js-plotly-plot")
          ?._fullData?.[0]?.type === "pie",
    );
    assert.ok(await f.page.locator("#category-pie-graph .slice").count());
    assert.match(
      await f.page
        .locator("#category-pie-graph .annotation")
        .allTextContents()
        .then((text) => text.join(" ")),
      /Total revenue.*\$50/,
    );
  };
  await donutReady();
  await f.page.getByRole("button", { name: "Replace revenue chart" }).click();
  // External Bootstrap CSS is stubbed in this offline fixture; use keyboard
  // activation so the dropdown is not covered by the unstyled graph container.
  await f.page.locator("#overview-revenue-map").focus();
  await f.page.locator("#overview-revenue-map").press("Enter");
  await f.page
    .locator("#category-pie-graph .choroplethlayer path")
    .first()
    .waitFor();
  assert.ok(
    f.requests.some(
      (r) => r.url === `${fixture.origin}/assets/topojson/world_110m.json`,
    ),
  );
  await assertHealthy(f);
  await f.page
    .locator("#category-pie-graph")
    .screenshot({ path: "/tmp/revenue-map.png" });
  // A saved map view must load on page navigation, then switch back cleanly.
  await f.page.reload();
  await dashboardReady(f);
  await f.page
    .locator("#category-pie-graph .choroplethlayer path")
    .first()
    .waitFor();
  await f.page.getByRole("button", { name: "Replace revenue chart" }).click();
  await f.page.locator("#overview-revenue-donut").focus();
  await f.page.locator("#overview-revenue-donut").press("Enter");
  await donutReady();
  await assertHealthy(f);
  await f.page
    .locator("#category-pie-graph")
    .screenshot({ path: "/tmp/revenue-donut.png" });
  await f.page.setViewportSize({ width: 375, height: 812 });
  await f.page.emulateMedia({ reducedMotion: "reduce" });
  await f.page.locator("#category-pie-graph").scrollIntoViewIfNeeded();
  await f.page
    .locator("#category-pie-graph")
    .screenshot({ path: "/tmp/revenue-donut-mobile.png" });
  await donutReady();
});

test("KPI sparklines load on both pages, follow filters and fit narrow cards", async (t) => {
  const f = await pageFixture(t, { signedIn: true });
  f.page.setDefaultTimeout(8000);
  await f.page.setViewportSize({ width: 1600, height: 900 });
  await f.page.goto(`${fixture.origin}/dashboard`);
  await dashboardReady(f);
  const sparklineReady = async () => {
    await f.page.waitForFunction(
      () => {
        const graphs = [
          ...document.querySelectorAll(".kpi-sparkline .js-plotly-plot"),
        ];
        return (
          graphs.length === 4 &&
          graphs.every((graph) => graph._fullData?.[0]?.type === "scatter")
        );
      },
      null,
      { timeout: 15000 },
    );
  };
  const checkMobileCards = async (name) => {
    await f.page.setViewportSize({ width: 375, height: 812 });
    await f.page.emulateMedia({ reducedMotion: "reduce" });
    await f.page.locator(".kpi-grid").scrollIntoViewIfNeeded();
    await f.page
      .locator(".kpi-grid")
      .screenshot({ path: `/tmp/${name}-kpi-sparklines-mobile.png` });
    const bounds = await f.page
      .locator(".kpi-card-with-trend")
      .evaluateAll((cards) =>
        cards.map((card) => {
          const value = card
            .querySelector(".kpi-summary")
            .getBoundingClientRect();
          const graph = card
            .querySelector(".kpi-sparkline")
            .getBoundingClientRect();
          const outer = card.getBoundingClientRect();
          return {
            stacked: graph.top >= value.bottom,
            contained:
              graph.right <= outer.right &&
              graph.left >= outer.left &&
              graph.bottom <= outer.bottom &&
              graph.height >= 60,
          };
        }),
      );
    assert.ok(bounds.every((card) => card.stacked && card.contained));
  };
  await sparklineReady();
  await f.page
    .locator(".kpi-grid")
    .screenshot({ path: "/tmp/product-kpi-sparklines.png" });
  await f.page.locator("#country-dropdown").click();
  await f.page.getByRole("option", { name: "PH", exact: true }).click();
  await f.page.waitForFunction(
    () => {
      const graph = document.querySelector(
        "#kpi-sales-sparkline .js-plotly-plot",
      );
      return (
        graph?._fullData?.[0]?.y?.reduce((sum, value) => sum + value, 0) === 40
      );
    },
    null,
    { timeout: 15000 },
  );
  await checkMobileCards("product");
  await f.page.setViewportSize({ width: 1600, height: 900 });
  await f.page.locator('a[href="/customers"]').first().click();
  await f.page.locator("#c360-page-loaded").waitFor({ state: "attached" });
  await sparklineReady();
  await f.page
    .locator(".kpi-grid")
    .screenshot({ path: "/tmp/customer-kpi-sparklines.png" });
  await checkMobileCards("customer");
  await assertHealthy(f);
});

test("signup password Show and Hide work with pointer and keyboard under CSP", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(`${fixture.origin}/signup`);
  await f.page.locator("#auth-content:not([hidden])").waitFor();
  const input = f.page.locator("#auth-password");
  const toggle = f.page.locator("#auth-show-password");
  await input.fill("synthetic-password");
  await toggle.click();
  assert.equal(await input.getAttribute("type"), "text");
  assert.equal(await toggle.getAttribute("aria-label"), "Hide password");
  await toggle.focus();
  await toggle.press("Enter");
  assert.equal(await input.getAttribute("type"), "password");
  assert.equal(await input.inputValue(), "synthetic-password");
  assert.equal(await toggle.getAttribute("aria-pressed"), "false");
  assert.equal(
    await f.page.locator(".auth-note").textContent(),
    "Verify your email to access your workspace.",
  );
  assert.equal(
    f.requests.some((r) => r.url.includes("grant_type=password")),
    false,
  );
  await assertHealthy(f);
});

test("members cannot open user management or its API", async (t) => {
  const f = await pageFixture(t, { signedIn: true });
  const response = await f.page.goto(`${fixture.origin}/admin/users`);
  assert.equal(response.status(), 403);
  await f.page
    .getByRole("heading", { name: "Admin access required" })
    .waitFor();
  const api = await f.context.request.get(`${fixture.origin}/api/admin/users`);
  assert.equal(api.status(), 403);
  assert.equal(await f.page.locator("#admin-users-grid").count(), 0);
  await assertHealthy(f);
});
test("admin directory manages access and roles, confirms actions, and fits mobile", async (t) => {
  const f = await pageFixture(t, { admin: true });
  await f.page.setViewportSize({ width: 1440, height: 1000 });
  await f.page.goto(`${fixture.origin}/admin/users`);
  await f.page.locator("#admin-users-grid .ag-row").first().waitFor();
  await f.page.getByText("member@example.com", { exact: true }).first().click();
  await f.page.waitForFunction(
    () => !document.getElementById("admin-users-suspend").disabled,
  );
  await f.page.screenshot({
    path: "/tmp/quantum-echo-user-management-desktop.png",
    fullPage: true,
  });
  const perform = async (action, expected) => {
    const row = f.page
      .locator("#admin-users-grid .ag-row")
      .filter({ hasText: "member@example.com" });
    if ((await row.getAttribute("aria-selected")) !== "true") await row.click();
    await f.page.locator(`#admin-users-${action}`).click();
    await f.page.locator("#admin-users-confirm-modal").waitFor();
    await f.page.locator("#admin-users-confirm").focus();
    await f.page.locator("#admin-users-confirm").press("Enter");
    await f.page.getByText(expected, { exact: true }).waitFor();
    const feedback = f.page.locator("#admin-users-action-message");
    await f.page.waitForFunction(() => {
      const bounds = document
        .getElementById("admin-users-action-message")
        .getBoundingClientRect();
      return bounds.top >= 0 && bounds.top < innerHeight;
    });
    assert.equal(
      await feedback.evaluate(
        (el) =>
          el.getBoundingClientRect().top >= 0 &&
          el.getBoundingClientRect().top < innerHeight,
      ),
      true,
    );
    assert.equal(
      await feedback.evaluate((el) =>
        Boolean(
          el.compareDocumentPosition(document.querySelector(".admin-hero")) &
            Node.DOCUMENT_POSITION_FOLLOWING,
        ),
      ),
      true,
    );

    await f.page.waitForFunction(
      () =>
        document.getElementById("admin-users-selected")?.textContent ===
        "Select an account",
    );
  };
  // Cancel must not perform the selected mutation.
  await f.page.locator("#admin-users-suspend").click();
  await f.page.locator("#admin-users-confirm-modal").waitFor();
  // External Bootstrap CSS is stubbed in this offline fixture. Use keyboard
  // activation for modal controls, as in the existing export-menu tests.
  await f.page.locator("#admin-users-cancel").focus();
  await f.page.locator("#admin-users-cancel").press("Enter");
  await f.page
    .locator("#admin-users-confirm-modal")
    .waitFor({ state: "hidden" });
  await perform("grant_admin", "Administrator access granted.");
  await perform("revoke_admin", "Administrator access revoked.");
  await perform("suspend", "Account suspended.");
  assert.equal(
    await f.page.locator("#admin-users-restore").isDisabled(),
    true,
    "Selection resets after a change",
  );
  await f.page
    .locator("#admin-users-grid .ag-row")
    .filter({ hasText: "member@example.com" })
    .click();
  await f.page.waitForFunction(
    () => !document.getElementById("admin-users-restore").disabled,
  );
  assert.equal(
    await f.page.locator("#admin-users-revoke_admin").isDisabled(),
    true,
    "Members do not have admin access to revoke",
  );

  await perform("restore", "Account access restored.");
  await f.page
    .locator("#admin-users-grid .ag-row")
    .filter({ hasText: "admin@example.com" })
    .click();
  await f.page.waitForFunction(
    () => document.getElementById("admin-users-revoke_admin").disabled,
  );
  assert.equal(await f.page.locator("#admin-users-suspend").isDisabled(), true);
  await f.page.setViewportSize({ width: 375, height: 812 });
  await f.page.emulateMedia({ reducedMotion: "reduce" });
  await f.page.waitForFunction(
    () =>
      parseFloat(
        getComputedStyle(document.querySelector(".main-content-wrapper"))
          .marginLeft,
      ) === 0,
  );
  await f.page.screenshot({
    animations: "disabled",
    path: "/tmp/quantum-echo-user-management-mobile.png",
    fullPage: true,
  });
  assert.equal(
    await f.page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await assertHealthy(f);
});

test("non-owner administrators cannot see or invoke account deletion", async (t) => {
  const f = await pageFixture(t, { manager: true });
  await f.page.goto(`${fixture.origin}/admin/users`);
  await f.page.locator("#admin-users-grid .ag-row").first().waitFor();
  assert.equal(
    await f.page.locator("#admin-users-delete-section").isVisible(),
    false,
  );
  const response = await f.context.request.delete(
    `${fixture.origin}/api/admin/users/44444444-4444-4444-8444-444444444444`,
    {
      headers: { Origin: fixture.origin },
      data: { confirmation_email: "delete-test@example.com" },
    },
  );
  assert.equal(response.status(), 403);
  await assertHealthy(f);
});
test("owner deletes only a suspended account after typed email confirmation", async (t) => {
  const f = await pageFixture(t, { admin: true });
  await f.page.goto(`${fixture.origin}/admin/users`);
  await f.page.locator("#admin-users-grid .ag-row").first().waitFor();
  const row = f.page
    .locator("#admin-users-grid .ag-row")
    .filter({ hasText: "delete-test@example.com" });
  await row.click();
  const start = f.page.locator("#admin-users-delete");
  await start.click();
  const modal = f.page.locator("#admin-users-delete-modal");
  await modal.waitFor();
  const confirm = f.page.locator("#admin-users-delete-confirm");
  const email = f.page.locator("#admin-users-delete-confirmation");
  assert.equal(await confirm.isDisabled(), true);
  await email.fill("wrong@example.com");
  assert.equal(await confirm.isDisabled(), true);
  await f.page.locator("#admin-users-delete-cancel").focus();
  await f.page.locator("#admin-users-delete-cancel").press("Enter");
  await modal.waitFor({ state: "hidden" });
  assert.equal(await row.count(), 1);
  await start.click();
  await modal.waitFor();
  assert.equal(await email.inputValue(), "");
  await email.fill("delete-test@example.com");
  await f.page.waitForFunction(
    () => !document.getElementById("admin-users-delete-confirm").disabled,
  );
  await f.page.clock.install();
  await confirm.focus();
  await confirm.press("Enter");
  await f.page.getByText("Account deleted.", { exact: true }).waitFor();
  await row.waitFor({ state: "detached" });
  await f.page.waitForFunction(
    () =>
      document
        .getElementById("admin-users-action-message")
        .getBoundingClientRect().top < innerHeight,
  );
  await f.page
    .locator("#admin-users-grid .ag-row")
    .filter({ hasText: "admin@example.com" })
    .click();
  assert.equal(await start.isDisabled(), true);
  await f.page.clock.runFor(5100);
  await f.page
    .getByText("Account deleted.", { exact: true })
    .waitFor({ state: "hidden" });
  await assertHealthy(f);
});

test("password recovery uses built bundle and matching passwords under CSP", async (t) => {
  const { page, context, requests } = await pageFixture(t);
  await page.goto(`${fixture.origin}/login`);
  await page.getByRole("link", { name: "Forgot password?" }).click();
  await page.locator("#auth-email").fill("test@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await page.getByText("If an account exists", { exact: false }).waitFor();
  assert.equal(
    requests.some(({ url }) => url.startsWith(`${mockOrigin}/auth/v1/recover`)),
    true,
  );
  await page.goto(
    `${fixture.origin}/reset-password?code=synthetic-recovery-code`,
  );
  await page.locator("#auth-password").waitFor({ state: "visible" });
  assert.equal(page.url(), `${fixture.origin}/reset-password`);
  await page.locator("#auth-password").fill("new-long-password");
  await page.getByRole("button", { name: "Show password" }).click();
  assert.equal(
    await page.locator("#auth-password").getAttribute("type"),
    "text",
  );
  await page.locator("#auth-confirm-password").fill("different-password");
  await page.getByRole("button", { name: "Save new password" }).click();
  await page.getByText("Passwords must match.", { exact: true }).waitFor();
  await page.locator("#auth-confirm-password").fill("new-long-password");
  await page.getByRole("button", { name: "Save new password" }).click();
  await page
    .getByText("Password updated. Sign in with your new password.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    requests.some(
      ({ url, method }) =>
        url === `${fixture.origin}/auth/session` && method === "POST",
    ),
    false,
  );
  assert.equal(
    (await context.cookies()).some(({ name }) => name === "qe_access_token"),
    false,
  );
  assert.deepEqual(await page.evaluate(() => window.cspViolations), []);
});

test("five wrong passwords lock sign-in across browser contexts while reset remains available", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(`${fixture.origin}/login`);
  await f.page.locator("#auth-email").fill("lockout@example.com");
  for (let i = 0; i < 5; i++) {
    await f.page.locator("#auth-password").fill("incorrect-password");
    const response = f.page.waitForResponse(
      (r) => r.url() === `${fixture.origin}/auth/password`,
    );
    await f.page.locator('#auth-form button[type="submit"]').click();
    assert.equal((await response).status(), i === 4 ? 423 : 401);
    await f.page.locator('#auth-form button[type="submit"]:enabled').waitFor();
  }
  await f.page.getByText(/Try again in 15 minute/).waitFor();
  assert.equal(
    f.requests.some((r) => r.url.includes("grant_type=password")),
    false,
  );
  const other = await pageFixture(t);
  await other.page.goto(`${fixture.origin}/login`);
  await other.page.locator("#auth-email").fill("LOCKOUT@example.com");
  await other.page.locator("#auth-password").fill("synthetic-password");
  await other.page.locator('#auth-form button[type="submit"]').click();
  await other.page.getByText(/Try again in 15 minute/).waitFor();
  await other.page.getByRole("link", { name: "Forgot password?" }).click();
  await other.page
    .getByRole("button", { name: "Send reset link" })
    .waitFor({ state: "visible" });
  assert.equal(
    (await other.context.cookies()).some((c) => c.name === "qe_access_token"),
    false,
  );
  await assertHealthy(other);
});

test("recovery stays bound to its account when another tab changes the normal session", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(`${fixture.origin}/forgot-password`);
  await f.page.locator("#auth-email").fill("test@example.com");
  await f.page.getByRole("button", { name: "Send reset link" }).click();
  await f.page.getByText("If an account exists", { exact: false }).waitFor();
  await f.page.goto(
    `${fixture.origin}/reset-password?code=synthetic-recovery-code`,
  );
  await f.page.locator("#auth-password").waitFor({ state: "visible" });
  const other = await f.context.newPage();
  await other.goto(`${fixture.origin}/login`);
  const differentSession = session(true);
  await other.evaluate(
    ({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
    { key: storageKey, value: differentSession },
  );
  await f.page.locator("#auth-password").fill("new-long-password");
  await f.page.locator("#auth-confirm-password").fill("new-long-password");
  const update = f.page.waitForRequest(
    (r) => r.url() === `${mockOrigin}/auth/v1/user` && r.method() === "PUT",
  );
  await f.page.getByRole("button", { name: "Save new password" }).click();
  assert.equal(
    (await update).headers().authorization,
    `Bearer ${fixture.token}`,
  );
  await f.page
    .getByText("Password updated. Sign in with your new password.", {
      exact: true,
    })
    .waitFor();
  const stored = await other.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)),
    storageKey,
  );
  assert.equal(
    stored,
    null,
    "the browser requires a fresh sign-in after recovery",
  );
  await assertHealthy(f);
});

test("keyboard focus on Play does not restart the slideshow without activation", async (t) => {
  const f = await pageFixture(t);
  await f.page.clock.install();
  await f.page.goto(fixture.origin);
  const selector = f.page.locator('.auth-carousel-tabs [data-slide="0"]');
  const rotation = f.page.locator('[data-carousel="rotation"]');
  await selector.focus();
  await rotation.focus();
  await f.page.clock.runFor(100);
  assert.equal((await rotation.textContent()).trim(), "Play");
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    false,
  );
  await rotation.press("Enter");
  await f.page.clock.runFor(6100);
  assert.equal(
    await f.page.locator("#auth-slide-analytics").evaluate((el) => el.hidden),
    true,
  );
  await assertHealthy(f);
});

test("callback fragment sessions cannot sign the browser into an injected account", async (t) => {
  const f = await pageFixture(t);
  await f.page.goto(
    `${fixture.origin}/auth/callback#access_token=untrusted&refresh_token=untrusted`,
  );
  await f.page.getByText(/unsupported sign-in format/).waitFor();
  assert.equal(new URL(f.page.url()).hash, "");
  assert.equal(
    f.requests.some(
      (r) => r.url === `${fixture.origin}/auth/session` && r.method === "POST",
    ),
    false,
  );
  assert.equal(
    (await f.context.cookies()).some((c) => c.name === "qe_access_token"),
    false,
  );
});
