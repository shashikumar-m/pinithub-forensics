import { useState } from 'react';
import type { ProtectResult } from '../hooks/useProtectFlow';

interface Props {
  result: ProtectResult & { forensics?: any; metadata?: any };
  onProtectAnother: () => void;
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

const VERDICT_STYLES: Record<string, { bg: string; text: string; border: string; label: string }> = {
  EDITED: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    label: 'TAMPERED / EDITED',
  },
  NOT_EDITED: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    label: 'AUTHENTIC / NOT EDITED',
  },
  INCONCLUSIVE: {
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-200',
    label: 'INCONCLUSIVE',
  },
};

/**
 * UploadSuccessCard — displays Phase 1 image protection details
 * along with unified forensic analysis results (Phase 2-10).
 */
export default function UploadSuccessCard({ result, onProtectAnother }: Props) {
  const { image, analysisId, duplicate, forensics, metadata } = result as any;
  const [showHeatmap, setShowHeatmap] = useState(true);

  // Normalize evidence detectors from either unified 'evidence' or legacy 'results'
  const detectors: any[] = forensics?.evidence ?? forensics?.results ?? [];
  const verdict: string | undefined = forensics?.verdict;
  const probability: number | undefined = forensics?.probability;
  const summaryText: string = typeof forensics?.summary === 'string'
    ? forensics.summary
    : 'Forensic inspection completed across all available signal extractors.';

  const hasForensics = Boolean(forensics && (verdict || detectors.length > 0));
  const verdictStyle = verdict ? (VERDICT_STYLES[verdict] ?? VERDICT_STYLES.INCONCLUSIVE) : VERDICT_STYLES.INCONCLUSIVE;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      {duplicate ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="font-medium text-amber-800">Duplicate detected</p>
          <p className="mt-1 text-sm text-amber-700">
            This exact image is already protected in your vault (same SHA-256 hash).
          </p>
        </div>
      ) : (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4">
          <p className="font-medium text-green-800">✓ Image protected successfully</p>
          <p className="mt-1 text-sm text-green-700">
            Stored unchanged in private storage with verified SHA-256 hash.
          </p>
        </div>
      )}

      {/* Image details */}
      <div className="card space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Protected image details</h2>
        <dl className="divide-y divide-slate-100 text-sm">
          {[
            ['Filename', image.originalFilename],
            ['Format', image.format?.toUpperCase() ?? '—'],
            ['Dimensions', image.width && image.height ? `${image.width} × ${image.height} px` : '—'],
            ['File size', bytes(image.sizeBytes)],
            ['Source', image.source],
            ['Status', image.status],
            ['Camera Make / Model', metadata?.camera ? `${metadata.camera.make || ''} ${metadata.camera.model || ''}`.trim() || 'Not embedded' : 'Not extracted'],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between py-2">
              <dt className="text-slate-500">{label}</dt>
              <dd className="text-right font-medium text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* SHA-256 */}
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">Cryptographic SHA-256 Hash</h3>
        <p className="mt-1 break-all font-mono text-xs text-slate-600">{image.sha256}</p>
      </div>

      {/* Forensic Analysis Results */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-slate-900">Forensic Analysis</h3>
          {forensics?.executionMs && (
            <span className="text-xs text-slate-400 font-mono">
              {forensics.executionMs} ms
            </span>
          )}
        </div>

        {!hasForensics ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
            <p className="text-sm text-amber-800">
              <strong>Status: QUEUED</strong> — Analysis queued in forensic vault.
            </p>
            {analysisId && <p className="mt-1 text-xs text-slate-500">Analysis ID: {analysisId}</p>}
            <p className="mt-1 text-xs text-slate-400">
              Results will be available in the vault once processing completes.
            </p>
          </div>
        ) : (
          <>
            {/* Verdict and Probability Banner */}
            {verdict && (
              <div className={`rounded-lg border p-4 ${verdictStyle.bg} ${verdictStyle.border}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                      Scientific Verdict
                    </span>
                    <h4 className={`text-xl font-extrabold ${verdictStyle.text}`}>
                      {verdictStyle.label}
                    </h4>
                  </div>
                  {probability !== undefined && (
                    <div className="text-right">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Calibrated Confidence
                      </span>
                      <p className={`text-2xl font-black ${verdictStyle.text}`}>
                        {(probability * 100).toFixed(0)}%
                      </p>
                    </div>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-700">{summaryText}</p>
              </div>
            )}

            {/* AI Generation Signal */}
            {forensics?.aiDetection && (
              <div className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-medium text-slate-700">AI Synthetics / Inpainting Detector:</span>
                <span className="inline-flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                    forensics.aiDetection.label === 'AI_GENERATED'
                      ? 'bg-purple-100 text-purple-700'
                      : forensics.aiDetection.label === 'AI_EDITED'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {forensics.aiDetection.label}
                  </span>
                  <span className="text-xs font-mono text-slate-500">
                    score: {forensics.aiDetection.score?.toFixed(3)}
                  </span>
                </span>
              </div>
            )}

            {/* Forensic Heatmap Artifact (if generated) */}
            {forensics?.artifacts?.heatmapUrl && (
              <div className="rounded-md border border-slate-200 p-3 bg-slate-50 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-700">Composite Tamper Heatmap</span>
                  <button
                    type="button"
                    onClick={() => setShowHeatmap(!showHeatmap)}
                    className="text-xs font-medium text-brand-600 hover:text-brand-800"
                  >
                    {showHeatmap ? 'Hide Heatmap' : 'Show Heatmap'}
                  </button>
                </div>
                {showHeatmap && (
                  <div className="relative overflow-hidden rounded border border-slate-300 bg-black flex justify-center">
                    <img
                      src={forensics.artifacts.heatmapUrl}
                      alt="Tamper Heatmap"
                      className="max-h-72 object-contain"
                    />
                  </div>
                )}
              </div>
            )}

            {/* Multi-Detector Signal Breakdown */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Independent Forensic Detectors ({detectors.length})
              </h4>
              <ul className="space-y-2">
                {detectors.map((d: any, i: number) => {
                  const detectorName = d.detector || d.detectorName || `Detector ${i + 1}`;
                  const score = d.score;
                  const tag = d.tag || (score && score > 0.5 ? 'EVIDENCE' : 'CLEAR');

                  return (
                    <li key={i} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-slate-700">
                          {detectorName.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
                        </span>
                        <div className="flex items-center gap-2">
                          {score !== null && score !== undefined && (
                            <span className="font-mono text-xs text-slate-500">
                              score: {typeof score === 'number' ? score.toFixed(4) : score}
                            </span>
                          )}
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            tag === 'STRONG' || tag === 'PROVEN'
                              ? 'bg-purple-100 text-purple-700'
                              : tag === 'EXPERIMENTAL'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-slate-200 text-slate-700'
                          }`}>
                            {tag}
                          </span>
                        </div>
                      </div>
                      {d.notes && d.notes.length > 0 && (
                        <p className="mt-1 text-xs text-slate-500 italic">
                          {d.notes.join(' • ')}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </>
        )}
      </div>

      <button className="btn-primary w-full" onClick={onProtectAnother}>
        Protect another image
      </button>
    </div>
  );
}
