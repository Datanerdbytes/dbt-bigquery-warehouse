# Content Security Policy for Flask and Dash

## Enforcement and scope

`install_auth` generates a fresh 128-bit random nonce in `before_request` and
sets an enforced `Content-Security-Policy` header in `after_request` for each
HTML response. It preserves the existing authentication order, exact-Origin
checks, cookies, private/no-store caching, and authorization before data access.
Nonces come from `secrets.token_urlsafe(16)`, never request input or configuration.

Login, signup, callback, public landing, authenticated Dash pages, HTML redirects,
and HTML errors receive CSP. JavaScript/CSS assets and JSON responses do not
receive a document policy; their loading is governed by the requesting HTML.
An asset URL returning an HTML error receives CSP like any other HTML response.

## Policy

```text
default-src 'self';
script-src 'self' 'nonce-<fresh-response-nonce>' 'strict-dynamic';
style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net;
font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net;
connect-src 'self' https://<configured-Supabase-origin>;
img-src 'self' data:;
object-src 'none';
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

The Supabase origin is derived from `NEXT_PUBLIC_SUPABASE_URL`. Paths do not
broaden the origin. Invalid/unsafe source expressions are omitted, leaving only
`'self'`; there are no wildcard Supabase hosts or unrestricted HTTPS sources.
Authentication configuration errors continue to fail closed.

### Trusted scripts and dynamic chunks

- Jinja's `{{ csp_nonce }}` authorizes the auth template's timeout script and
  auth bundle, and the landing template's showcase bundle.
- Dash's index template uses `{%csp_nonce%}` for the manually included auth bundle.
  Dash does not run Jinja context processors on its index, so an
  `interpolate_index` override replaces that placeholder.
- The override adds the response nonce to **only Dash-generated `config`,
  `scripts`, and `renderer` fragments**. This covers component scripts, registered
  clientside code (including Dash Pages), and the inline `DashRenderer` bootstrap.
  It never stamps nonces onto the whole response or untrusted `app_entry` content.
- `strict-dynamic` permits chunks loaded by trusted scripts, including Dash's
  asynchronous graph/Plotly modules. Parser-inserted scripts need the nonce in
  modern CSP3 browsers even if their URL is same-origin. `'self'` supplies a CSP2
  fallback for local script files. Browsers without nonce support cannot run the
  inline Dash bootstrap; they are not certified by these Chromium tests.
- JavaScript `unsafe-inline`, `unsafe-eval`, inline event handlers, and broad
  script host lists are not enabled. CSP is a defense against injection; it does
  not establish that a trusted bundle's own code is safe.

### Explicit CSS compatibility exception

The policy permits inline **styles**, including runtime `<style>` elements and
style attributes used by installed Dash components, React, and Plotly. A script
nonce alone cannot authorize those styles. A nonce-only style policy blocks
component-injected CSS and breaks styling. A local Chromium probe observed 59
`style-src-elem` violations with the nonce-only style policy, including
`dash_renderer` and `dash_core_components` runtime styles. This is a documented CSS exception,
not a JavaScript exception or a claim that every resource uses a strict nonce.
Bootstrap/theme/icon styles use jsDelivr; Google Fonts use the two font origins.
A future component upgrade can revisit this exception with equivalent browser
verification. `object-src 'none'` also blocks plugin/object content.

## Build and test setup

Python uses the repository's Python 3.12 environment. `playwright` is pinned as a
development-only npm dependency and its matching Chromium must be installed:

```bash
npm ci
npx playwright install chromium
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```

Use an isolated dependency directory/environment when dependencies in a worktree
are shared with another agent. The repository currently tracks `node_modules`;
never stage its unrelated installation changes. No shared Python environment
synchronization is needed for this task.

The existing esbuild script emits escaped strings instead of template literals.
This preserves dependency string values containing tabs/newlines when repository
whitespace hooks run and makes repeated builds stable. Both tracked bundles are
built from source; neither is hand-edited. CI installs matching Chromium with
`npx playwright install --with-deps chromium` before the browser tests. The
secret-scanner baseline adds only the verified public literal `password` exposed
by the changed bundle formatting; scanning remains enabled.

### What the verification proves

- `tests/test_csp.py` checks Flask headers, response nonce freshness, policy
  sources, HTML error handling, and the **actual Dash** index on all page routes.
  Every generated script has the matching response nonce, and an untrusted
  `app_entry` script does not receive one. JSON/static responses and unauthorized
  data requests retain their existing behavior.
- `tests/csp-browser.test.mjs` launches headless Chromium against the real local
  Flask/Dash app using the built auth/showcase bundles. Its six test groups cover
  browser-enforced missing/wrong nonce rejection, blocked `eval`, allowed nonce
  execution, freshness, password login, signup confirmation, Dash bootstrap and
  dynamic graph chunks, Plotly rendering, callbacks, page navigation, refresh,
  sign-out, OAuth launch/exchange, and canceled OAuth recovery.
- Injection fixtures are inserted into the **HTTP HTML response**. DevTools
  evaluation has privileged behavior and cannot itself prove CSP enforcement.
  Tests assert actual `securitypolicyviolation` events with `enforce` disposition.
- `tests/csp_test_server.py` binds only an ephemeral loopback port. It disables
  dotenv loading, blocks BigQuery client construction, substitutes synthetic
  DataFrames and Supabase user-verification responses, and uses an isolated
  in-memory cache. Rate limiting is disabled only in this browser fixture so
  independent test contexts do not exhaust a shared limit; production limiter
  behavior remains exercised by the existing Python auth tests.
- Browser requests to Supabase are intercepted with fake identities/tokens.
  External CSS/fonts are fulfilled locally, and unexpected external requests
  are aborted. No production data, real credentials, or real accounts are used.
- Existing `auth-browser.test.mjs` retains detailed JSDOM auth-flow tests. JSDOM
  does **not** enforce CSP; those tests are not described as enforcement evidence.

These tests certify local Chromium behavior with synthetic data. They do not
certify live OAuth providers, production CDN content, hosted CI, or a deployment.
Re-run the gate after integration or dependency changes. The `interpolate_index`
fragment contract must be reviewed when Dash changes (tested here with 4.4.1).

## Release and rollback

CSP can affect client behavior, so review the tested worker commit and verify the
combined integration candidate before release. This task does not change the
Docker installation strategy or authorize deployment. The separate Docker
lock-based installation concern remains outside its scope.

Revert the CSP worker commits through the normal reviewed workflow if required;
retain authentication/authorization and other phase-1 security fixes. Do not
replace CSP with broad JavaScript exceptions as an emergency compatibility fix.

## References

- [MDN script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)
- [MDN style-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src)
- [Flask security headers](https://flask.palletsprojects.com/en/stable/web-security/)
