import { getSupabaseClient } from "./supabase-client.js";
window.qeAuthStarted = true;
const nativeFetch = window.fetch.bind(window);
const mode = document.documentElement.dataset.authPage;
const isAuthPage = Boolean(mode);
const isRecoveryPage = mode === "forgot" || mode === "reset";
let recoveryReady = false;
let recoveryUserId;
function invalidateRecovery() {
  recoveryReady = false;
  element("auth-content").hidden = true;
  element("auth-back").hidden = false;
  message(
    "Your recovery session changed or ended. Request a new reset link to continue.",
  );
}
const element = (id) => document.getElementById(id);
let client,
  initialized = false,
  signingOut = false;
let synchronization = Promise.resolve(false);
let synchronizationToken;
let resolveReady;
const ready = new Promise((resolve) => {
  resolveReady = resolve;
});
const messages = {
  account_locked:
    "Too many incorrect passwords. Password sign-in is temporarily locked. Try again in 15 minutes or reset your password.",
  invalid_credentials: "Invalid email or password.",
  lockout_not_configured:
    "Password sign-in is being configured. Contact your administrator.",
  attempt_in_progress:
    "Another sign-in attempt is being processed. Wait a moment and retry.",
  attempt_expired: "This sign-in attempt expired. Please try again.",
  rate_limited: "Too many authentication requests. Wait a minute and retry.",
  account_suspended:
    "Your workspace access has been suspended. Contact an administrator.",
  email_confirmation_required: "Confirm your email address before signing in.",
  auth_not_configured:
    "Authentication is not configured. Contact your administrator.",
  auth_unavailable:
    "Authentication is temporarily unavailable. Reload the page to retry.",
  session_expired: "Your session has expired. Please sign in again.",
  session_required: "Please sign in to continue.",
  origin_rejected:
    "This address does not match the configured application URL. Open the configured URL or contact your administrator.",
};
function conceal() {
  delete document.documentElement.dataset.authReady;
}
function message(text, tone = "error") {
  const target = element("auth-message") || element("auth-session-loading");
  if (target) {
    target.textContent = text;
    target.hidden = false;
    target.dataset.tone = tone;
    target.focus();
  }
  if (element("auth-loading")) element("auth-loading").hidden = true;
}
function pending(value) {
  document
    .querySelectorAll("#auth-content button, #auth-content input")
    .forEach((el) => {
      el.disabled = value;
    });
  element("auth-form")?.setAttribute("aria-busy", String(value));
}
function showForm() {
  element("auth-loading").hidden = true;
  element("auth-content").hidden = false;
}
async function bridge(method, session) {
  const response = await nativeFetch("/auth/session", {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...(session
      ? { body: JSON.stringify({ access_token: session.access_token }) }
      : {}),
    signal: AbortSignal.timeout(12000),
  });
  const body = await response.json();
  return { response, body };
}
async function syncSession(session) {
  if (signingOut) return false;
  const { response, body } = await bridge(session ? "POST" : "DELETE", session);
  if (!response.ok) {
    conceal();
    if (!isAuthPage && [401, 403].includes(response.status)) {
      location.replace("/login");
      return false;
    }
    if (
      isAuthPage &&
      response.status === 403 &&
      body.error !== "origin_rejected"
    ) {
      element("auth-content").hidden = true;
      element("auth-signout").hidden = false;
      if (body.error === "account_locked") {
        element("auth-back").href = "/forgot-password";
        element("auth-back").textContent = "Reset your password";
        element("auth-back").hidden = false;
      }
      message(messages[body.error] || "Access is unavailable.", "info");
      return false;
    }
    throw new Error(
      messages[body.error] || "Unable to verify your session. Reload to retry.",
    );
  }
  if (!session) {
    conceal();
    if (!isAuthPage) location.replace("/login");
    else if (mode === "login" || mode === "signup") showForm();
    return false;
  }
  if (isAuthPage) location.replace("/dashboard");
  else document.documentElement.dataset.authReady = "true";
  return true;
}
function synchronize(session, retry = false) {
  const token = session?.access_token ?? null;
  // Supabase can repeat SIGNED_IN on tab focus and alongside form submission.
  // Share the queued result, including failures, instead of replaying mutations.
  if (!retry && token === synchronizationToken) return synchronization;
  synchronizationToken = token;
  synchronization = synchronization
    .catch(() => false)
    .then(() => syncSession(session));
  return synchronization;
}
async function clearRecoveryBrowserSession() {
  // The recovery client has isolated storage. Clear the normal browser session
  // through Supabase JS as well, so an old access token cannot auto-sign in.
  const browserClient = await getSupabaseClient(nativeFetch);
  const { error } = await browserClient.auth.signOut({ scope: "local" });
  if (error) throw error;
}
async function signOut() {
  signingOut = true;
  conceal();
  try {
    await synchronization.catch(() => {});
    const { response, body } = await bridge("DELETE");
    if (!response.ok)
      throw new Error(messages[body.error] || "Unable to sign out. Retry.");
    const { error } = await client.auth.signOut({
      scope: mode === "reset" ? "global" : "local",
    });
    if (error) throw error;
    if (mode === "reset") await clearRecoveryBrowserSession();
    location.replace("/login");
  } catch (error) {
    signingOut = false;
    message(error.message);
  }
}
// Only Dash data requests are gated; auth and static resources must never deadlock.
window.fetch = async (input, init) => {
  const url = new URL(
    input instanceof Request ? input.url : input,
    location.href,
  );
  const protectedRequest =
    url.origin === location.origin && url.pathname.startsWith("/_dash-");
  if (protectedRequest) {
    if (!(await ready) || signingOut || !(await synchronization))
      throw new Error("Authentication required");
  }
  const response = await nativeFetch(input, init);
  if (protectedRequest && [401, 403, 503].includes(response.status)) {
    conceal();
    if (response.status === 503) message(messages.auth_unavailable);
    else location.replace("/login");
  }
  return response;
};
// Local form controls must work even while authentication is initializing.
document.addEventListener("click", (event) => {
  const button = event.target.closest?.("#auth-show-password");
  if (!button || button.disabled) return;
  const input = element("auth-password");
  if (!input) return;
  const showing = input.type === "password";
  input.type = showing ? "text" : "password";
  button.textContent = showing ? "Hide" : "Show";
  button.setAttribute(
    "aria-label",
    showing ? "Hide password" : "Show password",
  );
  button.setAttribute("aria-pressed", String(showing));
});
function wireRecoveryForm() {
  element("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    element("auth-message").hidden = true;
    const email = element("auth-email");
    const password = element("auth-password");
    const confirmation = element("auth-confirm-password");
    const fields =
      mode === "forgot"
        ? [[email, email.validity.valid ? "" : "Enter a valid email address."]]
        : [
            [
              password,
              password.value.length >= 8 ? "" : "Use at least 8 characters.",
            ],
            [
              confirmation,
              confirmation.value === password.value
                ? ""
                : "Passwords must match.",
            ],
          ];
    let invalid;
    for (const [input, error] of fields) {
      element(`${input.id}-error`).textContent = error;
      input.setAttribute("aria-invalid", String(Boolean(error)));
      if (error && !invalid) invalid = input;
    }
    if (invalid) {
      invalid.focus();
      return;
    }
    pending(true);
    let updated = false;
    try {
      if (mode === "forgot") {
        const { error } = await client.auth.resetPasswordForEmail(
          email.value.trim(),
          {
            redirectTo: `${location.origin}/reset-password`,
          },
        );
        if (error) throw error;
        element("auth-content").hidden = true;
        element("auth-back").hidden = false;
        message(
          "If an account exists for that email, you’ll receive a password reset link. Open the latest link in this browser.",
          "info",
        );
      } else {
        if (!recoveryReady)
          throw new Error("Request a new password reset link to continue.");
        const current = await client.auth.getSession();
        if (
          !recoveryReady ||
          current.error ||
          current.data.session?.user?.id !== recoveryUserId
        ) {
          invalidateRecovery();
          return;
        }
        const { error } = await client.auth.updateUser({
          password: password.value,
        });
        if (error) throw error;
        updated = true;
        recoveryReady = false;
        password.value = "";
        confirmation.value = "";
        element("auth-content").hidden = true;
        // Revoke recovery and existing refresh sessions; require a fresh sign-in.
        const result = await client.auth.signOut({ scope: "global" });
        await clearRecoveryBrowserSession();
        const cleared = await bridge("DELETE");
        if (result.error || !cleared.response.ok)
          throw new Error(
            "Your password was updated, but sign-out could not finish. Use Sign out before signing in again.",
          );
        element("auth-back").href = "/login";
        element("auth-back").textContent = "Back to sign in";
        element("auth-back").hidden = false;
        message("Password updated. Sign in with your new password.", "info");
      }
    } catch (error) {
      if (updated) element("auth-signout").hidden = false;
      message(
        error.message ||
          "Unable to reset your password. Request a new link and retry.",
      );
    } finally {
      pending(false);
    }
  });
}
async function passwordSignIn(credentials) {
  if (!client.qePasswordLockoutEnabled)
    return client.auth.signInWithPassword(credentials);
  const response = await nativeFetch("/auth/password", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
    signal: AbortSignal.timeout(20000),
  });
  const body = await response.json();
  if (!response.ok) {
    const wait =
      body.error === "account_locked" && Number.isInteger(body.retry_after)
        ? `Too many incorrect passwords. Try again in ${Math.max(1, Math.ceil(body.retry_after / 60))} minute(s). You can still reset your password.`
        : messages[body.error] || "Unable to sign in. Please retry.";
    throw new Error(wait);
  }
  return client.auth.setSession({
    access_token: body.access_token,
    refresh_token: body.refresh_token,
  });
}
function wireForm() {
  document.querySelectorAll("[data-provider]").forEach((button) =>
    button.addEventListener("click", async () => {
      pending(true);
      try {
        const { error } = await client.auth.signInWithOAuth({
          provider: button.dataset.provider,
          options: { redirectTo: `${location.origin}/auth/callback` },
        });
        if (error) throw error;
      } catch (error) {
        message(error.message);
        pending(false);
      }
    }),
  );
  element("auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    element("auth-message").hidden = true;
    const email = element("auth-email"),
      password = element("auth-password");
    const errors = [];
    for (const [input, text] of [
      [email, email.validity.valid ? "" : "Enter a valid email address."],
      [
        password,
        !password.value
          ? "Enter your password."
          : mode === "signup" && password.value.length < 8
            ? "Use at least 8 characters."
            : "",
      ],
    ]) {
      element(`${input.id}-error`).textContent = text;
      input.setAttribute("aria-invalid", String(Boolean(text)));
      if (text) errors.push([input, text]);
    }
    if (errors.length) {
      const target = element("auth-message");
      target.replaceChildren(document.createTextNode("Please correct: "));
      for (const [input, text] of errors) {
        const a = document.createElement("a");
        a.href = `#${input.id}`;
        a.textContent = text + " ";
        target.append(a);
      }
      target.hidden = false;
      target.focus();
      return;
    }
    pending(true);
    try {
      const credentials = {
        email: email.value.trim(),
        password: password.value,
      };
      const { data, error } =
        mode === "signup"
          ? await client.auth.signUp({
              ...credentials,
              options: { emailRedirectTo: `${location.origin}/auth/callback` },
            })
          : await passwordSignIn(credentials);
      if (error) throw error;
      password.value = "";
      if (data.session) await synchronize(data.session, true);
      else {
        element("auth-content").hidden = true;
        element("auth-back").hidden = false;
        message(
          "Check your email to confirm your address. Then return here to sign in.",
          "info",
        );
      }
    } catch (error) {
      message(error.message);
    } finally {
      pending(false);
    }
  });
}
async function boot() {
  let watchdog;
  try {
    watchdog = setTimeout(() => {
      conceal();
      message(
        "Sign-in is taking longer than expected. Reload the page to retry.",
      );
      resolveReady(false);
    }, 20000);
    if (mode === "rate_limited") throw new Error(messages.rate_limited);
    client = await getSupabaseClient(nativeFetch, {
      recovery: mode === "reset",
    });
    document.addEventListener("click", (event) => {
      if (event.target.closest("#auth-signout, #dashboard-signout"))
        void signOut();
    });
    client.auth.onAuthStateChange((event, session) => {
      if (
        initialized &&
        mode === "reset" &&
        recoveryReady &&
        (event === "SIGNED_OUT" || session?.user?.id !== recoveryUserId)
      ) {
        invalidateRecovery();
        return;
      }
      if (initialized && !signingOut && !isRecoveryPage)
        setTimeout(() => {
          void synchronize(session).catch((error) => {
            conceal();
            message(error.message);
          });
        }, 0);
    });
    if (isRecoveryPage) {
      wireRecoveryForm();
      if (mode === "reset") {
        const params = new URLSearchParams(location.search);
        const code = params.get("code");
        const fragment = location.hash;
        history.replaceState(null, "", "/reset-password");
        if (!code || params.has("error") || fragment)
          throw new Error(
            "This reset link is missing, expired, or invalid. Request a new link and open it in the browser where you requested it.",
          );
        const { data, error } = await client.auth.exchangeCodeForSession(code);
        if (error || !data.session || data.redirectType !== "PASSWORD_RECOVERY")
          throw new Error(
            "Unable to verify this reset link. Request a new link and open it in the same browser.",
          );
        recoveryUserId = data.session.user?.id;
        if (!recoveryUserId)
          throw new Error(
            "Unable to verify the recovery account. Request a new reset link.",
          );
        recoveryReady = true;
      }
      showForm();
      resolveReady(false);
      initialized = true;
      return;
    }
    if (isAuthPage) wireForm();
    if (mode === "unavailable") throw new Error(messages.auth_unavailable);
    let session;
    if (mode === "callback") {
      const params = new URLSearchParams(location.search);
      const fragment = new URLSearchParams(location.hash.slice(1));
      const code = params.get("code");
      history.replaceState(null, "", "/auth/callback");
      if (params.has("error") || fragment.has("error")) {
        const errorCode =
          params.get("error_code") || fragment.get("error_code");
        throw new Error(
          errorCode === "otp_expired"
            ? "This confirmation link has expired or has already been used. If your email is already confirmed, return to sign in; otherwise request a new confirmation email."
            : "Sign-in was canceled or the link could not be completed. If your email is already confirmed, return to sign in.",
        );
      }
      if (fragment.has("access_token") || fragment.has("refresh_token")) {
        throw new Error(
          "This link uses an unsupported sign-in format. Return to sign in with your email and password, or request a new confirmation link.",
        );
      }
      const { data, error } = code
        ? await client.auth.exchangeCodeForSession(code)
        : await client.auth.getSession();
      if (error)
        throw new Error(
          "Unable to complete this link. Open it in the same browser and address where you signed up. If your email is already confirmed, return to sign in with your email and password.",
        );
      session = data.session;
      if (!session) {
        element("auth-back").hidden = false;
        message(
          "This page has no active sign-in link. If you have confirmed your email, return to sign in with your email and password. Otherwise, open the latest confirmation email in the browser where you signed up.",
          "info",
        );
        resolveReady(false);
        initialized = true;
        return;
      }
    } else {
      const { data, error } = await client.auth.getSession();
      if (error) throw error;
      session = data.session;
    }
    resolveReady(await synchronize(session));
    initialized = true;
  } catch (error) {
    conceal();
    message(error.message || messages.auth_unavailable);
    resolveReady(false);
    if (isAuthPage) {
      element("auth-back").hidden = false;
      if (
        client &&
        (mode === "login" || mode === "signup" || mode === "forgot")
      )
        showForm();
    }
  } finally {
    clearTimeout(watchdog);
  }
}
if (document.readyState === "loading")
  document.addEventListener("DOMContentLoaded", boot, { once: true });
else void boot();
window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    conceal();
    location.reload();
  }
});
