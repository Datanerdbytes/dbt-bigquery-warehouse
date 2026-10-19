import { createClient } from "@supabase/supabase-js";
let client;
export async function getSupabaseClient(
  fetchConfig = fetch,
  { recovery = false } = {},
) {
  if (client && !recovery) return client;
  const response = await fetchConfig("/auth/config", {
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  if (!response.ok)
    throw new Error(
      "Authentication is not configured. Contact your administrator.",
    );
  const config = await response.json();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || config.url;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || config.anonKey;
  if (!url || !key) throw new Error("Authentication is not configured.");
  // Recovery sessions must never read or replace another tab's stored account.
  // Only the one-time PKCE verifier is shared with the requesting browser.
  const normalKey = `sb-${new URL(url).hostname.split(".")[0]}-auth-token`;
  const recoveryKey = `${normalKey}-recovery-${crypto.randomUUID()}`;
  const recoveryMemory = new Map();
  const verifierKey = `${normalKey}-code-verifier`;
  const isolatedStorage = {
    getItem(name) {
      return name === `${recoveryKey}-code-verifier`
        ? localStorage.getItem(verifierKey)
        : (recoveryMemory.get(name) ?? null);
    },
    setItem(name, value) {
      recoveryMemory.set(name, value);
    },
    removeItem(name) {
      if (name === `${recoveryKey}-code-verifier`)
        localStorage.removeItem(verifierKey);
      recoveryMemory.delete(name);
    },
  };
  const instance = createClient(url, key, {
    auth: {
      flowType: "pkce",
      detectSessionInUrl: false,
      persistSession: true,
      autoRefreshToken: !recovery,
      ...(recovery
        ? { storageKey: recoveryKey, storage: isolatedStorage }
        : {}),
    },
  });
  instance.qePasswordLockoutEnabled = config.passwordLockoutEnabled === true;
  if (!recovery) client = instance;
  return instance;
}
