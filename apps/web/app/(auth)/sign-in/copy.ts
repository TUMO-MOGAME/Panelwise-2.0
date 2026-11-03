// Sign-in copy (web.md §4.0, §6 Copy) and which one an Auth error gets.

export const REFUSED = "That email and password don't match. Check both and try again.";
export const UNAVAILABLE = "Signing in isn't working right now. Try again in a minute.";

export interface SignInState {
  error: string | null;
  email: string; // kept across a refused attempt, as signin.png shows
}

/** Only a 4xx refusal of the credentials is the user's to fix; anything else is unavailability. */
export function signInErrorCopy(error: { status?: number; code?: string }): string {
  const refused = error.status !== undefined && error.status >= 400 && error.status < 500 && error.status !== 429;
  return refused ? REFUSED : UNAVAILABLE;
}
