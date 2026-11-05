import type { DetectorOutput } from '../api/detectors';

interface Props {
  detectors: DetectorOutput[];
  loading?: boolean;
}

const DETECTOR_INFO: Record<string, { label: string; scoreLabel: string }> = {
  ela: { label: 'Error Level Analysis', scoreLabel: 'Recompression error statistic' },
  noise_residual: { label: 'Noise Residual Analysis', scoreLabel: 'Local residual inconsistency' },
  dct_analysis: { label: 'DCT / JPEG Analysis', scoreLabel: 'DC energy ratio' },
  jpeg_double_compression: { label: 'JPEG Double-Compression', scoreLabel: 'Histogram gap indicator' },
  resampling: { label: 'Resampling Detection', scoreLabel: 'Periodicity strength' },
  jpeg_grid: { label: 'JPEG Grid / Blocking', scoreLabel: 'Normalized blocking strength' },
  copy_move: { label: 'Copy-Move Detection', scoreLabel: 'Geometric consistency ratio' },
  metadata_inspector: { label: 'Metadata Inspector', scoreLabel: 'Evidence extraction' },
};

/**
 * DetectorResults — displays individual detector results.
 *
 * Shows each detector independently. No final verdict or fusion.
 * Clearly labels that these are independent forensic signals.
 */
export default function DetectorResults({ detectors, loading }: Props) {
  if (loading) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Classical Forensic Evidence</h2>
        <p className="mt-4 text-sm text-slate-400">Running detectors…</p>
      </div>
    );
  }

  if (!detectors || detectors.length === 0) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Classical Forensic Evidence</h2>
        <p className="mt-4 text-sm text-slate-400">
          No detector outputs available. Detectors have not been run yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
        <p className="text-sm text-blue-800">
          <strong>Classical forensic evidence.</strong> These are independent signals,
          not a final authenticity verdict. No fusion or calibration has been applied.
        </p>
      </div>

      {detectors.map((d) => (
        <DetectorCard key={d.id} detector={d} />
      ))}
    </div>
  );
}

function DetectorCard({ detector }: { detector: DetectorOutput }) {
  const info = DETECTOR_INFO[detector.detector] ?? { label: detector.detector, scoreLabel: 'Score' };
  const status = detector.status;
  const details = detector.details as Record<string, unknown>;
  const evidence = (details?.evidence ?? {}) as Record<string, unknown>;
  const limitations = (details?.limitations ?? []) as string[];
  const warnings = (details?.warnings ?? []) as string[];

  const statusColors: Record<string, string> = {
    COMPLETED: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    NOT_APPLICABLE: 'bg-slate-100 text-slate-500',
    NOT_RUN: 'bg-slate-100 text-slate-400',
    RUNNING: 'bg-blue-100 text-blue-700',
    NOT_IMPLEMENTED: 'bg-amber-100 text-amber-700',
  };
  const statusColor = statusColors[status] ?? 'bg-slate-100 text-slate-500';

  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{info.label}</h3>
          <p className="text-xs text-slate-400">
            v{detector.version} · {detector.executionTimeMs}ms
          </p>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor}`}>
          {status}
        </span>
      </div>

      {status === 'COMPLETED' && detector.score !== null && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">{info.scoreLabel}</span>
            <span className="font-mono font-medium text-slate-700">
              {detector.score.toFixed(4)}
            </span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand-500"
              style={{ width: `${Math.min(100, detector.score * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-xs text-slate-400 italic">
            Score meaning: {(details?.score_semantics as string) ?? info.scoreLabel}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Reliability: {(details?.reliability as string) ?? 'UNCALIBRATED'}
          </p>
        </div>
      )}

      {status === 'COMPLETED' && Object.keys(evidence).length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence</p>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
            {Object.entries(evidence).slice(0, 8).map(([key, val]) => (
              <div key={key} className="flex justify-between">
                <dt className="text-slate-500">{key}</dt>
                <dd className="font-mono text-slate-700">
                  {typeof val === 'number' ? val.toFixed(2) : String(val).slice(0, 30)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {status === 'NOT_APPLICABLE' && (
        <p className="mt-2 text-xs text-slate-500">
          {(details?.reason as string) ?? 'Not applicable for this image format.'}
        </p>
      )}

      {status === 'FAILED' && detector.error && (
        <p className="mt-2 text-xs text-red-600">{detector.error}</p>
      )}

      {limitations.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Limitations</p>
          <ul className="list-inside list-disc space-y-0.5 text-xs text-slate-500">
            {limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-2">
          <p className="text-xs text-amber-600">⚠ {warnings.length} warning(s)</p>
        </div>
      )}

      {details?.artifact != null && (
        <div className="mt-2">
          <p className="text-xs text-slate-500">
            📎 Evidence map generated: {String((details.artifact as Record<string, unknown>).type)}
          </p>
        </div>
      )}
    </div>
  );
}
