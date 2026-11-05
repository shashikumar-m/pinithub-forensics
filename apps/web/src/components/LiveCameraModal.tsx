import { useRef, useState, useEffect, useCallback } from 'react';

interface LiveCameraModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPhotoCaptured: (file: File) => void;
  onUseNativeCamera?: () => void;
}

export default function LiveCameraModal({
  isOpen,
  onClose,
  onPhotoCaptured,
  onUseNativeCamera,
}: LiveCameraModalProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment');
  const [capturedPreview, setCapturedPreview] = useState<string | null>(null);
  const [capturedBlob, setCapturedBlob] = useState<Blob | null>(null);
  const [loadingCamera, setLoadingCamera] = useState(true);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [flashEffect, setFlashEffect] = useState(false);

  // Safely stop all tracks in active media stream
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // ignore
        }
      });
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }, []);

  // Attach stream to video element whenever videoRef or stream changes
  const attachStream = useCallback((stream: MediaStream) => {
    streamRef.current = stream;
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      videoRef.current
        .play()
        .then(() => {
          setLoadingCamera(false);
        })
        .catch((err) => {
          console.warn('Auto-play caught:', err);
          // Still dismiss loader so user sees live frame
          setLoadingCamera(false);
        });
    }
  }, []);

  // Callback ref to guarantee we attach stream as soon as video DOM node mounts
  const setVideoNode = useCallback(
    (node: HTMLVideoElement | null) => {
      videoRef.current = node;
      if (node && streamRef.current && node.srcObject !== streamRef.current) {
        node.srcObject = streamRef.current;
        node.play().catch(() => {});
      }
    },
    []
  );

  const startCamera = useCallback(
    async (facing: 'environment' | 'user') => {
      stopStream();
      setCameraError(null);
      setLoadingCamera(true);

      // Check for MediaDevices API support
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraError(
          'Live video stream is not supported in this browser context (requires HTTPS). You can use your device native camera app instead.'
        );
        setLoadingCamera(false);
        return;
      }

      try {
        // Try ideal resolution with facingMode
        const constraints: MediaStreamConstraints = {
          video: {
            facingMode: { ideal: facing },
            width: { ideal: 1920, min: 640 },
            height: { ideal: 1080, min: 480 },
          },
          audio: false,
        };

        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        attachStream(stream);
      } catch (err: any) {
        console.warn('Initial camera constraints failed, attempting basic fallback:', err);
        try {
          // Fallback 1: simple facingMode string
          const fallbackStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: facing },
            audio: false,
          });
          attachStream(fallbackStream);
        } catch (err2: any) {
          console.warn('Fallback 1 failed, attempting unconstrained video:', err2);
          try {
            // Fallback 2: any video device
            const anyStream = await navigator.mediaDevices.getUserMedia({
              video: true,
              audio: false,
            });
            attachStream(anyStream);
          } catch (finalErr: any) {
            setLoadingCamera(false);
            const errName = finalErr?.name || err?.name;
            if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
              setCameraError(
                'Camera permission was denied. Please allow camera access in your browser settings, or use the Native Camera button.'
              );
            } else if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
              setCameraError('No physical camera was detected on this device.');
            } else if (errName === 'NotReadableError' || errName === 'TrackStartError') {
              setCameraError('Camera is already in use by another application.');
            } else {
              setCameraError(
                'Could not initialize camera feed. Please check camera permissions or try the Native Camera option.'
              );
            }
          }
        }
      }
    },
    [stopStream, attachStream]
  );

  // Start or stop camera based on modal isOpen
  useEffect(() => {
    if (isOpen) {
      setCapturedPreview(null);
      setCapturedBlob(null);
      startCamera(facingMode);
    } else {
      stopStream();
    }
    return () => {
      stopStream();
    };
  }, [isOpen, facingMode, startCamera, stopStream]);

  // Capture snapshot from current video frame
  const handleCaptureSnapshot = () => {
    if (!videoRef.current || !canvasRef.current) return;

    // Trigger visual shutter flash
    setFlashEffect(true);
    setTimeout(() => setFlashEffect(false), 220);

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;

    canvas.width = w;
    canvas.height = h;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Flip back if selfie user-facing camera
    if (facingMode === 'user') {
      ctx.translate(w, 0);
      ctx.scale(-1, 1);
    }

    ctx.drawImage(video, 0, 0, w, h);

    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const preview = URL.createObjectURL(blob);
        setCapturedBlob(blob);
        setCapturedPreview(preview);
        stopStream();
      },
      'image/jpeg',
      0.95
    );
  };

  const handleRetake = () => {
    if (capturedPreview) {
      URL.revokeObjectURL(capturedPreview);
      setCapturedPreview(null);
    }
    setCapturedBlob(null);
    startCamera(facingMode);
  };

  const handleConfirmPhoto = () => {
    if (!capturedBlob) return;
    const filename = `camera-capture-${Date.now()}.jpg`;
    const file = new File([capturedBlob], filename, { type: 'image/jpeg' });
    onPhotoCaptured(file);
    handleCloseModal();
  };

  const handleCloseModal = () => {
    stopStream();
    if (capturedPreview) {
      URL.revokeObjectURL(capturedPreview);
      setCapturedPreview(null);
    }
    setCapturedBlob(null);
    onClose();
  };

  const toggleFacingMode = () => {
    const next = facingMode === 'environment' ? 'user' : 'environment';
    setFacingMode(next);
  };

  const handleFallbackToNative = () => {
    handleCloseModal();
    if (onUseNativeCamera) {
      onUseNativeCamera();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-3 sm:p-6 animate-fadeIn">
      <div className="relative flex flex-col w-full max-w-xl max-h-[92vh] overflow-hidden rounded-3xl bg-slate-900 border border-slate-700 shadow-2xl text-white">
        {/* Modal Top Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-2">
            <span className="flex h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-bold tracking-wide uppercase text-slate-200">
              {capturedPreview ? 'Review Photo' : 'Live Camera Viewfinder'}
            </span>
          </div>

          <button
            onClick={handleCloseModal}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
            title="Close camera"
          >
            ✕
          </button>
        </div>

        {/* Viewfinder / Preview Display Area */}
        <div className="relative flex-1 flex items-center justify-center bg-black overflow-hidden min-h-[320px] sm:min-h-[440px]">
          {/* Shutter Flash Animation */}
          {flashEffect && (
            <div className="absolute inset-0 bg-white z-30 pointer-events-none transition-opacity duration-200" />
          )}

          {/* Video element is permanently mounted to maintain ref binding */}
          <video
            ref={setVideoNode}
            autoPlay
            playsInline
            muted
            onLoadedMetadata={() => {
              setLoadingCamera(false);
              videoRef.current?.play().catch(() => {});
            }}
            onPlaying={() => setLoadingCamera(false)}
            className={`max-h-[60vh] w-full object-cover sm:object-contain transition-opacity duration-300 ${
              capturedPreview || cameraError ? 'hidden' : loadingCamera ? 'opacity-20' : 'opacity-100'
            } ${facingMode === 'user' ? 'scale-x-[-1]' : ''}`}
          />

          {/* Captured Review Display */}
          {capturedPreview && (
            <img
              src={capturedPreview}
              alt="Captured"
              className="max-h-[60vh] w-auto max-w-full object-contain animate-fadeIn"
            />
          )}

          {/* Viewfinder Framing Guidelines (visible only during live stream) */}
          {!capturedPreview && !cameraError && !loadingCamera && (
            <>
              <div className="absolute inset-8 pointer-events-none border border-white/20 rounded-2xl flex items-center justify-center">
                <div className="h-6 w-6 border-t-2 border-l-2 border-cyan-400 absolute top-0 left-0" />
                <div className="h-6 w-6 border-t-2 border-r-2 border-cyan-400 absolute top-0 right-0" />
                <div className="h-6 w-6 border-b-2 border-l-2 border-cyan-400 absolute bottom-0 left-0" />
                <div className="h-6 w-6 border-b-2 border-r-2 border-cyan-400 absolute bottom-0 right-0" />
                <div className="h-2 w-2 rounded-full bg-cyan-400/60" />
              </div>

              {/* Flip Camera Switch Button (Top Right of Viewfinder) */}
              <button
                type="button"
                onClick={toggleFacingMode}
                className="absolute top-4 right-4 z-20 flex items-center gap-1.5 rounded-full bg-black/60 backdrop-blur-sm border border-white/20 px-3 py-1.5 text-xs text-white hover:bg-black/80 transition-colors shadow-md active:scale-95"
                title="Switch between front and back camera"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                <span className="text-[11px] font-semibold">{facingMode === 'environment' ? 'Back' : 'Front'}</span>
              </button>
            </>
          )}

          {/* Loading Camera Spinner Overlay */}
          {loadingCamera && !cameraError && !capturedPreview && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 backdrop-blur-xs z-10">
              <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-700 border-t-cyan-400" />
              <p className="text-xs text-slate-300 font-medium">Starting camera stream…</p>
            </div>
          )}

          {/* Error Message & Native Camera Fallback */}
          {cameraError && (
            <div className="p-6 text-center max-w-sm space-y-3 z-20">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/20 text-amber-400">
                <svg className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                  />
                </svg>
              </div>
              <p className="text-sm font-semibold text-amber-200">{cameraError}</p>
              <div className="flex flex-col gap-2 pt-2">
                <button
                  type="button"
                  onClick={handleFallbackToNative}
                  className="rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 px-4 py-2.5 text-xs font-bold text-white shadow-lg active:scale-95 transition-all"
                >
                  📱 Open System Camera App
                </button>
                <div className="flex justify-center gap-2">
                  <button
                    type="button"
                    onClick={() => startCamera(facingMode)}
                    className="rounded-xl bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300"
                  >
                    Retry Live Feed
                  </button>
                  <button
                    type="button"
                    onClick={handleCloseModal}
                    className="rounded-xl bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Control Bar */}
        <div className="p-4 sm:p-5 bg-slate-950 border-t border-slate-800">
          {capturedPreview ? (
            /* Confirm or Retake Bar */
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={handleRetake}
                className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-slate-800 hover:bg-slate-700 py-3 text-sm font-semibold text-slate-200 transition-colors active:scale-95"
              >
                <span>↺</span>
                <span>Retake Photo</span>
              </button>

              <button
                type="button"
                onClick={handleConfirmPhoto}
                className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 py-3 text-sm font-bold text-white shadow-lg shadow-emerald-600/30 transition-all active:scale-95"
              >
                <span>✓</span>
                <span>Use This Photo</span>
              </button>
            </div>
          ) : (
            /* Live Shutter Controls */
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={handleFallbackToNative}
                className="text-xs font-semibold text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg border border-slate-800 hover:border-slate-700 transition-colors flex items-center gap-1.5"
                title="Open native OS camera app instead"
              >
                <span>📱</span>
                <span className="hidden sm:inline">Use Native Camera</span>
                <span className="sm:hidden">Native</span>
              </button>

              {/* Native-style Camera Shutter Button */}
              <button
                type="button"
                onClick={handleCaptureSnapshot}
                disabled={loadingCamera || !!cameraError}
                className="group relative flex h-16 w-16 items-center justify-center rounded-full border-4 border-white bg-transparent p-1 shadow-lg transition-transform active:scale-90 disabled:opacity-40"
                title="Capture Photo"
              >
                <span className="h-full w-full rounded-full bg-white group-hover:bg-slate-200 transition-colors" />
              </button>

              <button
                type="button"
                onClick={toggleFacingMode}
                disabled={loadingCamera || !!cameraError}
                className="text-xs font-semibold text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg border border-slate-800 hover:border-slate-700 transition-colors flex items-center gap-1 disabled:opacity-40"
              >
                <span>Flip</span>
                <span>⇄</span>
              </button>
            </div>
          )}
        </div>

        {/* Hidden Canvas used for high-res snapshot rasterization */}
        <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
      </div>
    </div>
  );
}
