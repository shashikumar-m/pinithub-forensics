/**
 * ReportViewer — displays a tamper-evident forensic report.
 *
 * Phase 0: structural placeholder. Report generation and tamper-evident
 * sealing are planned for later phases. Never shows a fabricated report.
 */
export default function ReportViewer() {
  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-slate-900">Forensic Report</h2>
      <div className="mt-4 flex flex-col items-center justify-center py-8">
        <svg className="h-10 w-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="mt-3 text-sm text-slate-400">No report available</p>
        <p className="mt-1 text-xs text-slate-400">
          Report generation requires a completed forensic analysis.
        </p>
      </div>
    </div>
  );
}
