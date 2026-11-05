import { useTravelAnalysis, useTriggerTravelAnalysis } from '../api/travel';
import type { TravelAnalysisRecord, TravelTransformation, TravelChangeRegion, MetadataChange } from '@pinithub/shared';
import { TRANSPORT_TRANSFORMS, CONTENT_TRANSFORMS } from '@pinithub/shared';
import ProgressState from './ProgressState';

interface Props {
  comparisonId: string;
}

const STATUS_COLORS: Record<string, string> = {
  NO_SIGNIFICANT_CHANGE: 'bg-green-100 text-green-700',
  TRANSFORMED_COPY: 'bg-blue-100 text-blue-700',
  CONTENT_CHANGED: 'bg-amber-100 text-amber-800',
  AI_CHANGE_DETECTED: 'bg-red-100 text-red-800',
  NO_MATCH: 'bg-orange-100 text-orange-700',
  INCONCLUSIVE: 'bg-slate-100 text-slate-600',
  QUEUED: 'bg-blue-100 text-blue-600',
  FAILED: 'bg-red-100 text-red-700',
};

/**
 * TravelAnalysisPanel — Phase 7 investigation display.
 *
 * Clearly separates:
 *   - Transport transformations (benign platform behaviour)
 *   - Content changes (potential manipulations)
 *
 * Never labels compression, resize, or metadata strip as "edited".
 */
export default function TravelAnalysisPanel({ comparisonId }: Props) {
  const { data, isLoading, refetch } = useTravelAnalysis(comparisonId);
  const trigger = useTriggerTravelAnalysis();

  const notRun = !data || ('status' in data && (data as any).status === 'NOT_RUN');
  const ta = !notRun && 'travelAnalysis' in data
    ? (data as any).travelAnalysis as TravelAnalysisRecord
    : null;

  const isRunning = ta?.status === 'QUEUED';

  if (isLoading) return <div className="card"><p className="text-sm text-slate-400">Loading…</p></div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Travel Analysis</h2>
          <p className="text-xs text-slate-400">Transport transformations ≠ malicious edits</p>
        </div>
        {notRun && (
          <button className="btn-primary text-xs" disabled={trigger.isPending}
            onClick={() => trigger.mutate(comparisonId, { onSuccess: () => setTimeout(() => refetch(), 2000) })}>
            {trigger.isPending ? 'Starting…' : 'Analyse travel'}
          </button>
        )}
      </div>

      {notRun && (
        <div className="card text-center">
          <p className="text-sm text-slate-400">
            Travel analysis compares the suspect copy to the protected original
            and identifies what happened during transit.
          </p>
        </div>
      )}

      {isRunning && <ProgressState step="PROTECTING" />}

      {ta && !isRunning && (
        <>
          {/* Status */}
          <div className="card">
            <div className="flex items-center gap-3">
              <span className={`rounded-full px-3 py-1 text-sm font-semibold ${STATUS_COLORS[ta.status] ?? 'bg-slate-100'}`}>
                {ta.status}
              </span>
              <StatusExplanation status={ta.status} />
            </div>
          </div>

          {/* Transport vs Content separation */}
          {ta.transformations && ta.transformations.length > 0 && (
            <TransformationBreakdown transformations={ta.transformations as TravelTransformation[]} />
          )}

          {/* Evidence */}
          {ta.evidence && (ta.evidence as string[]).length > 0 && (
            <div className="card space-y-2">
              <h3 className="text-sm font-semibold text-slate-700">Evidence</h3>
              <ul className="space-y-1">
                {(ta.evidence as string[]).map((e, i) => (
                  <li key={i} className="text-xs text-slate-600">• {e}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Metadata changes */}
          {ta.metadataChanges && (ta.metadataChanges as MetadataChange[]).length > 0 && (
            <MetadataChangesPanel changes={ta.metadataChanges as MetadataChange[]} />
          )}

          {/* Content changes */}
          {ta.changes && (ta.changes as TravelChangeRegion[]).length > 0 && (
            <ChangesPanel changes={ta.changes as TravelChangeRegion[]} />
          )}

          {/* Crop summary */}
          {ta.cropResult && (ta.cropResult as any).status === 'DETECTED' && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-700">Crop Analysis</h3>
              <p className="mt-1 text-sm text-amber-700">
                Crop detected: <strong>{((ta.cropResult as any).crop_percentage ?? 0).toFixed(2)}%</strong> of original removed
              </p>
            </div>
          )}

          {/* AI detection summary */}
          {ta.aiDetectionResult && (ta.aiDetectionResult as any).status !== 'UNAVAILABLE' && (
            <div className="card">
              <h3 className="text-sm font-semibold text-slate-700">AI Evidence</h3>
              <p className="mt-1 text-xs text-slate-600">
                AI detection: <strong>{(ta.aiDetectionResult as any).status}</strong>
                <span className="ml-1 text-amber-600">(UNCALIBRATED)</span>
              </p>
            </div>
          )}

          {/* Registration quality */}
          {ta.registrationQuality && (
            <details className="card">
              <summary className="cursor-pointer text-xs text-slate-500">Registration quality</summary>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                {Object.entries(ta.registrationQuality as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <dt className="text-slate-400">{k}</dt>
                    <dd className="text-slate-600">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}

          {/* Warnings */}
          {ta.warnings && (ta.warnings as string[]).length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
              <ul className="space-y-0.5 text-xs text-amber-700">
                {(ta.warnings as string[]).map((w, i) => <li key={i}>⚠ {w}</li>)}
              </ul>
            </div>
          )}

          <p className="text-xs text-slate-400 italic">
            Exec time: {ta.executionMs}ms · Analyzer v{ta.analyzerVersion}
          </p>
        </>
      )}
    </div>
  );
}

function StatusExplanation({ status }: { status: string }) {
  const msgs: Record<string, string> = {
    NO_SIGNIFICANT_CHANGE: 'No significant transformations detected.',
    TRANSFORMED_COPY: 'Platform-like transformations detected (compression, resize, metadata). These are benign transport behaviours.',
    CONTENT_CHANGED: 'Potential content changes detected (crop, objects, text). These require further investigation.',
    AI_CHANGE_DETECTED: 'AI-like evidence detected. Results are experimental (UNCALIBRATED).',
    NO_MATCH: 'Images could not be matched — may be unrelated.',
    INCONCLUSIVE: 'Insufficient evidence to classify.',
  };
  const msg = msgs[status];
  if (!msg) return null;
  return <span className="text-sm text-slate-600">{msg}</span>;
}

function TransformationBreakdown({ transformations }: { transformations: TravelTransformation[] }) {
  const transport = transformations.filter(t => TRANSPORT_TRANSFORMS.has(t));
  const content = transformations.filter(t => CONTENT_TRANSFORMS.has(t));

  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">Detected Transformations</h3>

      {transport.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-blue-600 uppercase tracking-wide">
            Transport / Platform (benign)
          </p>
          <div className="flex flex-wrap gap-1">
            {transport.map(t => (
              <span key={t} className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">{t}</span>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-400 italic">
            These are common platform behaviours and are NOT evidence of manipulation.
          </p>
        </div>
      )}

      {content.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-amber-700 uppercase tracking-wide">
            Content Changes (require investigation)
          </p>
          <div className="flex flex-wrap gap-1">
            {content.map(t => (
              <span key={t} className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700">{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetadataChangesPanel({ changes }: { changes: MetadataChange[] }) {
  const statusColors: Record<string, string> = {
    REMOVED: 'text-amber-700',
    MODIFIED: 'text-blue-700',
    ADDED: 'text-green-700',
    UNAVAILABLE: 'text-slate-400',
  };
  return (
    <div className="card">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">Metadata Changes</h3>
      <p className="mb-2 text-xs italic text-slate-400">
        Metadata removal is common in platform sharing and is NOT evidence of manipulation.
      </p>
      <dl className="space-y-1 text-xs">
        {changes.map((c, i) => (
          <div key={i} className="flex items-baseline justify-between gap-2">
            <dt className="text-slate-500">{c.field}</dt>
            <dd className={`font-medium ${statusColors[c.status] ?? 'text-slate-600'}`}>
              {c.status}
              {c.status === 'REMOVED' && c.originalValue && ` (was: ${c.originalValue})`}
              {c.status === 'MODIFIED' && c.returnedValue && ` → ${c.returnedValue}`}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ChangesPanel({ changes }: { changes: TravelChangeRegion[] }) {
  return (
    <div className="card">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">
        Content Change Candidates ({changes.length})
      </h3>
      <ul className="space-y-2">
        {changes.map((c, i) => (
          <li key={i} className="rounded-md bg-amber-50 px-3 py-2 text-xs">
            <div className="flex justify-between">
              <span className="font-medium text-amber-800">{c.type}</span>
              {c.areaPercentage !== null && c.areaPercentage !== undefined && (
                <span className="text-amber-600">{c.areaPercentage.toFixed(2)}%</span>
              )}
            </div>
            <p className="text-slate-500">
              {c.bbox.width}×{c.bbox.height}px at ({c.bbox.x},{c.bbox.y})
              {c.reliability && <span className="ml-1">· {c.reliability}</span>}
            </p>
            {c.evidence.map((e, j) => (
              <p key={j} className="mt-0.5 text-slate-400">• {e}</p>
            ))}
          </li>
        ))}
      </ul>
    </div>
  );
}
