# Content Security Policy Implementation

## Overview

This document describes the Content Security Policy (CSP) implementation for the Quantum Echo Analytics Dashboard. The CSP is enforced on all HTML responses (auth pages, landing page, and dashboard routes) to mitigate XSS and script injection risks.

## CSP Policy

The following CSP header is applied to all `text/html` responses:

```http
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https://cdn.jsdelivr.net https://unpkg.com;
  style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net;
  font-src 'self' https://fonts.gstatic.com;
  connect-src 'self' https://*.supabase.co https://*.supabase.net;
  img-src 'self' data:;
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
```

### Directive Breakdown

| Directive | Value | Purpose |
|-----------|-------|---------|
| `default-src` | `'self'` | Fallback for all other directives |
| `script-src` | `'self' 'nonce-{nonce}' 'strict-dynamic' https://cdn.jsdelivr.net https://unpkg.com` | Allow scripts from same origin, nonce'd inline scripts, strict-dynamic for trusted scripts, and Dash CDN |
| `style-src` | `'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net` | Allow styles from same origin, nonce'd inline styles, Google Fonts CSS, and Dash CDN |
| `font-src` | `'self' https://fonts.gstatic.com` | Allow fonts from same origin and Google Fonts static files |
| `connect-src` | `'self' https://*.supabase.co https://*.supabase.net` | Allow fetch/XHR to same origin and Supabase for auth |
| `img-src` | `'self' data:` | Allow images from same origin and data URIs |
| `frame-ancestors` | `'none'` | Prevent framing/clickjacking |
| `base-uri` | `'self'` | Restrict `<base>` tag to same origin |
| `form-action` | `'self'` | Restrict form submissions to same origin |

## Nonce Generation

- **Algorithm**: `secrets.token_urlsafe(16)` — cryptographically unpredictable, 16 bytes (22 chars URL-safe base64)
- **Scope**: Per-request, generated in Flask's `before_request` handler
- **Storage**: Stored in `g.csp_nonce` for access in templates and `after_request`
- **Freshness**: Unique nonce per response; never reused or derived from user input

## Template Integration

### Auth Pages (`auth.html`)

```html
<!-- Meta tag for JavaScript access -->
<meta name="csp-nonce" content="{{ csp_nonce }}">

<!-- Inline timeout script with nonce -->
<script nonce="{{ csp_nonce }}">
  setTimeout(function () { ... }, 10000);
</script>

<!-- External auth bundle with nonce -->
<script nonce="{{ csp_nonce }}" defer src="/assets/auth.bundle.js"></script>
```

### Landing Page (`landing.html`)

```html
<meta name="csp-nonce" content="{{ csp_nonce }}">
<script nonce="{{ csp_nonce }}" defer src="/assets/showcase.bundle.js"></script>
```

### Dashboard (`app.py` — Dash index string)

```python
DASH_INDEX_STRING = """<!DOCTYPE html>
<html>
    <head>
        <meta name="csp-nonce" content="{{ csp_nonce }}">
        <script nonce="{{ csp_nonce }}" defer src="/assets/auth.bundle.js"></script>
        {%metas%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""
```

## Flask Implementation

### `my-dash-app/auth.py`

1. **Nonce Generation** (`_generate_nonce`):
   ```python
   def _generate_nonce() -> str:
       return secrets.token_urlsafe(16)
   ```

2. **Context Processor** (injects nonce into templates):
   ```python
   @server.context_processor
   def inject_csp_nonce():
       return {"csp_nonce": getattr(g, "csp_nonce", None)}
   ```

3. **Before Request** (generates fresh nonce):
   ```python
   @server.before_request
   def protect():
       g.csp_nonce = _generate_nonce()
       # ... auth logic
   ```

4. **After Request** (applies CSP header):
   ```python
   @server.after_request
   def private(response):
       # ... existing security headers
       if response.content_type and response.content_type.startswith("text/html"):
           nonce = getattr(g, "csp_nonce", None)
           if nonce:
               csp_parts = [
                   "default-src 'self'",
                   f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' https://cdn.jsdelivr.net https://unpkg.com",
                   f"style-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com https://cdn.jsdelivr.net",
                   "font-src 'self' https://fonts.gstatic.com",
                   "connect-src 'self' https://*.supabase.co https://*.supabase.net",
                   "img-src 'self' data:",
                   "frame-ancestors 'none'",
                   "base-uri 'self'",
                   "form-action 'self'",
               ]
               response.headers["Content-Security-Policy"] = "; ".join(csp_parts)
       return response
   ```

### `my-dash-app/app.py`

- Context processor for Dash templates:
  ```python
  @app.context_processor
  def inject_csp_nonce():
      return {"csp_nonce": getattr(g, "csp_nonce", None)}
  ```

- Custom `index_string` with nonce for Dash's auto-injected scripts

## Testing

### Python Tests (`tests/test_csp.py`)

18 tests verify:
- CSP header presence on all auth routes (`/login`, `/signup`, `/auth/callback`, `/`)
- Required directives present
- Allowed external origins (Google Fonts, Supabase, Dash CDN)
- Nonce in HTML matches CSP header
- Nonce uniqueness per request
- No `unsafe-inline` or `unsafe-eval`
- Static assets (`/assets/*`) do not receive CSP header
- Dashboard routes (when authenticated) have CSP

Run with:
```bash
.venv/bin/python -B -m pytest tests/test_csp.py -v
```

### Browser Tests (`tests/csp-browser.test.mjs`)

Browser-based verification using JSDOM to confirm:
- Inline scripts without nonce are blocked
- Nonce'd scripts execute correctly
- External scripts from allowed origins load
- External scripts from disallowed origins are blocked
- CSP violation reports would be generated (in report-only mode)

Run with:
```bash
npm run test:auth  # Includes CSP browser tests
```

## Route Coverage

| Route | CSP Enforced | Notes |
|-------|--------------|-------|
| `/login` | ✅ | Auth page with inline timeout script |
| `/signup` | ✅ | Auth page with inline timeout script |
| `/auth/callback` | ✅ | OAuth callback (may redirect) |
| `/` (landing) | ✅ | Public page with showcase bundle |
| `/dashboard` | ✅ | Protected dashboard (requires auth) |
| `/customers` | ✅ | Protected page (requires auth) |
| `/pipeline-health` | ✅ | Protected page (requires auth) |
| `/assets/*` | ❌ | Static assets — no CSP (cacheable) |
| `/auth/config` | ❌ | JSON API endpoint |
| `/auth/session` | ❌ | JSON API endpoint |
| `/healthz` | ❌ | Health check endpoint |

## Exceptions and Notes

### Dash Component CDN

Dash loads component scripts from `cdn.jsdelivr.net` and `unpkg.com`. These are explicitly allowed in `script-src` because:
- They are required for Dash's dynamic component loading
- They are served from trusted, versioned CDN URLs
- `strict-dynamic` allows trusted scripts to load further scripts

### Supabase Connections

Supabase authentication requires connections to:
- `https://*.supabase.co` — Main API endpoint
- `https://*.supabase.net` — Realtime/WebSocket endpoints

These are allowed in `connect-src` only (not in `script-src`).

### No `unsafe-inline` or `unsafe-eval`

The policy deliberately avoids:
- `'unsafe-inline'` — All inline scripts/styles must have a matching nonce
- `'unsafe-eval'` — Not needed by the application
- Wildcard hosts (`https:`) — All external origins are explicitly listed

## Deployment Notes

- The CSP is enforced in production (not report-only)
- Nonces are generated per-request — no caching of HTML with nonces
- `Cache-Control: private, no-store` prevents HTML caching
- `Vary: Cookie` ensures authenticated/unauthenticated responses are cached separately

## Rollback Procedure

If CSP breaks legitimate functionality:
1. Temporarily switch to report-only mode by changing header to `Content-Security-Policy-Report-Only`
2. Monitor violation reports
3. Adjust policy or fix application code
4. Re-enable enforcement

## Future Considerations

- Consider adding `script-src-attr` and `style-src-attr` for inline event handlers/styles if needed
- Evaluate `trusted-types` for DOM XSS protection
- Monitor Dash version upgrades for new CDN requirements
