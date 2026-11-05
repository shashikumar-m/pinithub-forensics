import type { RegionRecord } from '@pinithub/shared';

interface Props {
  regions?: RegionRecord[] | null;
}

/**
 * ChangeList — displays detected changes between original and suspect images.
 *
 * Only renders real data from the backend. When no data is available,
 * shows an empty state. Never fabricates change items like "Crop: 23%"
 * or "AI edited: Yes".
 */
export default function ChangeList({ regions }: Props) {
  if (!regions || regions.length === 0) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Detected Changes</h2>
        <p className="mt-4 text-sm text-slate-400">
          No changes detected. This requires a completed forensic analysis.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-slate-900">Detected Changes</h2>
      <ul className="mt-4 divide-y divide-slate-200">
        {regions.map((r) => (
          <li key={r.id} className="py-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">{r.type}</span>
              {r.score !== null && (
                <span className="text-xs text-slate-500">
                  Score: {r.score.toFixed(2)}
                </span>
              )}
            </div>
            {r.description && (
              <p className="mt-1 text-xs text-slate-500">{r.description}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
