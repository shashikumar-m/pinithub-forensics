import { useState } from 'react';
import { CONSENT_VERSION, POLICY_VERSION } from '../hooks/useProtectFlow';
import type { ImageSource } from '@pinithub/shared';

interface Props {
  onConsent: (sourceType: ImageSource) => void;
}

/**
 * ConsentStep — captures explicit user consent before image processing.
 *
 * The consent text is driven by CONSENT_VERSION / POLICY_VERSION constants
 * so it can be updated without rewriting the component.
 *
 * We do NOT make legal claims on behalf of PinITHUB — the text describes
 * what will technically happen to the image.
 */
export default function ConsentStep({ onConsent }: Props) {
  const [checked, setChecked] = useState(false);
  const [pendingSource, setPendingSource] = useState<ImageSource | null>(null);

  function handleProceed() {
    if (!checked || !pendingSource) return;
    onConsent(pendingSource);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="card space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">Before you continue</h2>
          <p className="mt-1 text-xs text-slate-400">
            Consent v{CONSENT_VERSION} · Policy {POLICY_VERSION}
          </p>
        </div>

        <div className="space-y-3 text-sm text-slate-600">
          <p>
            You are about to protect an image using PINITHUB Forensics. Please read the
            following carefully before proceeding:
          </p>
          <ul className="list-inside list-disc space-y-2 pl-2">
            <li>
              Your image will be uploaded to secure private storage and will{' '}
              <strong>not be publicly accessible</strong>.
            </li>
            <li>
              A <strong>SHA-256 cryptographic hash</strong> of the exact original file bytes
              will be computed and stored to verify future integrity.
            </li>
            <li>
              Basic image information (dimensions, format, file size) will be recorded.
            </li>
            <li>
              Image metadata (EXIF) analysis will be performed in a later phase of the
              forensic pipeline.
            </li>
            <li>
              If your image contains <strong>GPS location data</strong>, the location value
              will not be logged or displayed — only the presence or absence of GPS data is
              noted.
            </li>
            <li>
              Your image data is <strong>owner-scoped</strong> — other users cannot access
              your protected images.
            </li>
            <li>
              The original file is stored <strong>byte-for-byte unchanged</strong>. It will
              not be resized, recompressed, or converted.
            </li>
          </ul>
        </div>

        <div>
          <h3 className="mb-2 text-sm font-medium text-slate-700">
            How will you provide your image?
          </h3>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setPendingSource('FILE_UPLOAD')}
              className={`flex-1 rounded-lg border-2 px-4 py-3 text-sm font-medium transition-colors ${
                pendingSource === 'FILE_UPLOAD'
                  ? 'border-brand-600 bg-brand-50 text-brand-700'
                  : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
              }`}
            >
              📁 Upload a file
            </button>
            <button
              type="button"
              onClick={() => setPendingSource('CAMERA_CAPTURE')}
              className={`flex-1 rounded-lg border-2 px-4 py-3 text-sm font-medium transition-colors ${
                pendingSource === 'CAMERA_CAPTURE'
                  ? 'border-brand-600 bg-brand-50 text-brand-700'
                  : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
              }`}
            >
              📷 Take a photo
            </button>
          </div>
        </div>

        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          />
          <span className="text-sm text-slate-700">
            I have read the above information and I consent to my image being processed for
            forensic analysis purposes.
          </span>
        </label>

        <button
          type="button"
          onClick={handleProceed}
          disabled={!checked || !pendingSource}
          className="btn-primary w-full disabled:opacity-40"
        >
          Continue
        </button>
      </div>
    </div>
  );
}
