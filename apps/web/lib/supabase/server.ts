// The server-side guard (web.md §4.0): every page and route handler asks currentUser() before it
// calls the API. getClaims() verifies the token against the project's JWKS, as the API does;
// the access token is read only after that.

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { supabaseEnv } from "./env";

export async function createClient() {
  // Cookies first, env second: reading them is what makes every caller render per request, even
  // in a build with no Supabase configured.
  const store = await cookies();
  const env = supabaseEnv();
  if (!env) return null;
  return createServerClient(env.url, env.key, {
    cookies: {
      getAll: () => store.getAll(),
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => store.set(name, value, options));
        } catch {
          // A server component can't write cookies; the proxy has already refreshed them.
        }
      },
    },
  });
}

export interface CurrentUser {
  email: string | null;
  accessToken: string;
}

export async function currentUser(): Promise<CurrentUser | null> {
  const supabase = await createClient();
  if (!supabase) return null;
  const { data, error } = await supabase.auth.getClaims();
  if (error || !data?.claims) return null;
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;
  const email = typeof data.claims.email === "string" ? data.claims.email : null;
  return { email, accessToken: session.access_token };
}
