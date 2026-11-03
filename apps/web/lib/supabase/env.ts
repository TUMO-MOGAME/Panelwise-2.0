// The Supabase project the web app signs in against: only the publishable key ever reaches the
// browser (deploy.md §4). Null when unset, so callers fail closed: signed out, never signed in.

export function supabaseEnv(): { url: string; key: string } | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  return url && key ? { url, key } : null;
}
