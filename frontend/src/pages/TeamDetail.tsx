import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useTeam, useUpdateTeam } from '../api/teams';
import { usePermission } from '../hooks/usePermission';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Label, Textarea } from '../components/ui/Input';
import { VideoUploader } from '../components/teams/VideoUploader';

export function TeamDetailPage() {
  const { number } = useParams<{ number: string }>();
  const { data: team } = useTeam(number ?? null);
  const updateTeam = useUpdateTeam();
  const canEdit = usePermission('teams:edit');

  const [pitLocation, setPitLocation] = useState('');
  const [extraNotes, setExtraNotes] = useState('');

  useEffect(() => {
    setPitLocation(team?.pit_location ?? '');
    setExtraNotes(team?.extra_notes ?? '');
  }, [team]);

  if (!number) return null;

  const stats = team?.cached_stats ?? {};

  return (
    <div>
      <Link to="/teams" className="mb-4 inline-flex items-center gap-1 text-sm text-vmd-link hover:underline">
        <ArrowLeft size={14} /> Back to Teams
      </Link>
      <PageHeader title={`Team ${number}`} subtitle={team?.robot_name ?? undefined} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">Profile</h2>
          <div className="space-y-3">
            <div>
              <Label>Pit Location</Label>
              <Input value={pitLocation} onChange={(e) => setPitLocation(e.target.value)} disabled={!canEdit} />
            </div>
            <div>
              <Label>Extra Notes</Label>
              <Textarea rows={3} value={extraNotes} onChange={(e) => setExtraNotes(e.target.value)} disabled={!canEdit} />
            </div>
            {canEdit && (
              <Button
                variant="primary"
                onClick={() =>
                  updateTeam.mutate({ number, body: { pit_location: pitLocation, extra_notes: extraNotes } })
                }
                disabled={updateTeam.isPending}
              >
                Save
              </Button>
            )}
          </div>

          <h2 className="mb-2 mt-5 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
            Stats (from scraper cache)
          </h2>
          {Object.keys(stats).length === 0 ? (
            <p className="text-sm text-vmd-textSubtle">No cached stats yet.</p>
          ) : (
            <dl className="grid grid-cols-2 gap-1 text-sm">
              {Object.entries(stats).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-vmd-textMuted">{key}</dt>
                  <dd className="text-right text-vmd-text">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
            Robot 360 Video
          </h2>
          <VideoUploader teamNumber={number} />
        </Card>
      </div>
    </div>
  );
}
