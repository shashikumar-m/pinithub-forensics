import InvestigationCompare from '../components/InvestigationCompare';

/**
 * Investigation page — Phase 4 + 5 + 7.
 * Reference comparison, crop detection, and travel analysis.
 * No final authenticity verdict is produced.
 */
export default function Investigation() {
  return (
    <div className="container-page">
      <h1 className="text-2xl font-bold text-slate-900">Investigation</h1>
      <p className="mt-1 text-sm text-slate-600">
        Compare a protected original against a suspect copy. Registration, difference
        analysis, crop detection, and travel analysis are shown as forensic signals — not a final verdict.
      </p>

      <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
        <p className="text-sm text-amber-800">
          <strong>Phase 4–7 — Reference Comparison, Crop &amp; Travel Analysis.</strong>{' '}
          Transport transformations (compression, resize, metadata strip) are benign platform
          behaviours — NOT content manipulation evidence.
        </p>
      </div>

      <div className="mt-8">
        <InvestigationCompare />
      </div>
    </div>
  );
}
