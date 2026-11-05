import { useState } from 'react';
import { useImages } from '../api/images';
import { useCreateComparison, useComparison, useComparisonRegions, useDeleteComparison } from '../api/comparisons';
import type { ComparisonRecord } from '@pinithub/shared';
import UploadBox from './UploadBox';
import ProgressState from './ProgressState';
import { useUploadImage } from '../api/uploads';
import CropAnalysis from './CropAnalysis';
import TravelAnalysisPanel from './TravelAnalysisPanel';

const STATUS_COLORS: Record<string, string> = {
  QUEUED: 'bg-amber-100 text-amber-700',
  RUNNING: 'bg-blue-100 text-blue-700',
  MATCHING: 'bg-blue-100 text-blue-700',
  REGISTERING: 'bg-blue-100 text-blue-700',
  COMPARING: 'bg-blue-100 text-blue-700',
  COMPLETED: 'bg-green-100 text-green-700',
  FAILED: 'bg-red-100 text-red-700',
  NO_MATCH: 'bg-orange-100 text-orange-700',
  INCONCLUSIVE: 'bg-amber-100 text-amber-700',
};

/**
 * InvestigationCompare — Phase 4 comparison workflow.
 *
 * 1. Select a protected original
 * 2. Upload a suspect copy
 * 3. Start comparison
 * 4. Show real registration evidence
 * 5. Show difference analysis
 * 6. Show candidate changed regions
 *
 * No final manipulation verdict is shown.
 */
export default function InvestigationCompare() {
  const [referenceId, setReferenceId] = useState<string | null>(null);
  const [suspectId, setSuspectId] = useState<string | null>(null);
  const [comparisonId, setComparisonId] = useState<string | null>(null);

  const { data: images } = useImages(1, 50);
  const uploadSuspect = useUploadImage();
  const createComparison = useCreateComparison();
  const { data: comparisonData } = useComparison(comparisonId);
  const { data: regionsData } = useComparisonRegions(comparisonId);
  const deleteComparison = useDeleteComparison();

  const comparison = comparisonData?.comparison as ComparisonRecord | undefined;

  const isRunning = comparison
    ? ['QUEUED', 'RUNNING', 'MATCHING', 'REGISTERING', 'COMPARING'].includes(comparison.status)
    : false;

  function handleSuspectFile(file: File) {
    uploadSuspect.mutate(
      { file, role: 'SUSPECT' },
      {
        onSuccess: (res) => {
          setSuspectId(res.image.id);
        },
      },
    );
  }

  async function startComparison() {
    if (!referenceId || !suspectId) return;
    createComparison.mutate(
      { referenceImageId: referenceId, suspectImageId: suspectId },
      { onSuccess: (res) => setComparisonId(res.comparison.id) },
    );
  }

  return (
    <div className="space-y-6">
      {/* Step 1 + 2: Select images */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Reference selection */}
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            1. Select protected original
          </h3>
          {images && images.items.length > 0 ? (
            <select
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              value={referenceId ?? ''}
              onChange={(e) => setReferenceId(e.target.value || null)}
            >
              <option value="">— Select original —</option>
              {images.items
                .filter((img) => img.role === 'ORIGINAL')
                .map((img) => (
                  <option key={img.id} value={img.id}>
                    {img.originalFilename} ({img.width}×{img.height})
                  </option>
                ))}
            </select>
          ) : (
            <p className="text-sm text-slate-400">No protected originals found. Protect an image first.</p>
          )}
          {referenceId && (
            <p className="mt-1 font-mono text-xs text-slate-400 truncate">{referenceId}</p>
          )}
        </div>

        {/* Suspect upload */}
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            2. Upload suspect copy
          </h3>
          {suspectId ? (
            <div>
              <p className="text-sm text-green-700">✓ Suspect uploaded</p>
              <p className="mt-0.5 font-mono text-xs text-slate-400 truncate">{suspectId}</p>
              <button
                className="btn-secondary mt-2 text-xs"
                onClick={() => setSuspectId(null)}
              >
                Replace
              </button>
            </div>
          ) : (
            <UploadBox onFile={handleSuspectFile} />
          )}
          {uploadSuspect.isPending && (
            <p className="mt-2 text-sm text-blue-600">Uploading suspect…</p>
          )}
        </div>
      </div>

      {/* Start comparison */}
      <div className="flex items-center gap-3">
        <button
          className="btn-primary"
          disabled={!referenceId || !suspectId || createComparison.isPending || isRunning}
          onClick={startComparison}
        >
          {createComparison.isPending ? 'Starting…' : 'Start comparison'}
        </button>
        {comparison && (
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${STATUS_COLORS[comparison.status] ?? 'bg-slate-100 text-slate-500'}`}>
            {comparison.status}
          </span>
        )}
      </div>

      {/* Running state */}
      {isRunning && <ProgressState step="PROTECTING" />}

      {/* Results */}
      {comparison && !isRunning && (
        <>
          <ComparisonResults comparison={comparison} regions={regionsData?.regions ?? []} />
          {comparison.status === 'COMPLETED' && (
            <>
              <CropAnalysis comparisonId={comparison.id} />
              <TravelAnalysisPanel comparisonId={comparison.id} />
            </>
          )}
          {/* Delete comparison */}
          <div className="flex justify-end">
            <button
              className="text-xs text-red-500 hover:text-red-700"
              onClick={() => {
                if (window.confirm('Delete this comparison and all its results?')) {
                  deleteComparison.mutate(comparison.id, {
                    onSuccess: () => setComparisonId(null),
                  });
                }
              }}
            >
              🗑 Delete comparison
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function ComparisonResults({ comparison, regions }: {
  comparison: ComparisonRecord;
  regions: any[];
}) {
  const [showDetails, setShowDetails] = useState(false);
  const status = comparison.status;

  return (
    <div className="space-y-4">
      {/* Notice banner */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
        <p className="text-sm text-blue-800">
          <strong>Registration evidence only.</strong>{' '}
          {status === 'COMPLETED'
            ? 'Registration succeeded and difference analysis was performed.'
            : status === 'NO_MATCH'
            ? 'These images could not be reliably matched. They may be unrelated.'
            : status === 'INCONCLUSIVE'
            ? 'Registration quality was insufficient for reliable comparison.'
            : `Status: ${status}`}
          {' '}No final authenticity verdict is produced.
        </p>
      </div>

      {/* Registration summary */}
      <div className="card">
        <h3 className="mb-3 text-sm font-semibold text-slate-700">Registration</h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">Status</dt>
          <dd className={`font-medium ${status === 'COMPLETED' ? 'text-green-700' : status === 'NO_MATCH' ? 'text-orange-700' : 'text-amber-700'}`}>
            {status}
          </dd>
          <dt className="text-slate-500">Detector</dt>
          <dd className="text-slate-800">{comparison.detectorUsed ?? '—'} v{comparison.detectorVersion ?? '—'}</dd>
          <dt className="text-slate-500">Keypoints (ref/sus)</dt>
          <dd className="text-slate-800">{comparison.keypointsReference ?? '—'} / {comparison.keypointsSuspect ?? '—'}</dd>
          <dt className="text-slate-500">Good matches</dt>
          <dd className="text-slate-800">{comparison.goodMatches ?? '—'}</dd>
          <dt className="text-slate-500">Inliers</dt>
          <dd className="text-slate-800">{comparison.inlierCount ?? '—'}</dd>
          <dt className="text-slate-500">Inlier ratio</dt>
          <dd className="text-slate-800">{comparison.inlierRatio != null ? comparison.inlierRatio.toFixed(3) : '—'}</dd>
          <dt className="text-slate-500">Reprojection error</dt>
          <dd className="text-slate-800">{comparison.reprojectionError != null ? `${comparison.reprojectionError.toFixed(2)}px` : '—'}</dd>
          <dt className="text-slate-500">Overlap ratio</dt>
          <dd className="text-slate-800">{comparison.overlapRatio != null ? `${(comparison.overlapRatio * 100).toFixed(1)}%` : '—'}</dd>
          <dt className="text-slate-500">Exec time</dt>
          <dd className="text-slate-800">{comparison.executionTimeMs != null ? `${comparison.executionTimeMs}ms` : '—'}</dd>
        </dl>
        <button
          className="btn-secondary mt-3 text-xs"
          onClick={() => setShowDetails(!showDetails)}
        >
          {showDetails ? 'Hide' : 'Show'} technical details
        </button>
        {showDetails && comparison.homographyMatrix && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-semibold text-slate-500">Homography matrix</p>
            <pre className="overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-600">
              {JSON.stringify(comparison.homographyMatrix, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* Difference analysis */}
      {status === 'COMPLETED' && (
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">Difference Analysis</h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-500">Mean absolute diff</dt>
            <dd className="text-slate-800">{comparison.meanAbsDiff != null ? comparison.meanAbsDiff.toFixed(4) : '—'}</dd>
            <dt className="text-slate-500">SSIM score</dt>
            <dd className="text-slate-800">{comparison.ssimScore != null ? comparison.ssimScore.toFixed(4) : '—'}</dd>
          </dl>
          <p className="mt-2 text-xs italic text-slate-400">
            Differences due to JPEG compression, resize, brightness changes are expected and
            do not indicate manipulation.
          </p>
        </div>
      )}

      {/* Candidate regions */}
      {regions.length > 0 && (
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-slate-700">
            Candidate Changed Regions ({regions.length})
          </h3>
          <p className="mb-3 text-xs text-amber-700">
            These are candidate regions from difference analysis only — not classified as
            edits. Future phases will analyze these further.
          </p>
          <ul className="space-y-2">
            {regions.slice(0, 10).map((r, i) => (
              <li key={r.id} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-xs">
                <span className="text-slate-600">
                  Region {i + 1}: {r.bbox.width}×{r.bbox.height} at ({r.bbox.x}, {r.bbox.y})
                </span>
                <span className="text-slate-500">
                  {r.areaPercent?.toFixed(2)}% of image
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warnings */}
      {comparison.warnings && (comparison.warnings as string[]).length > 0 && (
        <div className="card border-amber-200 bg-amber-50">
          <h3 className="mb-2 text-xs font-semibold text-amber-800">Warnings</h3>
          <ul className="list-inside list-disc space-y-1 text-xs text-amber-700">
            {(comparison.warnings as string[]).map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
