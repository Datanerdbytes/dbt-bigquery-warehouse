import { createClient } from "@supabase/supabase-js";
let client;
export async function getSupabaseClient(fetchConfig = fetch) {
  if (client) return client;
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
  client = createClient(url, key, {
    auth: {
      flowType: "pkce",
      detectSessionInUrl: false,
      persistSession: true,
      autoRefreshToken: true,
    },
  });
  return client;
}
