import { Music } from 'lucide-react';
import { Button } from '../ui/Button';
import { startSpotifyPkceFlow } from '../../api/spotifyOAuth';
import { useUiStore } from '../../stores/ui';
import type { IntegrationInstance } from '../../types/api';

/** Plan §3.5/§5.4/§12: "Authenticate with Spotify" button per Spotify
 * instance — kicks off the browser PKCE redirect (see
 * `api/spotifyOAuth.ts`). Token status itself isn't separately exposed by
 * the backend beyond the instance's connection `status`, so this reads
 * that (via the caller's `IntegrationStatusChip`) rather than a dedicated
 * "authenticated: true/false" field the API doesn't provide. */
export function SpotifyAuthButton({ integration }: { integration: IntegrationInstance }) {
  const pushToast = useUiStore((s) => s.pushToast);
  const clientId = String(integration.config.client_id ?? '');

  async function handleClick() {
    if (!clientId) {
      pushToast('Set a Client ID on this instance before authenticating.', 'error');
      return;
    }
    await startSpotifyPkceFlow(integration.entity_id, clientId);
  }

  return (
    <Button onClick={handleClick} variant="secondary">
      <Music size={14} /> Authenticate with Spotify
    </Button>
  );
}
