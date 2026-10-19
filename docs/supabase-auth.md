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

The app loads root `.env` without overriding runtime environment variables.
Any account in the configured Supabase project with a verified email can sign in
immediately. No manual approval or environment email list is required. Legacy
`AUTH_ALLOWED_EMAILS` values are ignored and can be removed. All verified users
have the existing dashboard capabilities.

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
Optional build-time public variables are
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
before any Dash request hooks or data callbacks. The access token
cookie is HttpOnly and SameSite=Lax, and Secure except on explicitly configured
HTTP localhost origins. Refresh tokens remain managed by Supabase JS; no token
is stored in `dcc.Store`. Mutations require the exact configured Origin.

`/login`, `/signup`, `/auth/callback`, `/auth/config`, the required auth assets,
and minimal `/healthz` are public. Data endpoints return 401/403 for rejected
sessions and 503 for configuration/service failures. Responses are private and
not cacheable. `/` redirects verified users to `/dashboard`.

The browser waits for session synchronization before Dash requests and hides the
shell during initialization or session loss. Sign-out clears the server cookie
and local Supabase session; Supabase events synchronize other tabs. Outages and
expired callbacks display recovery instructions rather than an indefinite loader.

Public auth page and configuration reads do not consume the login attempt budget.
The session bridge limits rejected POST attempts to ten per minute per remote
address; successful verification and logout do not consume that budget. The
browser shares synchronization results for repeated events with the same access
token, including rejected results. A refreshed token or an explicit sign-in
attempt triggers a new synchronization. Every protected request still verifies
the token and confirmed email with Supabase.

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

Anonymous GET/HEAD requests to `/` render the product showcase without starting Supabase or loading dashboard data. A verified session at `/` still redirects to `/dashboard`; stale, denied, or unavailable sessions can still view the public landing page. `/login` and `/signup` are dedicated authentication pages, linked from the landing page header. Protected dashboard routes, callbacks, and exports retain their existing authorization requirements.

`npm run build:auth` builds the authentication bundle and the separate, public `showcase.bundle.js` slideshow. Both are excluded from Dash auto-injection and are loaded only by their respective templates. Docker copies both generated bundles from its Node build stage.

### Confirmation-link recovery

PKCE confirmation links must be opened using the same browser and origin where
signup began; `localhost` and `127.0.0.1` have separate browser storage. The
callback rejects token-bearing URL fragments. Sign-in links must use the
browser-bound PKCE code exchange, followed by server verification of the access
token before dashboard access is allowed.
A refreshed callback resumes an existing session. A callback with no code or
session displays sign-in guidance, while expired/used links display a specific
recovery message. If the email is already verified, sign in at `/login` using
the existing account. No new registration or manual approval is needed.

## Administrator user management

Verified users continue to sign in without an email allowlist. The admin directory
at `/admin/users` additionally requires `app_metadata.qe_role = "admin"`, obtained
from Supabase Auth on each protected request. User-editable `user_metadata`,
client stores, and unverified JWT claims never grant administrator access.

Add `SUPABASE_SERVICE_ROLE_KEY` to the server environment or the worktree's local
`.env`. Use the service-role key from the same Supabase project as the public
URL and anon key. This credential must never enter browser bundles, public
configuration, source control, or chat. With no key, management fails closed
with a setup message; normal verified-user sign-in continues to work.

Bootstrap the requested initial administrator only after its email is verified:

```sh
uv run python Scripts/bootstrap_admin.py --email datanerdbytes@gmail.com
uv run python Scripts/bootstrap_admin.py --email datanerdbytes@gmail.com --apply
```

The first command checks the account without changing it. The second assigns
`qe_role: admin` and `qe_owner: true` through the server-only Supabase Admin API.
This command is never run automatically at startup. The owner is protected from
suspension or demotion through the page, ensuring at least one administrator
remains. Changing the protected owner requires a separate operator procedure.

Administrators can view paginated accounts, suspend/restore members, and grant
or revoke other administrator roles. Grants require a verified, active account.
Self-changes and owner changes are rejected on the server. An administrator must
be demoted to member before suspension. Password viewing, manual email verification, and confirmation-email sending are not exposed.

Suspension sets both the Supabase ban and a server-managed `qe_suspended` flag.
Every protected app request revalidates this flag with Supabase, so existing
sessions are blocked as well as future logins. Admin role changes likewise apply
on the next request. Mutations require the configured exact Origin and explicit
confirmation in the interface. HTTP APIs and Dash callbacks independently enforce
admin access; hiding navigation is only a convenience.

The directory reads at most 25 accounts per request. Column filters apply to
that directory page, with grid pagination showing ten accounts at a time. Only
account ID, email, role, verification/access states, and account timestamps are
sent to the browser. No complete Auth records, token data, identities, or private
metadata are returned. Times are labeled UTC. Supabase is the source of truth;
user records are never copied into the warehouse or a shared analytics cache.

### Delete account (owner only)

The protected owner can permanently delete a suspended member after typing that
account's email in a separate confirmation dialog. The server revalidates the
actor's owner role, target identity, current suspension, and matching email at
confirmation time. Self-deletion, owner deletion, and administrator deletion are
blocked; revoke the admin role and suspend the account first. Other administrators
cannot use deletion through the UI, HTTP API, or forged Dash callbacks.

The server uses Supabase Auth's hard-delete operation (`should_soft_delete: false`).
Supabase controls existing foreign-key cascades; related records may also be
removed if the database defines such cascades. Storage ownership and foreign-key
restrictions can prevent deletion. The app does not automatically delete files,
change constraints, or clean up related records. It reports provider failures
without exposing internal details. A network timeout leaves the outcome uncertain;
refresh the directory before any deliberate retry. There is no automatic replay.

Deleting an account removes its sign-in identity, not a ban on its email: the same
email can register again under open signup. Application requests still validate
users with Supabase on every request. Other services accepting stateless tokens
need their own revocation checks; this page does not claim to invalidate every
already-issued JWT. No BigQuery data is deleted by this feature.


### Password recovery

The sign-in page’s **Forgot password?** link opens `/forgot-password`. Supabase sends a recovery email with a PKCE redirect to `<AUTH_APP_ORIGIN>/reset-password`. Add this exact URL under **Authentication → URL Configuration → Redirect URLs** for each deployed origin (including `http://127.0.0.1:8050/reset-password` for local development). Keep the recovery email template’s Supabase verification link; a direct link to the application cannot exchange the recovery code.

Open the latest email link in the same browser and origin used to request it. The reset page requires a valid recovery PKCE exchange, never imports fragment tokens or uses a cached session, and asks for a matching new password of at least eight characters. Provider password policies still apply. A consumed, expired, or cross-browser link requires a new request; refreshing the reset form also requires a new link. On success the app requests global Supabase sign-out, clears its access cookie, and asks the user to sign in again. Existing access tokens remain valid until their normal expiry, as defined by Supabase session behavior. Resetting a password does not restore suspended workspace access.

Requests show a generic confirmation without revealing whether an email exists. Supabase email delivery, rate limits, and SMTP configuration apply. Offline tests mock email delivery and password changes; they do not send real recovery messages.

### Temporary password lockout (Supabase Free)

The optional lockout blocks workspace access after **five incorrect passwords within a 15-minute window**, for **15 minutes from the fifth failure**. It expires automatically. A successful password sign-in before the threshold clears the failure count. A real password change (including completing password recovery) clears the lock through a database trigger; requesting a recovery email does not. Administrative suspension remains independent and cannot be cleared by password recovery.

When enabled, password sign-in goes through `/auth/password` on the Flask server. Supabase still verifies the password using the public project key. Only Supabase's explicit `invalid_credentials` response counts; timeouts, configuration failures, unconfirmed-email errors and provider throttling do not. The browser imports the returned session using Supabase JS, then uses the existing verified `/auth/session` bridge. Passwords are not stored or logged by the gateway. All gateway responses are private/no-store and mutations require the exact app Origin.

Attempt counts live in `public.qe_password_attempts`. A service-role-only database function takes a row lock and reserves a 30-second attempt lease per normalized email. Parallel submissions cannot race the counter. Abandoned leases expire, and old responses cannot finalize a newer attempt. Reads of the current lock run on every protected workspace request using the remotely verified user's email, so a token obtained directly from Supabase cannot bypass an active workspace lock. Storage or verification failures deny access; there is no fallback to browser counters or process memory.

**Free-plan scope:** the app can count only incorrect passwords sent through its gateway. Direct calls to Supabase's password endpoint remain subject to Supabase's own limits and cannot be included in this counter on Free. The workspace still denies access while its own lock is active. Supabase's Password Verification Attempt hook, which could count attempts at the provider itself, requires Teams or Enterprise: [Auth Hooks availability](https://supabase.com/docs/guides/auth/auth-hooks). This feature does not claim to disable the provider's password endpoint, OAuth, or issued tokens globally.

To activate:

1. Apply `supabase/migrations/202610190001_password_lockout.sql` in the matching project's Supabase SQL Editor. It creates one private-to-clients table, one service-role-only RPC, and a trigger on password-hash changes in `auth.users`. Review and apply it once. The app does not automatically apply migrations.
2. Keep `SUPABASE_SERVICE_ROLE_KEY` configured only on the server. Add `AUTH_PASSWORD_LOCKOUT_ENABLED=true` to the worktree's ignored `.env` or the deployed server environment, and restart the server. Refresh existing browser tabs to load the new runtime configuration. Browser configuration exposes only the enablement boolean, public URL, and anon key.
3. With a disposable test account, verify four incorrect passwords give the generic credential error, the fifth gives a temporary-lock message, and another browser cannot sign into the workspace until expiry or a completed password reset. No real users are modified by the offline tests.

The flag defaults to `false` so an unapplied migration cannot unexpectedly break existing sign-in. A deployment is **not protected by this feature until the migration is applied and the flag enabled**. Once enabled, a missing key, missing RPC, or unavailable database fails closed. Turning the flag off is an explicit rollback of lockout enforcement, not an automatic outage fallback. Old browser clients may still call Supabase directly, subject to the Free-plan scope above.

Counters contain normalized email addresses, including invalid sign-in targets, and are inaccessible to `anon`/`authenticated` through RLS and revoked function/table grants. An operator can periodically remove inactive rows older than 30 days (`updated_at`) after ensuring any lock and lease have expired; no scheduled hosted cleanup is installed. The existing IP request limiter is an additional per-process brake, not the source of shared account-lockout enforcement.

Verification: Python gateway/route tests and browser tests mock provider/storage I/O. `tests/password-lockout-sql.test.mjs` executes the actual migration against isolated in-memory PostgreSQL using PGlite, including permission checks, fifth-failure lockout, expiry, successful-password reset, lease races, and the password-change trigger. Run it with `QE_PGLITE_MODULE=/path/to/pglite/dist/index.js node --test tests/password-lockout-sql.test.mjs`; The pinned PGlite development dependency runs in the standard `npm run test:auth` suite and is not a production runtime dependency. The fixture creates only synthetic local roles and accounts and never connects to Supabase.


### Review fixes and deletion safety

Password-reset sessions use isolated in-memory storage and a unique Supabase storage key/channel. They share only the requesting browser's one-time PKCE verifier, not its normal session. Signing into another account in another tab cannot change which account receives the password update. After a successful reset, the normal browser session is also signed out locally through Supabase JS so a cached access token cannot immediately sign the browser back in. The form also checks the recovered user before updating and closes if its recovery session changes or ends. Known unconfirmed-email and suspended-user errors from the password gateway remain actionable authentication errors and never increment the wrong-password count.

The landing slideshow pauses when keyboard focus enters its controls, including Play. Only activating Play can resume playback while that button is focused. The original six-second slide interval and slide-transition duration are preserved.

Before account deletion is available, apply `supabase/migrations/202610190002_account_deletion_guard.sql` to the matching project. The app checks the installed trigger's readiness before calling Supabase's Admin delete API and refuses deletion if the guard is missing or disabled. The trigger checks the current `auth.users` row inside the delete transaction and rejects active members, administrators, and the protected owner. Therefore a restoration or promotion committed after the confirmation snapshot cannot turn into an unsafe deletion. A concurrent change that starts after deletion has acquired the row lock waits and cannot update the deleted row. No process-local lock or expiring network lease is used to protect deletion.

This migration adds a deletion restriction to `auth.users`, so it also applies to direct hard deletions from Supabase tools; other SQL integrity constraints and Storage ownership checks still apply. It does not delete any existing accounts when installed. Readiness does not depend on the optional password-lockout enablement flag. The app does not automatically apply either migration. SQL regression tests execute both migrations only against synthetic in-memory PostgreSQL.


Apply `supabase/migrations/202610190003_administrator_access_guard.sql` before deploying administrator access management. It rejects a combined administrator role and active suspension inside the database transaction, including concurrent promotion/suspension requests. Existing inconsistent records are not modified by installation; they can be repaired by revoking the role or restoring access. Install all numbered migrations in order when provisioning a new project.
