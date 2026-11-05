import { useState } from 'react';
import { useAnalyses } from '../api/analyses';
import AIForensicsPanel from '../components/AIForensicsPanel';

export default function History() {
  const { data, isLoading, error } = useAnalyses({ page: 1, pageSize: 20 });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="container-page">
      <h1 className="text-2xl font-bold text-slate-900">Analysis History</h1>
      <p className="mt-1 text-sm text-slate-600">Past forensic analyses and their status.</p>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {/* Analysis list */}
        <div className="lg:col-span-1">
          {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
          {error && <p className="text-sm text-red-600">Failed to load analyses.</p>}
          {data?.items.length === 0 && (
            <div className="card text-center">
              <p className="text-sm text-slate-500">No analyses yet.</p>
            </div>
          )}
          <ul className="space-y-2">
            {data?.items.map((a) => (
              <li key={a.id}>
                <button
                  className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedId === a.id ? 'border-brand-500 bg-brand-50' : 'border-slate-200 bg-white hover:bg-slate-50'}`}
                  onClick={() => setSelectedId(a.id)}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-800">{a.type}</span>
                    <StatusBadge status={a.status} />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {new Date(a.createdAt).toLocaleString()}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Detail panel */}
        <div className="space-y-4 lg:col-span-2">
          {selectedId ? (
            <>
              <AIForensicsPanel analysisId={selectedId} />
            </>
          ) : (
            <div className="card flex h-40 items-center justify-center">
              <p className="text-sm text-slate-400">Select an analysis to view AI forensics</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    QUEUED: 'bg-amber-100 text-amber-700',
    RUNNING: 'bg-blue-100 text-blue-700',
    DONE: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    CREATED: 'bg-slate-100 text-slate-600',
    NOT_RUN: 'bg-slate-100 text-slate-500',
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {status}
    </span>
  );
}
