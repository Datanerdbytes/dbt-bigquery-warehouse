import { getSupabaseClient } from "./supabase-client.js";
window.qeAuthStarted = true;
const nativeFetch = window.fetch.bind(window);
const mode = document.documentElement.dataset.authPage;
const isAuthPage = Boolean(mode);
const element = (id) => document.getElementById(id);
let client,
  initialized = false,
  signingOut = false;
let synchronization = Promise.resolve(false);
let resolveReady;
const ready = new Promise((resolve) => {
  resolveReady = resolve;
});
const messages = {
  rate_limited: "Too many authentication requests. Wait a minute and retry.",
  approval_required:
    "Your email is verified. An administrator must approve your account before you can access this workspace.",
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
function synchronize(session) {
  synchronization = synchronization
    .catch(() => false)
    .then(() => syncSession(session));
  return synchronization;
}
async function signOut() {
  signingOut = true;
  conceal();
  try {
    await synchronization.catch(() => {});
    const { response, body } = await bridge("DELETE");
    if (!response.ok)
      throw new Error(messages[body.error] || "Unable to sign out. Retry.");
    const { error } = await client.auth.signOut({ scope: "local" });
    if (error) throw error;
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
function wireForm() {
  element("auth-show-password").addEventListener("click", (event) => {
    const input = element("auth-password"),
      showing = input.type === "password";
    input.type = showing ? "text" : "password";
    event.currentTarget.textContent = showing ? "Hide" : "Show";
    event.currentTarget.setAttribute(
      "aria-label",
      showing ? "Hide password" : "Show password",
    );
    event.currentTarget.setAttribute("aria-pressed", String(showing));
  });
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
          : await client.auth.signInWithPassword(credentials);
      if (error) throw error;
      password.value = "";
      if (data.session) await synchronize(data.session);
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
    client = await getSupabaseClient(nativeFetch);
    document.addEventListener("click", (event) => {
      if (event.target.closest("#auth-signout, #dashboard-signout"))
        void signOut();
    });
    client.auth.onAuthStateChange((_event, session) => {
      if (initialized && !signingOut)
        setTimeout(() => {
          void synchronize(session).catch((error) => {
            conceal();
            message(error.message);
          });
        }, 0);
    });
    if (isAuthPage) wireForm();
    if (mode === "unavailable") throw new Error(messages.auth_unavailable);
    let session;
    if (mode === "callback") {
      const params = new URLSearchParams(location.search),
        code = params.get("code");
      history.replaceState(null, "", "/auth/callback");
      if (params.has("error") || !code)
        throw new Error(
          "The sign-in link is invalid or canceled. If your email is already confirmed, return to sign in.",
        );
      const { data, error } = await client.auth.exchangeCodeForSession(code);
      if (error)
        throw new Error(
          "Unable to complete this link. If your email is confirmed, return to sign in in the browser where you started.",
        );
      session = data.session;
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
      if (client && (mode === "login" || mode === "signup")) showForm();
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
