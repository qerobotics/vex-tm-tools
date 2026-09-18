import { DatabaseZap } from 'lucide-react';
import { useReadyz } from '../../api/health';

/**
 * Plan Appendix A.10 (Redis Degradation) / audit finding 3.7: the backend
 * degrades gracefully when Redis is unreachable (`/readyz` reports
 * `status: "degraded"` with `redis: false` instead of a hard failure), but
 * the frontend previously only showed a plain `Redis: unreachable` text
 * line inside the Dashboard's Cluster Status card — not a distinct warning
 * banner like `ReconnectingBanner` (Appendix A.14). This mirrors that
 * component's treatment/placement so the two degraded-mode banners read as
 * one system, and is mounted globally in `PageLayout` (same as
 * `ReconnectingBanner`) since real-time features are degraded everywhere,
 * not just on the Dashboard.
 */
export function RedisWarningBanner() {
  const { data: ready } = useReadyz();
  if (!ready || ready.redis) return null;

  return (
    <div className="mx-4 mt-3 flex items-center gap-2 rounded-xl border border-amber-400/40 bg-amber-400/10 px-4 py-2 text-sm text-amber-200 lg:mx-8">
      <DatabaseZap size={16} />
      Redis unavailable — real-time features degraded.
    </div>
  );
}
