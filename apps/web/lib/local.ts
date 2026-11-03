// Panelwise 2.0's local mode: with PANELWISE_LOCAL_TOKEN set (server-side only, never
// NEXT_PUBLIC_), there is no Supabase. The one user is the laptop's owner, always signed in, and
// the server sends the token to the API, which shares it (services/api/app/core/auth.py).

export function localToken(): string | null {
  return process.env.PANELWISE_LOCAL_TOKEN || null;
}
