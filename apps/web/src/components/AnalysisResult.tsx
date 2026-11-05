import type { AnalysisRecord } from '@pinithub/shared';

interface Props {
  analysis?: AnalysisRecord | null;
}

/**
 * AnalysisResult — displays the result of a forensic analysis.
 *
 * CRITICAL: This component shows real backend data only. It never
 * displays fabricated values like "AI confidence: 98%" or "Edited: Yes".
 * When no result is available, it shows an appropriate empty state.
 */
export default function AnalysisResult({ analysis }: Props) {
  if (!analysis) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Analysis Result</h2>
        <p className="mt-4 text-sm text-slate-400">
          No analysis result available. Start an analysis from the Investigation page.
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-slate-900">Analysis Result</h2>
      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex justify-between">
          <dt className="text-slate-500">Type</dt>
          <dd className="text-slate-700">{analysis.type}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-slate-500">Status</dt>
          <dd className="text-slate-700">{analysis.status}</dd>
        </div>
        {/* Verdict and confidence only displayed when actually present from backend */}
        {analysis.verdict && (
          <div className="flex justify-between">
            <dt className="text-slate-500">Verdict</dt>
            <dd className="text-slate-700">{analysis.verdict}</dd>
          </div>
        )}
        {analysis.confidence !== null && analysis.confidence !== undefined && (
          <div className="flex justify-between">
            <dt className="text-slate-500">Confidence</dt>
            <dd className="text-slate-700">{(analysis.confidence * 100).toFixed(1)}%</dd>
          </div>
        )}
        {analysis.error && (
          <div className="flex justify-between">
            <dt className="text-slate-500">Error</dt>
            <dd className="text-red-600">{analysis.error}</dd>
          </div>
        )}
      </dl>
      {analysis.status === 'QUEUED' && (
        <p className="mt-4 text-xs text-amber-600">
          Analysis is queued. Forensic detection is not yet implemented in this phase.
        </p>
      )}
    </div>
  );
}
