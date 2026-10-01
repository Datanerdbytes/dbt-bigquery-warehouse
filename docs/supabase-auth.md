# Supabase authentication

Existing Supabase accounts are preserved. If you already confirmed your email,
open `/login` and sign in with that account; do not create a replacement account.

## Configuration

Set these variables in the root `.env` locally, and in Cloud Run's runtime
configuration for production:

- `NEXT_PUBLIC_SUPABASE_URL`: your existing Supabase project URL.
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: the public anon key, never a service-role key.
- `AUTH_APP_ORIGIN`: exact browser origin. Use `http://localhost:8050` locally
  and `https://dash-observability-app-1022429033383.us-central1.run.app` online.
- `AUTH_ALLOWED_EMAILS`: comma-separated exact verified email addresses.

The app loads root `.env` without overriding runtime environment variables.
An empty allowlist grants nobody access. Add or remove approved emails in the
server environment and restart/redeploy all instances for changes to take effect.
All approved users currently have the existing dashboard capabilities.

## Build and run

With Node 22+ and the existing Python environment:

```sh
npm ci
npm run build:auth
cd my-dash-app
../.venv/bin/python app.py
```

Use **localhost**, not `127.0.0.1`, when the configured origin is localhost.
The browser preserves Supabase's existing project-specific session storage.
The frontend reads only the public project URL and anon key from `/auth/config`;
it never receives the email allowlist. Optional build-time public variables are
supported, but leave them unset for runtime configuration in Docker and CI.

The Dockerfile builds the JS from source in a Node stage, then copies the bundle
into the Python image. No Supabase build secrets or Node runtime are needed in
production. `.dockerignore` excludes `.env`, virtual environments, and node_modules.
Commit the Python auth module, templates, CSS, frontend sources, package manifests,
build script, and Dockerfile together; deploying only the bundle breaks startup.
The existing tracked bundle is kept regenerated for local compatibility.

## Supabase settings

Keep Email confirmation enabled, and enable Google and GitHub with provider
credentials stored in Supabase. Add each app origin's `/auth/callback` URL to
Supabase's allowed redirect URLs. Google/GitHub provider apps use the Supabase
callback URL shown by the provider configuration, not the Dash callback URL.
For email PKCE links, use the browser where signup started. If the email was
confirmed but the callback cannot finish, return to `/login` and sign in.

## Security and behavior

Flask verifies each access token with Supabase Auth and checks confirmed email
and approval before any Dash request hooks or data callbacks. The access token
cookie is HttpOnly and SameSite=Lax, and Secure except on explicitly configured
HTTP localhost origins. Refresh tokens remain managed by Supabase JS; no token
is stored in `dcc.Store`. Mutations require the exact configured Origin.

`/login`, `/signup`, `/auth/callback`, `/auth/config`, the required auth assets,
and minimal `/healthz` are public. Data endpoints return 401/403 for rejected
sessions and 503 for configuration/service failures. Responses are private and
not cacheable. `/` redirects approved users to `/dashboard`.

The browser waits for session synchronization before Dash requests and hides the
shell during initialization or session loss. Sign-out clears the server cookie
and local Supabase session; Supabase events synchronize other tabs. Outages and
expired callbacks display recovery instructions rather than an indefinite loader.

## Offline validation

```sh
.venv/bin/python -B -m unittest discover -s tests -v
npm run test:auth
```

Tests mock Supabase and prohibit production BigQuery client construction in
regression tests. Actual account sign-in and OAuth provider consent require your
credentials and provider configuration; automated checks do not create accounts,
send confirmation emails, or query production analytics.

### Public product landing page

Anonymous GET/HEAD requests to `/` render the product showcase without starting Supabase or loading dashboard data. A verified, approved session at `/` still redirects to `/dashboard`; stale, denied, or unavailable sessions can still view the public landing page. `/login` and `/signup` are dedicated authentication pages, linked from the landing page header. Protected dashboard routes, callbacks, and exports retain their existing authorization requirements.

`npm run build:auth` builds the authentication bundle and the separate, public `showcase.bundle.js` slideshow. Both are excluded from Dash auto-injection and are loaded only by their respective templates. Docker copies both generated bundles from its Node build stage.
