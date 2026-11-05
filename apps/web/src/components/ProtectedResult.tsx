import { useState } from 'react';
import { useInvestigation, useInvestigationEvidence, useInvestigationRegions, useSealInvestigation, useInvestigationSeal } from '../api/investigations';
import type { InvestigationSummary, EvidenceItem, FinalRegion } from '@pinithub/shared';
import ProgressState from './ProgressState';

interface Props {
  investigationId: string;
}

const VERDICT_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  EDITED:               { bg: 'bg-red-100',    text: 'text-red-800',    label: 'EDITED' },
  NOT_EDITED:           { bg: 'bg-green-100',  text: 'text-green-800',  label: 'NOT EDITED' },
  INCONCLUSIVE:         { bg: 'bg-amber-100',  text: 'text-amber-800',  label: 'INCONCLUSIVE' },
  NO_MATCH:             { bg: 'bg-orange-100', text: 'text-orange-800', label: 'NO MATCH' },
  ANALYSIS_UNAVAILABLE: { bg: 'bg-slate-100',  text: 'text-slate-600',  label: 'UNAVAILABLE' },
};

const STRENGTH_COLORS: Record<string, string> = {
  HIGH: 'text-green-700', MEDIUM: 'text-amber-700',
  LOW: 'text-red-600', INSUFFICIENT: 'text-slate-400',
};

const STATUS_COLORS: Record<string, string> = {
  SUPPORTING: 'bg-red-50 text-red-700 border-red-200',
  NEUTRAL: 'bg-slate-50 text-slate-600 border-slate-200',
  CONTRADICTING: 'bg-green-50 text-green-700 border-green-200',
  UNAVAILABLE: 'bg-slate-50 text-slate-400 border-slate-200',
};

/**
 * ProtectedResult — Phase 8 Investigation Workspace.
 *
 * Displays the final fused investigation result:
 *   - Verdict + evidence strength
 *   - Evidence breakdown per detector
 *   - Fused regions in original coordinate system
 *   - Seal controls
 *
 * Never shows fake forensic values.
 * "NOT_EDITED" does not claim authenticity guarantee.
 */
export default function ProtectedResult({ investigationId }: Props) {
  const { data: invData, isLoading } = useInvestigation(investigationId);
  const { data: evidenceData } = useInvestigationEvidence(investigationId);
  const { data: regionsData } = useInvestigationRegions(investigationId);
  const { data: sealData, refetch: refetchSeal } = useInvestigationSeal(investigationId);
  const sealMutation = useSealInvestigation();
  const [showEvidence, setShowEvidence] = useState(false);

  if (isLoading) return <ProgressState step="PROTECTING" />;

  const inv = invData?.investigation as InvestigationSummary | undefined;
  if (!inv) return null;

  const isRunning = ['PENDING', 'RUNNING'].includes(inv.status);
  if (isRunning) return <ProgressState step="PROTECTING" />;

  const verdict = inv.verdict ?? 'INCONCLUSIVE';
  const vStyle = VERDICT_COLORS[verdict] ?? VERDICT_COLORS.INCONCLUSIVE;
  const evidence = evidenceData?.items ?? [];
  const regions = regionsData?.regions ?? [];
  const sealed = sealData && 'sealedHash' in sealData;

  return (
    <div className="space-y-4">
      {/* Investigation Summary Card */}
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Investigation Result</h2>

        <div className={`mt-3 flex items-center gap-3 rounded-lg ${vStyle.bg} px-4 py-3`}>
          <span className={`text-2xl font-bold ${vStyle.text}`}>{vStyle.label}</span>
          <div>
            <p className={`text-sm font-medium ${STRENGTH_COLORS[inv.evidenceStrength ?? 'INSUFFICIENT']}`}>
              Evidence strength: {inv.evidenceStrength ?? 'INSUFFICIENT'}
            </p>
            <p className="text-xs text-slate-500">
              Confidence: {inv.confidenceStatus ?? 'UNCALIBRATED'}
            </p>
          </div>
        </div>

        {inv.explanation && (
          <p className="mt-3 text-sm text-slate-600 italic">{inv.explanation}</p>
        )}

        {verdict === 'NOT_EDITED' && (
          <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            "Not Edited" means no modification evidence was found by the current detectors.
            It does <strong>not</strong> guarantee the image is authentic.
          </div>
        )}

        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">Evidence groups</dt>
          <dd>{evidence.length} items</dd>
          <dt className="text-slate-500">Regions detected</dt>
          <dd>{regions.length}</dd>
          <dt className="text-slate-500">Report hash</dt>
          <dd className="font-mono text-xs truncate">{inv.reportHash ? inv.reportHash.slice(0, 16) + '…' : '—'}</dd>
          <dt className="text-slate-500">Sealed</dt>
          <dd>{sealed ? '✓ Sealed' : 'Not sealed'}</dd>
        </dl>
      </div>

      {/* Regions */}
      {regions.length > 0 && (
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold text-slate-700">
            Detected Regions ({regions.length})
          </h3>
          <ul className="space-y-2">
            {regions.map((r: FinalRegion) => (
              <li key={r.id} className="rounded-md bg-amber-50 px-3 py-2 text-xs">
                <div className="flex justify-between">
                  <span className="font-medium text-amber-800">{r.type}</span>
                  <span className="text-amber-600">{r.areaPercentage.toFixed(2)}%</span>
                </div>
                <p className="text-slate-500">
                  {r.bbox.width}×{r.bbox.height}px at ({r.bbox.x},{r.bbox.y})
                  · evidence count: {r.evidenceCount}
                </p>
                <p className="text-slate-400">
                  Detectors: {r.sourceDetectors.join(', ')}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence breakdown */}
      <div className="card">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">Evidence Breakdown</h3>
          <button className="text-xs text-brand-600" onClick={() => setShowEvidence(!showEvidence)}>
            {showEvidence ? 'Hide' : 'Show'} all
          </button>
        </div>
        {showEvidence && (
          <ul className="mt-3 space-y-1">
            {evidence.map((ev: EvidenceItem) => (
              <li key={ev.id}
                className={`rounded border px-2 py-1.5 text-xs ${STATUS_COLORS[ev.status]}`}>
                <div className="flex justify-between">
                  <span className="font-medium">{ev.category}</span>
                  <span>{ev.status}</span>
                </div>
                <p className="text-slate-500 truncate">{ev.description}</p>
                <p className="text-slate-400">{ev.detector} v{ev.version}</p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Report + Seal */}
      <div className="card space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">Report & Seal</h3>

        <div className="flex gap-2 flex-wrap">
          <a
            href={`/v1/investigations/${investigationId}/report.json`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary text-xs"
          >
            Download JSON Report
          </a>
          {!sealed && (
            <button
              className="btn-primary text-xs"
              disabled={sealMutation.isPending}
              onClick={() => sealMutation.mutate(investigationId, { onSuccess: () => refetchSeal() })}
            >
              {sealMutation.isPending ? 'Sealing…' : 'Seal Report'}
            </button>
          )}
        </div>

        {sealed && 'sealedHash' in sealData && (
          <div className="rounded-md border border-green-200 bg-green-50 p-3">
            <p className="text-xs font-semibold text-green-800">Report Sealed (TAMPER_EVIDENT)</p>
            <p className="mt-1 break-all font-mono text-xs text-green-700">{sealData.sealedHash}</p>
            <p className="mt-1 text-xs text-green-600 italic">
              SHA-256 of canonical report JSON. Not TAMPER_PROOF.
              Verify by re-hashing the report.
            </p>
          </div>
        )}
      </div>

      {/* Limitations */}
      <div className="card border-slate-200 bg-slate-50">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Limitations</h3>
        <ul className="mt-2 space-y-0.5 text-xs text-slate-500">
          <li>• AI detection is experimental (UNCALIBRATED)</li>
          <li>• Classical signals are not individually definitive</li>
          <li>• Metadata is evidence, not proof</li>
          <li>• Fusion weights are heuristic — no calibrated probability</li>
          <li>• Heavy crops or transport-only copies may be INCONCLUSIVE</li>
        </ul>
      </div>
    </div>
  );
}
