import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { completeSpotifyPkceFlow } from '../api/spotifyOAuth';
import { useSetOauthToken } from '../api/integrations';
import { Card } from '../components/ui/Card';

/** Landing point for Spotify's PKCE redirect (plan §3.5 steps 2-4). Reads
 * `code`/`state` from the query string, exchanges them for tokens
 * client-side, then POSTs the tokens to our backend's
 * `/oauth_token` route and redirects back to the Integrations page. */
export function SpotifyCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const setOauthToken = useSetOauthToken();
  const [error, setError] = useState<string | null>(null);
  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;

    const code = params.get('code');
    const state = params.get('state');
    const errorParam = params.get('error');
    if (errorParam) {
      setError(`Spotify denied authorization: ${errorParam}`);
      return;
    }
    if (!code || !state) {
      setError('Missing code/state in Spotify callback URL.');
      return;
    }

    // The client_id isn't in the callback URL (Spotify's redirect never
    // echoes it back) — it was already used once to build the authorize
    // URL, so re-derive it the same way `SpotifyAuthButton` did: the
    // integration's stored (non-secret) config. Since we don't have the
    // entity_id yet either, `completeSpotifyPkceFlow` looks up both from
    // the stashed PKCE session — the client_id must therefore be re-passed
    // by the caller. Rather than re-fetching the integration list here, we
    // stash `client_id` alongside the verifier/entity_id at flow-start.
    const stashed = sessionStorage.getItem(`qecomp_spotify_pkce_client_id_${state}`);
    const clientId = stashed ?? '';

    completeSpotifyPkceFlow(clientId, code, state)
      .then((result) =>
        setOauthToken.mutateAsync({
          entityId: result.entityId,
          accessToken: result.accessToken,
          refreshToken: result.refreshToken,
          expiresIn: result.expiresIn,
        }),
      )
      .then(() => navigate('/integrations', { replace: true }))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'OAuth exchange failed'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-vmd-bg px-4">
      <Card className="max-w-md">
        {error ? (
          <p className="text-vmd-danger">{error}</p>
        ) : (
          <p className="text-vmd-textMuted">Completing Spotify authentication…</p>
        )}
      </Card>
    </div>
  );
}
