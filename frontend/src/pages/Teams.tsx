import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTeams } from '../api/teams';
import { useDebounce } from '../hooks/useDebounce';
import { PageHeader, Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';

export function TeamsPage() {
  const { data: teams, isLoading } = useTeams();
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 200);

  const filtered = (teams ?? []).filter((t) =>
    t.team_number.toLowerCase().includes(debouncedSearch.toLowerCase()),
  );

  return (
    <div>
      <PageHeader title="Teams" subtitle="Team profiles auto-populated from the TM scraper." />
      <Input
        placeholder="Search by team number…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mb-4 max-w-xs"
      />

      {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((team) => (
          <Link key={team.team_number} to={`/teams/${team.team_number}`}>
            <Card className="h-full hover:shadow-vmdCardHover">
              <p className="font-medium text-vmd-textStrong">{team.team_number}</p>
              {team.robot_name && <p className="text-sm text-vmd-textMuted">{team.robot_name}</p>}
              {team.pit_location && <p className="text-xs text-vmd-textSubtle">Pit: {team.pit_location}</p>}
              <p className="mt-1 text-xs text-vmd-textSubtle">
                Video: {team.video_processing_status}
              </p>
            </Card>
          </Link>
        ))}
      </div>
      {filtered.length === 0 && !isLoading && (
        <p className="text-sm text-vmd-textSubtle">No teams found yet — they auto-populate once matches are assigned.</p>
      )}
    </div>
  );
}
