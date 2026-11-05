import { useState } from 'react';
import { useAIDetection, useTriggerAIDetection } from '../api/analyses';
import type { AIDetectionDBRecord, AIRegion } from '@pinithub/shared';

interface Props {
  analysisId: string;
}

const STATUS_COLORS: Record<string, string> = {
  AI_GENERATED: 'bg-red-100 text-red-800',
  AI_EDITED_LOCAL: 'bg-amber-100 text-amber-800',
  NO_AI_EVIDENCE: 'bg-green-100 text-green-700',
  INCONCLUSIVE: 'bg-slate-100 text-slate-600',
  UNAVAILABLE: 'bg-slate-100 text-slate-400',
  QUEUED: 'bg-blue-100 text-blue-600',
  RUNNING: 'bg-blue-100 text-blue-700',
  FAILED: 'bg-red-100 text-red-700',
  NOT_RUN: 'bg-slate-100 text-slate-400',
};

/**
 * AIForensicsPanel — Phase 6 AI detection display.
 *
 * Shows:
 * - AI detection status
 * - Image-level score (raw, UNCALIBRATED)
 * - Detected regions with area percentages
 * - Model / version / calibration info
 * - Heatmap toggle (when available)
 *
 * CRITICAL: Never shows a definitive "edited/not-edited" verdict.
 * Always shows UNCALIBRATED label on any scores.
 * When model is unavailable, shows a clear message.
 */
export default function AIForensicsPanel({ analysisId }: Props) {
  const { data, isLoading, refetch } = useAIDetection(analysisId);
  const trigger = useTriggerAIDetection();
  const [showRegions, setShowRegions] = useState(false);

  const notRun = !data || ('status' in data && (data as any).status === 'NOT_RUN');
  const aiData = !notRun && 'aiDetection' in data
    ? (data as any).aiDetection as AIDetectionDBRecord
    : null;

  if (isLoading) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">AI Forensics</h3>
        <p className="mt-2 text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-700">AI Forensics</h3>
          <p className="text-xs text-slate-400">
            Experimental — UNCALIBRATED — not a definitive verdict
          </p>
        </div>
        {notRun && (
          <button
            className="btn-primary text-xs"
            disabled={trigger.isPending}
            onClick={() => trigger.mutate(analysisId, {
              onSuccess: () => setTimeout(() => refetch(), 2000),
            })}
          >
            {trigger.isPending ? 'Starting…' : 'Run AI detection'}
          </button>
        )}
      </div>

      {notRun && (
        <p className="text-sm text-slate-400">
          AI detection has not been run. Click "Run AI detection" to analyze.
          Requires trained model weights.
        </p>
      )}

      {aiData && (
        <>
          {/* Status */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[aiData.status] ?? 'bg-slate-100 text-slate-500'}`}>
              {aiData.status}
            </span>
            <StatusExplanation status={aiData.status} />
          </div>

          {/* UNAVAILABLE explanation */}
          {aiData.status === 'UNAVAILABLE' && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <p className="text-sm text-slate-600">
                <strong>AI detection unavailable.</strong>{' '}
                Trained model weights are required. Use the training script to train the model
                on a labelled dataset, then place the weights at the configured path.
              </p>
              <p className="mt-1 font-mono text-xs text-slate-400">
                python -m training.train_ai_detector --dataset_dir ... --output_dir ...
              </p>
            </div>
          )}

          {/* Image-level score */}
          {aiData.imageLevelScore !== null && aiData.imageLevelScore !== undefined && (
            <div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">
                  Image-level score (raw, UNCALIBRATED)
                </span>
                <span className="font-mono font-medium text-slate-700">
                  {aiData.imageLevelScore.toFixed(4)}
                </span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-amber-400"
                  style={{ width: `${Math.min(100, aiData.imageLevelScore * 100)}%` }}
                />
              </div>
              <p className="mt-0.5 text-xs italic text-slate-400">
                This is a raw sigmoid output — NOT a calibrated probability.
              </p>
            </div>
          )}

          {/* Edited area */}
          {aiData.editedAreaPct !== null && aiData.editedAreaPct !== undefined && (
            <div className="flex justify-between text-sm">
              <span className="text-slate-500">Estimated edited area</span>
              <span className="font-medium text-amber-700">
                {aiData.editedAreaPct.toFixed(2)}%
                <span className="ml-1 text-xs text-slate-400">(UNCALIBRATED)</span>
              </span>
            </div>
          )}

          {/* Regions */}
          {aiData.regions && (aiData.regions as AIRegion[]).length > 0 && (
            <div>
              <button
                className="btn-secondary text-xs"
                onClick={() => setShowRegions(!showRegions)}
              >
                {showRegions ? 'Hide' : 'Show'} {(aiData.regions as AIRegion[]).length} candidate region(s)
              </button>
              {showRegions && (
                <ul className="mt-2 space-y-2">
                  {(aiData.regions as AIRegion[]).slice(0, 10).map((r, i) => (
                    <li key={i} className="rounded-md bg-slate-50 px-3 py-2 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-600">
                          Region {i + 1}: {r.bbox.width}×{r.bbox.height}px at ({r.bbox.x},{r.bbox.y})
                        </span>
                        <span className="text-amber-700 font-medium">
                          {r.areaPercentage.toFixed(2)}%
                        </span>
                      </div>
                      {r.confidence !== null && r.confidence !== undefined && (
                        <p className="mt-0.5 text-slate-400">
                          Mean prob: {r.confidence.toFixed(3)} (raw, uncalibrated)
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Evidence */}
          {aiData.evidence && (aiData.evidence as string[]).length > 0 && (
            <details>
              <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
                Evidence summary
              </summary>
              <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
                {(aiData.evidence as string[]).map((e, i) => (
                  <li key={i}>• {e}</li>
                ))}
              </ul>
            </details>
          )}

          {/* Model info */}
          <div className="border-t border-slate-100 pt-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
              <dt className="text-slate-400">Model</dt>
              <dd className="text-slate-600">{aiData.modelName ?? '—'}</dd>
              <dt className="text-slate-400">Version</dt>
              <dd className="text-slate-600">{aiData.modelVersion ?? '—'}</dd>
              <dt className="text-slate-400">Calibration</dt>
              <dd className="font-medium text-amber-700">{aiData.calibrationStatus}</dd>
              <dt className="text-slate-400">Exec time</dt>
              <dd className="text-slate-600">{aiData.executionMs}ms</dd>
            </dl>
          </div>

          {/* Warnings */}
          {aiData.warnings && (aiData.warnings as string[]).length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-2">
              <ul className="space-y-0.5 text-xs text-amber-700">
                {(aiData.warnings as string[]).map((w, i) => (
                  <li key={i}>⚠ {w}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatusExplanation({ status }: { status: string }) {
  const msg: Record<string, string> = {
    AI_GENERATED: 'Whole-image AI-like evidence detected — may be fully AI-generated.',
    AI_EDITED_LOCAL: 'AI-like evidence in localized region(s). Not a confirmed edit.',
    NO_AI_EVIDENCE: 'No significant AI-like evidence detected.',
    INCONCLUSIVE: 'Weak AI-like evidence — cannot classify.',
    UNAVAILABLE: 'Model weights not loaded.',
  };
  const text = msg[status];
  if (!text) return null;
  return <span className="text-xs text-slate-500 italic">{text}</span>;
}
