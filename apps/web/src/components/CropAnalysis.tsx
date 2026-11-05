import { useCropDetection, useTriggerCropDetection } from '../api/comparisons';
import type { CropDetectionDBRecord } from '@pinithub/shared';

interface Props {
  comparisonId: string;
}

const STATUS_COLORS: Record<string, string> = {
  DETECTED: 'bg-amber-100 text-amber-800',
  NO_CROP: 'bg-green-100 text-green-700',
  NO_MATCH: 'bg-orange-100 text-orange-700',
  INCONCLUSIVE: 'bg-slate-100 text-slate-600',
  FAILED: 'bg-red-100 text-red-700',
  QUEUED: 'bg-blue-100 text-blue-700',
  NOT_RUN: 'bg-slate-100 text-slate-400',
};

/**
 * CropAnalysis — Phase 5 crop percentage detection display.
 *
 * Shows:
 * - Crop status
 * - Crop percentage (% of original removed)
 * - Kept percentage
 * - Confidence (UNCALIBRATED)
 * - Registration quality evidence
 * - Crop polygon footprint (SVG overlay)
 *
 * Does NOT show a final authenticity verdict.
 * Clearly distinguishes "crop %" from "difference %".
 */
export default function CropAnalysis({ comparisonId }: Props) {
  const { data, isLoading, refetch } = useCropDetection(comparisonId);
  const trigger = useTriggerCropDetection();

  const notRun = !data || ('status' in data && (data as any).status === 'NOT_RUN');
  const cropData = !notRun && 'cropDetection' in data
    ? (data as any).cropDetection as CropDetectionDBRecord
    : null;

  if (isLoading) {
    return (
      <div className="card">
        <h3 className="text-sm font-semibold text-slate-700">Crop Analysis</h3>
        <p className="mt-2 text-sm text-slate-400">Loading…</p>
      </div>
    );
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Crop Analysis</h3>
        {notRun && (
          <button
            className="btn-primary text-xs"
            disabled={trigger.isPending}
            onClick={() => trigger.mutate(comparisonId, {
              onSuccess: () => setTimeout(() => refetch(), 2000),
            })}
          >
            {trigger.isPending ? 'Starting…' : 'Detect crop'}
          </button>
        )}
      </div>

      {notRun && (
        <p className="text-sm text-slate-400">
          Crop detection has not been run. Click "Detect crop" to analyze.
        </p>
      )}

      {cropData && (
        <>
          {/* Status */}
          <div className="flex items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[cropData.status] ?? 'bg-slate-100'}`}>
              {cropData.status}
            </span>
            {cropData.status === 'DETECTED' && (
              <span className="text-sm text-amber-700 font-medium">
                {cropData.cropPercentage?.toFixed(2)}% of original removed
              </span>
            )}
            {cropData.status === 'NO_CROP' && (
              <span className="text-sm text-green-700">No significant crop detected</span>
            )}
            {cropData.status === 'INCONCLUSIVE' && (
              <span className="text-sm text-slate-500">
                Insufficient evidence to determine crop percentage
              </span>
            )}
            {cropData.status === 'NO_MATCH' && (
              <span className="text-sm text-orange-700">
                Images could not be matched — crop cannot be determined
              </span>
            )}
          </div>

          {/* Measurements */}
          {(cropData.status === 'DETECTED' || cropData.status === 'NO_CROP') && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-500">Crop removed</dt>
              <dd className="font-medium text-slate-800">
                {cropData.cropPercentage != null ? `${cropData.cropPercentage.toFixed(2)}%` : '—'}
              </dd>
              <dt className="text-slate-500">Original kept</dt>
              <dd className="font-medium text-slate-800">
                {cropData.keptPercentage != null ? `${cropData.keptPercentage.toFixed(2)}%` : '—'}
              </dd>
              <dt className="text-slate-500">Original area</dt>
              <dd className="font-medium text-slate-800">
                {cropData.originalAreaPixels.toLocaleString()} px
              </dd>
              <dt className="text-slate-500">Kept area</dt>
              <dd className="font-medium text-slate-800">
                {cropData.keptAreaPixels != null ? `${cropData.keptAreaPixels.toLocaleString()} px` : '—'}
              </dd>
              <dt className="text-slate-500">Confidence</dt>
              <dd className="text-slate-600">
                {cropData.confidence != null
                  ? `${(cropData.confidence * 100).toFixed(1)}% (UNCALIBRATED)`
                  : '—'}
              </dd>
              <dt className="text-slate-500">Method</dt>
              <dd className="text-slate-600 text-xs">{cropData.method ?? '—'}</dd>
              <dt className="text-slate-500">Detector</dt>
              <dd className="text-slate-600 text-xs">
                {cropData.detectorName} v{cropData.detectorVersion}
              </dd>
              <dt className="text-slate-500">Exec time</dt>
              <dd className="text-slate-600">{cropData.executionMs}ms</dd>
            </dl>
          )}

          {/* Crop footprint diagram */}
          {cropData.status === 'DETECTED' && cropData.cropPolygon && cropData.boundingBox && (
            <CropFootprint
              polygon={cropData.cropPolygon as Array<{ x: number; y: number }>}
              boundingBox={cropData.boundingBox as { x: number; y: number; width: number; height: number }}
              cropPct={cropData.cropPercentage ?? 0}
              keptPct={cropData.keptPercentage ?? 0}
            />
          )}

          {/* Registration quality */}
          {cropData.registrationQuality && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-700">
                Registration quality
              </summary>
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                {Object.entries(cropData.registrationQuality as unknown as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <dt className="text-slate-400">{k}</dt>
                    <dd className="text-slate-600">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            </details>
          )}

          {/* Warnings */}
          {cropData.warnings && (cropData.warnings as string[]).length > 0 && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-2">
              <ul className="space-y-0.5 text-xs text-amber-700">
                {(cropData.warnings as string[]).map((w, i) => (
                  <li key={i}>⚠ {w}</li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-xs italic text-slate-400">
            Crop % = area of original removed. All coordinates are in original image space.
            This is NOT an authenticity verdict.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * SVG-based crop footprint visualization.
 * Shows the kept region (polygon) overlaid on a representation of the original image.
 */
function CropFootprint({ polygon, boundingBox, cropPct, keptPct }: {
  polygon: Array<{ x: number; y: number }>;
  boundingBox: { x: number; y: number; width: number; height: number };
  cropPct: number;
  keptPct: number;
}) {
  // Normalize all coords to a 200×200 SVG viewport using bounding box max
  const allX = polygon.map((p) => p.x);
  const allY = polygon.map((p) => p.y);
  const maxX = Math.max(...allX, boundingBox.x + boundingBox.width);
  const maxY = Math.max(...allY, boundingBox.y + boundingBox.height);
  const svgW = 200;
  const svgH = 160;
  const scaleX = maxX > 0 ? svgW / maxX : 1;
  const scaleY = maxY > 0 ? svgH / maxY : 1;
  const scale = Math.min(scaleX, scaleY) * 0.9;

  const points = polygon
    .map((p) => `${(p.x * scale + 5).toFixed(1)},${(p.y * scale + 5).toFixed(1)}`)
    .join(' ');

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        Crop Footprint (original image coordinates)
      </p>
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
        <svg
          width={svgW + 10}
          height={svgH + 10}
          viewBox={`0 0 ${svgW + 10} ${svgH + 10}`}
          aria-label="Crop footprint showing kept region"
        >
          {/* Original image boundary */}
          <rect x="5" y="5" width={svgW} height={svgH}
            fill="#f0f4ff" stroke="#cbd5e1" strokeWidth="1" />
          {/* Removed area (cross-hatched) */}
          <rect x="5" y="5" width={svgW} height={svgH}
            fill="url(#hatch)" opacity="0.5" />
          {/* Kept/visible region polygon */}
          <polygon points={points}
            fill="#3b82f6" fillOpacity="0.2"
            stroke="#2563eb" strokeWidth="1.5"
            strokeDasharray="none" />
          {/* Labels */}
          <text x="50%" y={svgH / 2 - 8} textAnchor="middle" fontSize="9" fill="#64748b">
            KEPT REGION
          </text>
          <text x="50%" y={svgH / 2 + 4} textAnchor="middle" fontSize="9" fill="#2563eb" fontWeight="bold">
            {keptPct.toFixed(1)}%
          </text>

          {/* Hatch pattern for removed area */}
          <defs>
            <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="8" stroke="#cbd5e1" strokeWidth="1" />
            </pattern>
          </defs>
        </svg>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-blue-600 font-medium">■ Kept: {keptPct.toFixed(2)}%</span>
        <span className="text-slate-500">░ Removed: {cropPct.toFixed(2)}%</span>
      </div>
    </div>
  );
}
