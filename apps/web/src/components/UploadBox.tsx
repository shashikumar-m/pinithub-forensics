import { useState, useCallback, useRef } from 'react';

// Max size shown in the UI — actual enforcement is server-side
const MAX_MB = parseInt(import.meta.env.VITE_MAX_UPLOAD_MB ?? '25', 10);
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp'];

interface Props {
  /** Called with the validated file when ready to protect. */
  onFile: (file: File) => void;
  disabled?: boolean;
}

/**
 * UploadBox — drag-and-drop or file-select upload.
 *
 * Performs client-side pre-validation (type, size, extension) for UX only.
 * The server is the security boundary — all validation is repeated server-side.
 *
 * Source is FILE_UPLOAD. Does not modify the file before passing it on.
 */
export default function UploadBox({ onFile, disabled = false }: Props) {
  const [dragging, setDragging] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function validate(file: File): string | null {
    // Extension check (UX only — not security)
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Unsupported file extension "${ext}". Supported: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }
    // MIME check (UX only — not security)
    if (!ALLOWED_TYPES.includes(file.type)) {
      return `Unsupported file type "${file.type}". Supported: JPEG, PNG, WebP`;
    }
    // Size pre-check (UX only — server enforces the real limit)
    if (file.size > MAX_MB * 1024 * 1024) {
      return `File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum is ${MAX_MB} MB.`;
    }
    return null;
  }

  const handleFile = useCallback(
    (file: File) => {
      setClientError(null);
      const err = validate(file);
      if (err) {
        setClientError(err);
        return;
      }
      onFile(file);
    },
    [onFile],
  );

  return (
    <div className="space-y-3">
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload image area"
        className={`relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 transition-colors ${
          disabled
            ? 'cursor-not-allowed border-slate-200 bg-slate-50 opacity-60'
            : dragging
            ? 'border-brand-500 bg-brand-50 cursor-copy'
            : 'border-slate-300 bg-white cursor-pointer hover:border-brand-400 hover:bg-brand-50'
        }`}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !disabled && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (disabled) return;
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
      >
        <svg className="h-12 w-12 text-slate-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-sm font-medium text-slate-700">Drag and drop an image here</p>
        <p className="mt-1 text-xs text-slate-400">or click to browse</p>
        <p className="mt-2 text-xs text-slate-400">
          JPEG · PNG · WebP &nbsp;·&nbsp; max {MAX_MB} MB
        </p>

        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_TYPES.join(',')}
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            // Reset so the same file can be re-selected
            e.target.value = '';
          }}
        />
      </div>

      {clientError && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {clientError}
        </p>
      )}

      <p className="text-xs text-slate-400">
        Client-side validation is for convenience only. All files are re-validated
        server-side.
      </p>
    </div>
  );
}
