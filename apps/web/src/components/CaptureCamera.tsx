import { useRef, useState, useEffect, useCallback } from 'react';

interface Props {
  /** Called with the captured file when user confirms. */
  onCapture: (file: File, captureTimestamp: string) => void;
  /** Called when user cancels/goes back. */
  onCancel: () => void;
}

type CameraState =
  | 'IDLE'
  | 'REQUESTING'
  | 'LIVE'
  | 'CAPTURED'
  | 'DENIED'
  | 'UNAVAILABLE'
  | 'UNSUPPORTED';

/**
 * CaptureCamera — one-shot camera capture component.
 *
 * Flow: IDLE → REQUESTING → LIVE → CAPTURED → (confirm → onCapture)
 *                                            → (retake  → LIVE)
 *
 * Does NOT run continuous video analysis.
 * Does NOT upload video frames.
 * The captured image is treated as a normal image file after capture.
 *
 * Source is recorded as CAMERA_CAPTURE — this does NOT prove the image
 * is an unedited camera original. Forensic analysis determines that.
 */
export default function CaptureCamera({ onCapture, onCancel }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [state, setState] = useState<CameraState>('IDLE');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [capturedFile, setCapturedFile] = useState<File | null>(null);
  const [captureTimestamp, setCaptureTimestamp] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Stop stream on unmount
  useEffect(() => {
    return () => stopStream();
  }, []);

  function stopStream() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t: MediaStreamTrack) => t.stop());
      streamRef.current = null;
    }
  }

  const startCamera = useCallback(async () => {
    setErrorMessage(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setState('UNSUPPORTED');
      return;
    }

    setState('REQUESTING');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setState('LIVE');
    } catch (err: unknown) {
      const name = err instanceof Error ? (err as any).name : '';
      if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setState('DENIED');
        setErrorMessage('Camera permission was denied. Please allow camera access in your browser settings.');
      } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setState('UNAVAILABLE');
        setErrorMessage('No camera found on this device.');
      } else if (name === 'NotReadableError') {
        setState('UNAVAILABLE');
        setErrorMessage('Camera is in use by another application.');
      } else {
        setState('UNAVAILABLE');
        setErrorMessage('Camera could not be started.');
      }
    }
  }, []);

  const capture = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);

    const ts = new Date().toISOString();
    setCaptureTimestamp(ts);

    canvas.toBlob((blob) => {
      if (!blob) {
        setErrorMessage('Failed to capture image from camera.');
        return;
      }
      const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
      const url = URL.createObjectURL(blob);

      // Stop live stream once captured
      stopStream();

      setPreviewUrl(url);
      setCapturedFile(file);
      setState('CAPTURED');
    }, 'image/jpeg', 0.92);
  }, []);

  const retake = useCallback(() => {
    // Clean up preview URL to free memory
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setCapturedFile(null);
    setCaptureTimestamp(null);
    setState('IDLE');
    startCamera();
  }, [previewUrl, startCamera]);

  const confirm = useCallback(() => {
    if (!capturedFile || !captureTimestamp) return;
    onCapture(capturedFile, captureTimestamp);
  }, [capturedFile, captureTimestamp, onCapture]);

  const cancel = useCallback(() => {
    stopStream();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    onCancel();
  }, [previewUrl, onCancel]);

  return (
    <div className="space-y-4">
      {/* Error states */}
      {(state === 'DENIED' || state === 'UNAVAILABLE' || state === 'UNSUPPORTED') && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-700">Camera unavailable</p>
          <p className="mt-1 text-sm text-red-600">{errorMessage}</p>
          <div className="mt-3 flex gap-2">
            <button className="btn-secondary text-xs" onClick={onCancel}>
              ← Go back
            </button>
            {state !== 'UNSUPPORTED' && (
              <button className="btn-primary text-xs" onClick={startCamera}>
                Try again
              </button>
            )}
          </div>
        </div>
      )}

      {/* Idle — start prompt */}
      {state === 'IDLE' && (
        <div className="flex flex-col items-center gap-4 rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 py-12">
          <svg className="h-12 w-12 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <p className="text-sm text-slate-500">Tap below to open your camera</p>
          <div className="flex gap-3">
            <button className="btn-secondary" onClick={cancel}>Cancel</button>
            <button className="btn-primary" onClick={startCamera}>Open camera</button>
          </div>
        </div>
      )}

      {/* Requesting */}
      {state === 'REQUESTING' && (
        <div className="flex flex-col items-center gap-4 rounded-lg border border-slate-200 bg-white py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-brand-600" />
          <p className="text-sm text-slate-500">Requesting camera access…</p>
        </div>
      )}

      {/* Live preview */}
      {state === 'LIVE' && (
        <div className="space-y-3">
          <div className="overflow-hidden rounded-lg bg-black">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full"
              style={{ maxHeight: 400, objectFit: 'cover' }}
            />
          </div>
          <div className="flex justify-between">
            <button className="btn-secondary" onClick={cancel}>Cancel</button>
            <button className="btn-primary" onClick={capture}>
              📸 Capture photo
            </button>
          </div>
        </div>
      )}

      {/* Captured — confirm or retake */}
      {state === 'CAPTURED' && previewUrl && (
        <div className="space-y-3">
          <p className="text-sm font-medium text-slate-700">Review your photo</p>
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <img
              src={previewUrl}
              alt="Captured photo preview"
              className="w-full object-cover"
              style={{ maxHeight: 400 }}
            />
          </div>
          {captureTimestamp && (
            <p className="text-xs text-slate-400">
              Captured at {new Date(captureTimestamp).toLocaleString()}
            </p>
          )}
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            Recording source as <strong>CAMERA_CAPTURE</strong>. This indicates how the
            image entered the system — forensic analysis of authenticity happens in later
            phases.
          </p>
          <div className="flex justify-between">
            <button className="btn-secondary" onClick={retake}>↺ Retake</button>
            <button className="btn-primary" onClick={confirm}>✓ Use this photo</button>
          </div>
        </div>
      )}

      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
    </div>
  );
}
