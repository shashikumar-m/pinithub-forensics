/**
 * HeatmapViewer — displays evidence heatmaps and region masks.
 *
 * Phase 0: placeholder only. No heatmap is generated yet — this
 * would require the detector pipeline from later phases.
 * Never shows fabricated heatmap data.
 */
export default function HeatmapViewer() {
  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-slate-900">Evidence Heatmap</h2>
      <div className="mt-4 flex h-48 items-center justify-center rounded-lg bg-slate-50">
        <div className="text-center">
          <svg className="mx-auto h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19V6l12-3v13M9 19c0 1.657-1.343 3-3 3s-3-1.343-3-3 1.343-3 3-3 3 1.343 3 3zm12-3c0 1.657-1.343 3-3 3s-3-1.343-3-3 1.343-3 3-3 3 1.343 3 3z" />
          </svg>
          <p className="mt-2 text-xs text-slate-400">No heatmap available</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-slate-400">
        Heatmap generation requires the detector pipeline, which is not yet implemented.
      </p>
    </div>
  );
}
