/**
 * Browser-side Spotify PKCE flow (plan §3.5). Lives under `frontend/src/api/`
 * per §C.3/§C.5 rule 7 ("no raw fetch in pages") even though these calls
 * target Spotify's own accounts/API service rather than our FastAPI backend
 * — this is still the one sanctioned location for `fetch()` outside of
 * `lib/http.ts`. Not built as TanStack Query hooks since the flow is a
 * one-shot redirect + code exchange, not cached server data.
 */

const SPOTIFY_AUTHORIZE_URL = 'https://accounts.spotify.com/authorize';
const SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token';
const SCOPES = 'user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private';

function base64UrlEncode(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function sha256(input: string): Promise<ArrayBuffer> {
  const data = new TextEncoder().encode(input);
  return crypto.subtle.digest('SHA-256', data);
}

function randomVerifier(): string {
  const bytes = new Uint8Array(64);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes.buffer);
}

const STORAGE_PREFIX = 'qecomp_spotify_pkce_';

/** Step 1 (plan §3.5): generate the PKCE pair, stash the verifier +
 * entity_id keyed by `state` in sessionStorage, and redirect the browser to
 * Spotify's authorize endpoint. */
export async function startSpotifyPkceFlow(entityId: string, clientId: string): Promise<void> {
  const verifier = randomVerifier();
  const challenge = base64UrlEncode(await sha256(verifier));
  const state = randomVerifier();

  sessionStorage.setItem(STORAGE_PREFIX + state, JSON.stringify({ verifier, entityId }));
  // Stashed separately (rather than folded into the JSON above) so the
  // callback page's lookup-by-key expectation (`qecomp_spotify_pkce_client_id_<state>`)
  // is a stable, self-documenting key name.
  sessionStorage.setItem(`qecomp_spotify_pkce_client_id_${state}`, clientId);

  const redirectUri = `${window.location.origin}/integrations/spotify/callback`;
  const params = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    code_challenge_method: 'S256',
    code_challenge: challenge,
    state,
    scope: SCOPES,
  });
  window.location.href = `${SPOTIFY_AUTHORIZE_URL}?${params.toString()}`;
}

export interface SpotifyPkceCallbackResult {
  entityId: string;
  accessToken: string;
  refreshToken?: string;
  expiresIn: number;
}

/** Step 2/3 (plan §3.5): called from the `/integrations/spotify/callback`
 * route with the `code`/`state` query params Spotify redirected back with.
 * Exchanges the code + stashed verifier for tokens directly against
 * Spotify (client secret never touches the browser for this user-token
 * exchange — PKCE doesn't need it). Step 4 (POSTing the resulting tokens
 * to our backend) is the caller's job via `useSetOauthToken()`. */
export async function completeSpotifyPkceFlow(
  clientId: string,
  code: string,
  state: string,
): Promise<SpotifyPkceCallbackResult> {
  const raw = sessionStorage.getItem(STORAGE_PREFIX + state);
  if (!raw) {
    throw new Error('No matching PKCE session found for this state (expired or opened in another tab).');
  }
  sessionStorage.removeItem(STORAGE_PREFIX + state);
  sessionStorage.removeItem(`qecomp_spotify_pkce_client_id_${state}`);
  const { verifier, entityId } = JSON.parse(raw) as { verifier: string; entityId: string };

  const redirectUri = `${window.location.origin}/integrations/spotify/callback`;
  const body = new URLSearchParams({
    client_id: clientId,
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    code_verifier: verifier,
  });

  const res = await fetch(SPOTIFY_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Spotify token exchange failed: ${detail}`);
  }
  const json = (await res.json()) as {
    access_token: string;
    refresh_token?: string;
    expires_in: number;
  };
  return {
    entityId,
    accessToken: json.access_token,
    refreshToken: json.refresh_token,
    expiresIn: json.expires_in,
  };
}
