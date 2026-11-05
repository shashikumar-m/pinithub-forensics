import MetadataPanel from './MetadataPanel';

/**
 * VaultCard — displays a protected original image and its sealed record.
 * Phase 0: structural placeholder with no fake forensic values.
 * When real data is available, this component receives an ImageRecord.
 */
export default function VaultCard() {
  return (
    <div className="card">
      {/* Image preview placeholder */}
      <div className="mb-4 flex h-32 items-center justify-center rounded-md bg-slate-100">
        <svg className="h-8 w-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>

      {/* Metadata — empty state, no fabricated values */}
      <MetadataPanel />

      {/* Sealed record indicator */}
      <div className="mt-3 flex items-center gap-2 rounded-md bg-slate-50 px-3 py-2">
        <svg className="h-4 w-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <span className="text-xs text-slate-500">Sealed record</span>
      </div>
    </div>
  );
}
