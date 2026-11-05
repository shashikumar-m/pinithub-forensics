import ConsentStep from '../components/ConsentStep';
import CaptureCamera from '../components/CaptureCamera';
import UploadBox from '../components/UploadBox';
import ProgressState from '../components/ProgressState';
import UploadSuccessCard from '../components/UploadSuccessCard';
import { useProtectFlow } from '../hooks/useProtectFlow';

/**
 * Protect page — guides the user through the full image protection workflow.
 *
 * Steps:
 *   1. CONSENT_REQUIRED — user must read and consent
 *   2. CAPTURING / UPLOADING — source selection driven by consent choice
 *   3. PROTECTING — backend pipeline (validate, hash, store, record)
 *   4. PROTECTED — success with real image details
 *   5. FAILED — clean error with actionable message
 *
 * Both camera and upload paths feed the same backend /v1/uploads pipeline.
 * No fake forensic results are shown at any point.
 */
export default function Protect() {
  const { step, error, result, handleConsent, protect, reset } = useProtectFlow();

  return (
    <div className="container-page">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-slate-900">Protect an Image</h1>
        <p className="mt-1 text-sm text-slate-600">
          Register an original image in the forensic vault. The file is stored unchanged
          with a verified SHA-256 hash.
        </p>
      </div>

      {/* Step indicator */}
      <StepIndicator step={step} />

      <div className="mt-6">
        {/* Step 1 — Consent */}
        {step === 'CONSENT_REQUIRED' && (
          <ConsentStep onConsent={handleConsent} />
        )}

        {/* Step 2a — Camera capture */}
        {step === 'CAPTURING' && (
          <div className="mx-auto max-w-2xl">
            <h2 className="mb-4 text-lg font-semibold text-slate-800">Take a photo</h2>
            <CaptureCamera
              onCapture={(file, captureTimestamp) =>
                protect(file, 'CAMERA_CAPTURE', captureTimestamp)
              }
              onCancel={reset}
            />
          </div>
        )}

        {/* Step 2b — File upload */}
        {step === 'UPLOADING' && (
          <div className="mx-auto max-w-2xl">
            <h2 className="mb-4 text-lg font-semibold text-slate-800">Upload an image</h2>
            <UploadBox onFile={(file) => protect(file, 'FILE_UPLOAD')} />
            <div className="mt-4">
              <button className="btn-secondary text-sm" onClick={reset}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {/* Step 3 — Processing */}
        {step === 'PROTECTING' && <ProgressState step="PROTECTING" />}

        {/* Step 4 — Success */}
        {step === 'PROTECTED' && result && (
          <UploadSuccessCard result={result} onProtectAnother={reset} />
        )}

        {/* Step 5 — Failure */}
        {step === 'FAILED' && (
          <div className="mx-auto max-w-2xl">
            <div className="card border-red-200 bg-red-50">
              <h2 className="text-lg font-semibold text-red-800">Protection failed</h2>
              <p className="mt-2 text-sm text-red-700">
                {error?.message ?? 'An unexpected error occurred.'}
              </p>
              {error?.code && (
                <p className="mt-1 font-mono text-xs text-red-500">{error.code}</p>
              )}
              <button className="btn-primary mt-4" onClick={reset}>
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function StepIndicator({ step }: { step: string }) {
  const steps = [
    { id: 'CONSENT_REQUIRED', label: 'Consent' },
    { id: 'UPLOADING,CAPTURING', label: 'Select image' },
    { id: 'PROTECTING', label: 'Protecting' },
    { id: 'PROTECTED,FAILED', label: 'Done' },
  ];

  const currentIndex = steps.findIndex((s) => s.id.split(',').includes(step));

  return (
    <ol className="flex items-center gap-2" aria-label="Protection progress">
      {steps.map((s, i) => {
        const active = s.id.split(',').includes(step);
        const done = i < currentIndex;
        return (
          <li key={s.id} className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                active
                  ? 'bg-brand-600 text-white'
                  : done
                  ? 'bg-green-500 text-white'
                  : 'bg-slate-200 text-slate-500'
              }`}
            >
              {done ? '✓' : i + 1}
            </span>
            <span
              className={`hidden text-xs sm:inline ${
                active ? 'font-medium text-brand-700' : 'text-slate-400'
              }`}
            >
              {s.label}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 text-slate-300">›</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
