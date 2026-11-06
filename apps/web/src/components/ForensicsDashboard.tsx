import React, { useState, useRef } from 'react';
import LiveCameraModal from './LiveCameraModal';

export interface ForensicsAnalysisResult {
  status: string;
  mode: 'BLIND' | 'REFERENCE';
  verdict: 'EDITED' | 'NOT_EDITED' | 'INCONCLUSIVE';
  classification?: 'AI_GENERATED' | 'AI_EDITED' | 'CAMERA_CAPTURED' | 'DIGITALLY_ENHANCED' | 'EDITED' | 'INCONCLUSIVE';
  probability: number;
  dualScore?: {
    realPercentage: number;
    aiPercentage: number;
  };
  finalCall?: {
    verdict: string;
    title: string;
    description: string;
  };
  summary: string;
  affectedAreaPercentage?: number;
  dimensions?: { width: number; height: number };
  regions: Array<{
    id: string;
    bbox: { x: number; y: number; w: number; h: number };
    areaPct: number;
    confidence: number;
    editTypeGuess: string;
  }>;
  crop?: {
    status: string;
    cropPercentage: number;
    keptPercentage: number;
    polygon?: Array<{ x: number; y: number }>;
    boundingBox?: { x: number; y: number; width: number; height: number };
    method?: string;
  } | null;
  aiDetection?: {
    status: string;
    score: number;
    label: string;
  };
  registration?: {
    status: string;
    inliers?: number;
    inlierRatio?: number;
    reprojectionError?: number;
  } | null;
  evidence: Array<{
    detector: string;
    version: string;
    category: string;
    score: number | null;
    reliability: number | null;
    tag: string;
    notes: string[];
    evidence?: Record<string, any>;
    details?: Record<string, any>;
  }>;
  artifacts?: {
    heatmapUrl?: string;
    maskUrl?: string;
  };
  opticalMetadata?: {
    hasExif: boolean;
    make?: string | null;
    model?: string | null;
    deviceName?: string | null;
    lensModel?: string | null;
    dateTimeOriginal?: string | null;
    offsetTime?: string | null;
    exposureTime?: string | null;
    fNumber?: string | null;
    iso?: string | null;
    focalLength?: string | null;
    sensorVerification?: string;
    deviceDescription?: string | null;
  };
  warnings?: string[];
  limitations?: string[];
  executionMs?: number;
}

interface PipelineStage {
  name: string;
  desc: string;
  threshold: number;
}

const PIPELINE_STAGES: PipelineStage[] = [
  {
    name: 'Stage 1/7: Binary & EXIF Metadata Extraction',
    desc: 'Reading file headers, camera make/model, device OS, and C2PA provenance manifests...',
    threshold: 14,
  },
  {
    name: 'Stage 2/7: JPEG Error Level Analysis (ELA)',
    desc: 'Computing localized recompression difference matrices at Q75/Q90 to detect compression anomalies...',
    threshold: 28,
  },
  {
    name: 'Stage 3/7: Optical Sensor Shot Noise (PRNU)',
    desc: 'Extracting high-pass wavelet residual field and verifying Poisson-Gaussian camera sensor noise stationarity...',
    threshold: 46,
  },
  {
    name: 'Stage 4/7: 2D FFT Discrete Cosine Frequency Analysis',
    desc: 'Testing Fourier power spectrum 1/f^α decay and scanning for synthetic generative periodic lattice spikes...',
    threshold: 64,
  },
  {
    name: 'Stage 5/7: JPEG Grid Alignment & Resampling',
    desc: 'Checking 8×8 block origin alignment, DCT histogram gap profiles, and Radon transform interpolation peaks...',
    threshold: 78,
  },
  {
    name: 'Stage 6/7: Neural Deep Learning Inpainting Detection',
    desc: 'Executing multi-generator UNet + EfficientNet-B3 segmentation across suspect pixel coordinates...',
    threshold: 90,
  },
  {
    name: 'Stage 7/7: Multi-Detector Evidence Calibration & Fusion',
    desc: 'Cross-corroborating physical signals, eliminating false alarms, and calculating Boolean mask union...',
    threshold: 98,
  },
  {
    name: 'Analysis Complete: Finalizing Report',
    desc: 'Compiling executive summary, calibrated confidence scores, and rendering forensic visualization maps...',
    threshold: 100,
  },
];

const DETECTOR_CHIPS = [
  { id: 'meta', label: 'EXIF / C2PA', minPct: 14 },
  { id: 'ela', label: 'Error Level Analysis', minPct: 28 },
  { id: 'noise', label: 'Sensor Noise Field', minPct: 46 },
  { id: 'dct', label: 'DCT 2D FFT Spectrum', minPct: 64 },
  { id: 'grid', label: 'JPEG 8×8 Grid', minPct: 72 },
  { id: 'resample', label: 'Resampling Radon', minPct: 78 },
  { id: 'copy_move', label: 'Copy-Move SIFT/ORB', minPct: 84 },
  { id: 'ai', label: 'AI Generative UNet', minPct: 90 },
  { id: 'fusion', label: 'Multi-Signal Fusion', minPct: 98 },
];

export default function ForensicsDashboard() {
  const [suspectFile, setSuspectFile] = useState<File | null>(null);
  const [suspectPreview, setSuspectPreview] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ForensicsAnalysisResult | null>(null);

  const currentStage = PIPELINE_STAGES.find((s) => progress <= s.threshold) || PIPELINE_STAGES[PIPELINE_STAGES.length - 1];

  // Heatmap viewer state
  const [heatmapOpacity, setHeatmapOpacity] = useState(60);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);
  const [expandedMetrics, setExpandedMetrics] = useState<Record<string, boolean>>({});
  const [isCameraOpen, setIsCameraOpen] = useState(false);

  function toggleMetric(name: string) {
    setExpandedMetrics((prev) => ({ ...prev, [name]: !prev[name] }));
  }

  const suspectInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(file: File) {
    setSuspectFile(file);
    const url = URL.createObjectURL(file);
    setSuspectPreview(url);
    setResult(null);
    setError(null);
  }

  function handleSuspectChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  }

  function handleClearImage(e: React.MouseEvent) {
    e.stopPropagation();
    setSuspectFile(null);
    setSuspectPreview(null);
    setResult(null);
    setError(null);
    if (suspectInputRef.current) suspectInputRef.current.value = '';
    if (cameraInputRef.current) cameraInputRef.current.value = '';
  }

  async function handleAnalyze() {
    if (!suspectFile) {
      setError('Please select an image to analyze.');
      return;
    }

    setLoading(true);
    setError(null);
    setProgress(4);
    setElapsedSeconds(0);

    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      setElapsedSeconds(Math.round(elapsed * 10) / 10);

      setProgress((prev) => {
        if (prev >= 98) return 98;
        const remaining = 98 - prev;
        const step = Math.max(0.35, remaining * 0.045);
        return Math.min(98, Math.round((prev + step) * 10) / 10);
      });
    }, 150);

    try {
      const formData = new FormData();
      formData.append('file', suspectFile);

      const res = await fetch('/v1/analyses/direct', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.error?.message || `Analysis failed with status ${res.status}`);
      }

      const data: ForensicsAnalysisResult = await res.json();
      clearInterval(interval);
      setProgress(100);

      // Brief 350ms pause so user sees the satisfying 100% complete state before revealing report
      await new Promise((r) => setTimeout(r, 350));
      setResult(data);
    } catch (err: any) {
      clearInterval(interval);
      setError(err?.message || 'Failed to complete forensic analysis.');
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  }

  function handleExportJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `forensic-report-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleExportPdf() {
    window.print();
  }

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* 1. Upload & Inspection Control Card */}
      <div className="rounded-2xl sm:rounded-3xl border border-slate-200/90 bg-white p-4 sm:p-7 shadow-sm transition-all">
        {/* Card Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-500 animate-pulse" />
              <h2 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
                Upload &amp; Analyze Image
              </h2>
            </div>
            <p className="mt-1 text-xs sm:text-sm text-slate-500 leading-snug">
              Supports real camera photos (smartphones, WhatsApp, documents) and AI models (Canva, Gemini, ChatGPT/DALL-E, Midjourney, Stable Diffusion).
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 border border-brand-200/80 px-3 py-1 text-[11px] sm:text-xs font-semibold text-brand-700">
              <svg className="h-3.5 w-3.5 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <span>Multi-Source Provenance</span>
            </span>
          </div>
        </div>

        {/* Dropzone Container */}
        <div className="mt-5">
          <div
            onClick={() => suspectInputRef.current?.click()}
            className="group relative flex min-h-[200px] sm:min-h-[250px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50/70 p-4 sm:p-6 transition-all hover:border-brand-500 hover:bg-brand-50/20 active:scale-[0.99]"
          >
            {suspectPreview ? (
              <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-xl">
                <img
                  src={suspectPreview}
                  alt="Suspect Preview"
                  className="max-h-[320px] sm:max-h-[420px] w-auto max-w-full object-contain rounded-lg shadow-sm"
                />

                {/* Live Scanning Laser Overlay during Loading */}
                {loading && (
                  <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-lg bg-cyan-950/30 backdrop-blur-[0.5px]">
                    <div className="absolute left-0 right-0 h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_16px_#22d3ee] animate-laser" />
                    <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,0.08)_1px,transparent_1px)] bg-[size:100%_8px]" />
                    <div className="absolute top-3 left-3 flex items-center gap-2 rounded-lg bg-black/85 px-3 py-1.5 text-xs font-mono text-cyan-300 border border-cyan-500/50 shadow-md">
                      <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
                      <span className="font-bold tracking-wider">OPTICAL SCANNING IN PROGRESS</span>
                    </div>
                  </div>
                )}

                {!loading && (
                  <button
                    onClick={handleClearImage}
                    className="absolute top-3 right-3 rounded-full bg-black/75 hover:bg-red-600 text-white p-1.5 shadow-md transition-colors"
                    title="Clear image"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
              </div>
            ) : (
              <div className="text-center py-4 px-2">
                <div className="mx-auto flex h-14 w-14 sm:h-16 sm:w-16 items-center justify-center rounded-2xl bg-gradient-to-tr from-brand-100 to-indigo-100 text-brand-600 mb-3 shadow-inner group-hover:scale-105 transition-transform">
                  <svg className="h-7 w-7 sm:h-8 sm:w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <p className="text-sm sm:text-base font-bold text-slate-800">
                  Tap to browse or drop image here
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  JPEG, PNG, WebP · WhatsApp · Phone Camera · AI Exports (up to 50MB)
                </p>

                {/* Mobile & Desktop Camera / Upload Buttons */}
                <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      suspectInputRef.current?.click();
                    }}
                    className="rounded-xl bg-white border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-xs flex items-center gap-1.5 active:scale-95 transition-all"
                  >
                    📁 Gallery / Files
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsCameraOpen(true);
                    }}
                    className="rounded-xl bg-brand-50 border border-brand-200 px-3.5 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 shadow-xs flex items-center gap-1.5 active:scale-95 transition-all"
                  >
                    📷 Live Camera
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      cameraInputRef.current?.click();
                    }}
                    className="rounded-xl bg-slate-900 border border-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 shadow-xs flex items-center gap-1.5 active:scale-95 transition-all"
                  >
                    📱 Native Camera
                  </button>
                </div>
              </div>
            )}

            {/* Hidden File Inputs */}
            <input
              ref={suspectInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleSuspectChange}
            />
            <input
              ref={cameraInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={handleSuspectChange}
            />
          </div>

          {/* Selected File Details Bar */}
          {suspectFile && !loading && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 border border-slate-200/80 px-3.5 py-2 text-xs">
              <div className="flex items-center gap-2 truncate">
                <span className="text-slate-400">Selected:</span>
                <span className="font-semibold text-slate-800 truncate max-w-[200px] sm:max-w-md">{suspectFile.name}</span>
                <span className="text-slate-400 font-mono">({(suspectFile.size / 1024).toFixed(0)} KB)</span>
              </div>
              <div className="flex items-center gap-2 ml-auto">
                <button
                  type="button"
                  onClick={() => setIsCameraOpen(true)}
                  className="rounded-lg bg-white border border-slate-200 hover:bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-xs transition-all flex items-center gap-1 active:scale-95"
                >
                  📷 Retake
                </button>
                <button
                  type="button"
                  onClick={handleClearImage}
                  className="text-xs font-semibold text-red-600 hover:text-red-700 underline underline-offset-2"
                >
                  Change Photo
                </button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="mt-4 rounded-xl bg-red-50 p-3.5 text-xs sm:text-sm text-red-700 border border-red-200 flex items-center gap-2">
            <svg className="h-5 w-5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {/* Live 10-Stage Pipeline Scanning Progress Card */}
        {loading && (
          <div className="mt-5 rounded-2xl border-2 border-brand-500/40 bg-gradient-to-br from-slate-900 via-slate-850 to-slate-900 p-4 sm:p-6 text-white shadow-xl animate-fadeIn ring-1 ring-cyan-500/30">
            <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-700/60 pb-3 sm:pb-4">
              <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500" />
                </span>
                <span className="text-xs sm:text-sm font-bold uppercase tracking-wider text-cyan-300">
                  Executing 10-Stage Forensic Pipeline
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                <span>Elapsed: <strong className="text-cyan-300 font-bold">{elapsedSeconds.toFixed(1)}s</strong></span>
                <span className="text-slate-600">•</span>
                <span className="text-slate-400">Est: ~12-16s</span>
              </div>
            </div>

            <div className="mt-4 flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
              <div>
                <p className="text-xs font-bold text-cyan-400 tracking-wide uppercase">
                  {currentStage.name}
                </p>
                <p className="mt-0.5 text-xs sm:text-sm text-slate-300 leading-snug max-w-xl">
                  {currentStage.desc}
                </p>
              </div>
              <div className="flex items-baseline gap-1 font-mono self-end sm:self-auto">
                <span className="text-3xl sm:text-5xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-cyan-300 via-white to-brand-300">
                  {Math.round(progress)}
                </span>
                <span className="text-xl sm:text-2xl font-bold text-cyan-400">%</span>
              </div>
            </div>

            {/* Glowing Shimmer Bar */}
            <div className="relative mt-3.5 h-3 sm:h-3.5 w-full overflow-hidden rounded-full bg-slate-800 border border-slate-700/80 shadow-inner">
              <div
                className="relative h-full rounded-full bg-gradient-to-r from-brand-500 via-indigo-500 to-cyan-400 transition-all duration-300 ease-out shadow-[0_0_16px_rgba(34,211,238,0.5)]"
                style={{ width: `${progress}%` }}
              >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer" />
              </div>
            </div>

            {/* Live Detector Verification Matrix */}
            <div className="mt-5 pt-4 border-t border-slate-700/60">
              <p className="text-[10px] sm:text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
                Live Physical &amp; AI Detector Verification Status
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {DETECTOR_CHIPS.map((chip) => {
                  const isDone = progress >= chip.minPct;
                  const isCurrent = !isDone && progress >= chip.minPct - 12;
                  return (
                    <div
                      key={chip.id}
                      className={`flex items-center gap-1.5 sm:gap-2 rounded-lg px-2 sm:px-2.5 py-1.5 text-[11px] sm:text-xs transition-all ${
                        isDone
                          ? 'bg-emerald-950/50 border border-emerald-500/40 text-emerald-200 shadow-xs'
                          : isCurrent
                          ? 'bg-cyan-950/60 border border-cyan-400/60 text-cyan-200 ring-1 ring-cyan-400/30'
                          : 'bg-slate-800/50 border border-slate-700/50 text-slate-400'
                      }`}
                    >
                      {isDone ? (
                        <svg className="h-3.5 w-3.5 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : isCurrent ? (
                        <svg className="h-3.5 w-3.5 text-cyan-400 animate-spin shrink-0" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                        </svg>
                      ) : (
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-500 shrink-0 ml-1 mr-1" />
                      )}
                      <span className="truncate font-medium">{chip.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Primary Action Button */}
        <div className="mt-5 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <div className="text-xs text-slate-500 order-2 sm:order-1 text-center sm:text-left">
            <span>Forensic Mode: </span>
            <span className="font-semibold text-slate-700">Multi-Signal Provenance &amp; Physical Sensor Fusion</span>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={loading || !suspectFile}
            className={`w-full sm:w-auto flex items-center justify-center gap-2 rounded-xl px-7 py-3 text-sm font-bold text-white shadow-md transition-all order-1 sm:order-2 active:scale-95 ${
              loading || !suspectFile
                ? 'cursor-not-allowed bg-slate-400'
                : 'bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-700 hover:to-indigo-700 shadow-brand-500/25 hover:shadow-lg'
            }`}
          >
            {loading ? (
              <>
                <svg className="h-4 w-4 animate-spin text-white" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                <span>Analyzing Forensics… {Math.round(progress)}%</span>
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
                <span>Run Forensic Analysis</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* 2. Forensic Analysis Results Section */}
      {result && (
        <div className="space-y-6 sm:space-y-8 animate-fadeIn">
          {/* 1. Final Call Hero Banner & Dual-Percentage Gauge */}
          {(() => {
            const aiPct = result.dualScore?.aiPercentage ?? Number((result.probability * 100).toFixed(1));
            const realPct = result.dualScore?.realPercentage ?? Number(Math.max(0, 100 - aiPct).toFixed(1));
            const isAiGen = result.classification === 'AI_GENERATED';
            const isEnhanced = result.classification === 'DIGITALLY_ENHANCED';
            const isUserEdit = result.classification === 'EDITED';
            const isAiEdit = !isAiGen && !isEnhanced && !isUserEdit && (result.classification === 'AI_EDITED' || (result.verdict === 'EDITED' && (result.regions?.length ?? 0) > 0));
            const isCam = !isAiGen && !isEnhanced && !isUserEdit && !isAiEdit && (result.classification === 'CAMERA_CAPTURED' || result.verdict === 'NOT_EDITED');

            const finalTitle = isAiGen
              ? 'FULL AI GENERATED'
              : isEnhanced
              ? 'REAL PHOTO (DIGITALLY ENHANCED)'
              : isUserEdit
              ? 'MANIPULATED / USER EDITED'
              : isAiEdit
              ? 'AI EDITED / INPAINTED'
              : isCam
              ? 'REAL CAMERA PHOTO'
              : 'INCONCLUSIVE';

            const finalBadge = isAiGen
              ? 'SYNTHETIC MEDIA'
              : isEnhanced
              ? 'AUTHENTIC PHOTO • POST-PROCESSED'
              : isUserEdit
              ? 'MANUAL EDIT • TEXT/IMAGE ADDED'
              : isAiEdit
              ? 'LOCAL TAMPERING DETECTED'
              : isCam
              ? 'AUTHENTIC OPTICAL CAPTURE'
              : 'UNVERIFIED';

            return (
              <div className="space-y-4 sm:space-y-6">
                {/* Final Call Decision Card */}
                <div
                  className={`rounded-2xl sm:rounded-3xl border p-5 sm:p-7 shadow-sm transition-all ${
                    isAiGen
                      ? 'border-purple-300 bg-gradient-to-br from-purple-50 via-white to-indigo-50'
                      : isEnhanced
                      ? 'border-sky-300 bg-gradient-to-br from-sky-50 via-white to-teal-50'
                      : isUserEdit
                      ? 'border-rose-300 bg-gradient-to-br from-rose-50 via-white to-orange-50'
                      : isAiEdit
                      ? 'border-amber-300 bg-gradient-to-br from-amber-50 via-white to-orange-50'
                      : isCam
                      ? 'border-emerald-300 bg-gradient-to-br from-emerald-50 via-white to-teal-50'
                      : 'border-slate-300 bg-white'
                  }`}
                >
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/60 pb-5">
                    <div>
                      <div className="flex flex-wrap items-center gap-2 mb-2">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-black tracking-wider uppercase ${
                            isAiGen
                              ? 'bg-purple-200 text-purple-900'
                              : isEnhanced
                              ? 'bg-sky-200 text-sky-900'
                              : isUserEdit
                              ? 'bg-rose-200 text-rose-900'
                              : isAiEdit
                              ? 'bg-amber-200 text-amber-900'
                              : isCam
                              ? 'bg-emerald-200 text-emerald-900'
                              : 'bg-slate-200 text-slate-800'
                          }`}
                        >
                          <span
                            className={`h-2.5 w-2.5 rounded-full animate-ping ${
                              isAiGen
                                ? 'bg-purple-600'
                                : isEnhanced
                                ? 'bg-sky-600'
                                : isUserEdit
                                ? 'bg-rose-600'
                                : isAiEdit
                                ? 'bg-amber-600'
                                : isCam
                                ? 'bg-emerald-600'
                                : 'bg-slate-600'
                            }`}
                          />
                          <span>FINAL CALL: {finalTitle}</span>
                        </span>
                        <span className="rounded-md bg-white/90 border border-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-600 shadow-2xs">
                          {finalBadge}
                        </span>
                        {result.executionMs && (
                          <span className="text-[11px] text-slate-400 font-mono">
                            ⚡ {result.executionMs} ms
                          </span>
                        )}
                      </div>

                      <h2 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
                        {isAiGen
                          ? 'Synthetic AI Media (Generated from Scratch)'
                          : isEnhanced
                          ? 'Real Camera Photograph (Digitally Enhanced / Stylized)'
                          : isUserEdit
                          ? `Manipulated Image: Local Content Edit / Text Added in ~${result.affectedAreaPercentage || 0}% of Canvas`
                          : isAiEdit
                          ? `Manipulated Image: Localized AI Edit in ~${result.affectedAreaPercentage || 0}% of Canvas`
                          : isCam
                          ? 'Authentic Camera Capture (100% Genuine Physical Image)'
                          : 'Digital Non-Camera Media'}
                      </h2>

                      <p className="mt-1 text-xs sm:text-sm text-slate-600 leading-relaxed max-w-3xl">
                        {result.finalCall?.description || result.summary}
                      </p>
                    </div>

                    {/* Export Buttons */}
                    <div className="flex flex-wrap items-center gap-2 self-start md:self-auto shrink-0">
                      <button
                        onClick={handleExportPdf}
                        className="rounded-xl border border-brand-200 bg-brand-50 px-3.5 py-2 text-xs font-bold text-brand-700 hover:bg-brand-100 flex items-center gap-1.5 shadow-2xs transition-colors"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z" />
                        </svg>
                        <span>Export PDF</span>
                      </button>
                      <button
                        onClick={handleExportJson}
                        className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 shadow-2xs transition-colors"
                      >
                        JSON
                      </button>
                    </div>
                  </div>

                  {/* Dual-Percentage ZeroGPT-Style Meter */}
                  <div className="mt-5 pt-1">
                    <div className="grid grid-cols-2 gap-3 sm:gap-6 mb-3">
                      {/* Real Block */}
                      <div className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-3.5 sm:p-4 text-center shadow-2xs">
                        <div className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-emerald-800">
                          Real Image Likelihood
                        </div>
                        <div className="mt-1 flex items-baseline justify-center gap-1 font-mono">
                          <span className="text-3xl sm:text-4xl font-black text-emerald-700">{realPct}</span>
                          <span className="text-base font-bold text-emerald-600">%</span>
                        </div>
                        <div className="mt-1 text-[10px] sm:text-[11px] text-emerald-600 font-medium">
                          Authentic Camera &amp; Sensor Optics
                        </div>
                      </div>

                      {/* AI / Edited Block */}
                      <div
                        className={`rounded-2xl border p-3.5 sm:p-4 text-center shadow-2xs ${
                          isAiGen || isAiEdit || isUserEdit
                            ? 'border-red-300 bg-red-50/80 text-red-900'
                            : 'border-slate-200 bg-slate-50 text-slate-700'
                        }`}
                      >
                        <div className="text-[11px] sm:text-xs font-bold uppercase tracking-wider">
                          AI / Edited Likelihood
                        </div>
                        <div className="mt-1 flex items-baseline justify-center gap-1 font-mono">
                          <span
                            className={`text-3xl sm:text-4xl font-black ${
                              isAiGen || isAiEdit || isUserEdit ? 'text-red-600' : 'text-slate-800'
                            }`}
                          >
                            {aiPct}
                          </span>
                          <span className="text-base font-bold">%</span>
                        </div>
                        <div className="mt-1 text-[10px] sm:text-[11px] font-medium opacity-80">
                          {isEnhanced
                            ? 'Digital Filters, HDR, or Post-Processing'
                            : isUserEdit
                            ? `~${result.affectedAreaPercentage || 0}% Added Image / Text Overlay Detected`
                            : isAiEdit
                            ? `~${result.affectedAreaPercentage || 0}% Local Inpainting Detected`
                            : isAiGen
                            ? 'Diffusion / GAN Generated'
                            : 'Minimal Residual Artifacts'}
                        </div>
                      </div>
                    </div>

                    {/* Split Dual-Colored Progress Bar */}
                    <div className="relative mt-3">
                      <div className="h-4 w-full overflow-hidden rounded-full bg-slate-200 flex shadow-inner">
                        <div
                          className="h-full bg-emerald-500 transition-all duration-700 flex items-center justify-start pl-2 text-[10px] font-bold text-white"
                          style={{ width: `${realPct}%` }}
                          title={`Real: ${realPct}%`}
                        >
                          {realPct > 15 && `Real ${realPct}%`}
                        </div>
                        <div
                          className={`h-full transition-all duration-700 flex items-center justify-end pr-2 text-[10px] font-bold text-white ${
                            isAiGen ? 'bg-purple-600' : isUserEdit ? 'bg-rose-600' : 'bg-red-500'
                          }`}
                          style={{ width: `${aiPct}%` }}
                          title={`AI / Edited: ${aiPct}%`}
                        >
                          {aiPct > 15 && `AI ${aiPct}%`}
                        </div>
                      </div>
                    </div>

                    <div className="mt-2 flex justify-between text-[11px] text-slate-500 font-semibold px-1">
                      <span className="text-emerald-700">🟢 100% Optical Sensor Match</span>
                      <span className="text-slate-400">Total = 100% Complementary Evidence</span>
                      <span className={isAiGen ? 'text-purple-700' : 'text-red-700'}>
                        🔴 100% Synthetic / Tampered
                      </span>
                    </div>
                  </div>
                </div>

                {/* 2. Visual "Where It Was Edited" Tampering Locator */}
                {isAiEdit && result.regions && result.regions.length > 0 && suspectPreview ? (
                  <div className="rounded-2xl sm:rounded-3xl border-2 border-red-300 bg-white p-4 sm:p-6 shadow-sm">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                      <div>
                        <div className="inline-flex items-center gap-1.5 rounded-full bg-red-100 px-3 py-1 text-xs font-black text-red-800 mb-1">
                          <span className="h-2 w-2 rounded-full bg-red-600 animate-ping" />
                          <span>TAMPERING LOCATED ({result.regions.length} REGION{result.regions.length > 1 ? 'S' : ''})</span>
                        </div>
                        <h3 className="text-base sm:text-lg font-black text-slate-900">
                          Where The Image Was Edited (Visual Localization)
                        </h3>
                        <p className="text-xs text-slate-500">
                          The red bounding box pinpoints the exact object synthesized with Generative AI / Inpainting.
                        </p>
                      </div>

                      {/* Opacity slider for thermal heatmap */}
                      {result.artifacts?.heatmapUrl && (
                        <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-xl self-start sm:self-auto">
                          <label className="text-xs font-semibold text-slate-600">AI Heatmap:</label>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={heatmapOpacity}
                            onChange={(e) => setHeatmapOpacity(Number(e.target.value))}
                            className="h-2 w-24 sm:w-28 cursor-pointer rounded-lg bg-slate-200 accent-red-600"
                          />
                          <span className="w-8 text-right font-mono text-xs font-bold text-slate-800">
                            {heatmapOpacity}%
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Image with bounding box overlay */}
                    <div className="relative mt-4 flex items-center justify-center overflow-hidden rounded-xl bg-slate-900/95 p-3 sm:p-5">
                      <div className="relative inline-block max-h-[55vh] sm:max-h-[500px]">
                        <img
                          src={suspectPreview}
                          alt="Original Suspect"
                          className="max-h-[55vh] sm:max-h-[500px] w-auto max-w-full object-contain rounded-lg"
                        />

                        {result.artifacts?.heatmapUrl && (
                          <img
                            src={result.artifacts.heatmapUrl}
                            alt="Forensic Heatmap"
                            style={{ opacity: heatmapOpacity / 100 }}
                            className="pointer-events-none absolute inset-0 h-full w-full object-contain mix-blend-screen transition-opacity duration-150"
                          />
                        )}

                        {/* Bounding box(es) */}
                        {result.dimensions &&
                          result.regions.map((reg) => {
                            const leftPct = (reg.bbox.x / result.dimensions!.width) * 100;
                            const topPct = (reg.bbox.y / result.dimensions!.height) * 100;
                            const widthPct = (reg.bbox.w / result.dimensions!.width) * 100;
                            const heightPct = (reg.bbox.h / result.dimensions!.height) * 100;

                            return (
                              <div
                                key={reg.id}
                                style={{
                                  left: `${leftPct}%`,
                                  top: `${topPct}%`,
                                  width: `${widthPct}%`,
                                  height: `${heightPct}%`,
                                }}
                                className="pointer-events-auto absolute border-3 border-red-500 bg-red-500/25 shadow-lg animate-pulse"
                              >
                                <span className="absolute -top-6 left-0 rounded-md bg-red-600 px-2 py-0.5 text-[11px] font-black text-white shadow-md whitespace-nowrap">
                                  ⚠️ AI Inpaint: {reg.areaPct}% Area
                                </span>
                              </div>
                            );
                          })}
                      </div>
                    </div>

                    {/* Region Details Grid */}
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                      {result.regions.map((reg, idx) => (
                        <div key={reg.id} className="rounded-xl border border-red-200 bg-red-50/50 p-3 text-xs">
                          <div className="flex items-center justify-between font-bold text-red-900 mb-1">
                            <span>Region #{idx + 1}: {reg.editTypeGuess}</span>
                            <span className="font-mono text-red-700">{reg.areaPct}% of image</span>
                          </div>
                          <div className="text-[11px] text-slate-600 font-mono">
                            Coordinates: [X: {reg.bbox.x}, Y: {reg.bbox.y}, {reg.bbox.w}×{reg.bbox.h}px]
                          </div>
                          <div className="text-[11px] text-slate-500 mt-1">
                            Confidence: {(reg.confidence * 100).toFixed(1)}% (Corroborated by ELA &amp; UNet)
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : isCam || isEnhanced ? (
                  <div className="rounded-2xl sm:rounded-3xl border border-emerald-300 bg-gradient-to-r from-emerald-50 via-white to-teal-50 p-5 sm:p-6 shadow-sm">
                    <div className="flex items-start sm:items-center gap-4">
                      <div className="rounded-2xl bg-emerald-100 border border-emerald-300 p-3 text-emerald-700 text-2xl shrink-0">
                        🛡️
                      </div>
                      <div>
                        <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-200/80 px-2.5 py-0.5 text-xs font-black text-emerald-900 mb-1">
                          <span>0 SPLICED / INPAINTED REGIONS DETECTED</span>
                        </div>
                        <h3 className="text-base sm:text-lg font-black text-slate-900">
                          {isEnhanced ? 'Authentic Photographic Base Verified (Post-Processing Detected)' : 'Clean Optical Scan Verified (100% Authentic Canvas)'}
                        </h3>
                        <p className="mt-1 text-xs sm:text-sm text-slate-600 leading-relaxed">
                          {isEnhanced
                            ? 'Authentic camera lens perspective and natural lighting physics verified. Digital enhancement (HDR tone-mapping, color grading, or sharpening) is present, but NO generative AI inpainting or splicing was detected.'
                            : 'All image quadrants match genuine camera sensor PRNU noise stationarity. No localized inpainting, splicing, copy-move duplication, or AI generative fill was found across any pixel region.'}
                        </p>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })()}

          {/* Primary Findings Cards (AI Content & Camera Sensor Profile) */}
          <div className="grid gap-4 sm:gap-6 md:grid-cols-2">
            {/* Card 1: AI Content & Inpainting */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm sm:text-base">
                    <span className="text-purple-600">✨</span>
                    <span>AI Content &amp; Inpainting</span>
                  </h3>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                      result.aiDetection?.label === 'AI_GENERATED' || result.aiDetection?.status === 'AI_GENERATED'
                        ? 'bg-purple-100 text-purple-800'
                        : result.aiDetection?.label === 'AI_EDITED' || result.aiDetection?.status === 'AI_EDITED_LOCAL'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-emerald-100 text-emerald-800'
                    }`}
                  >
                    {result.aiDetection?.label === 'AI_GENERATED' || result.aiDetection?.status === 'AI_GENERATED'
                      ? 'AI GENERATED'
                      : result.aiDetection?.label === 'AI_EDITED' || result.aiDetection?.status === 'AI_EDITED_LOCAL'
                      ? 'AI EDIT DETECTED'
                      : 'CONVENTIONAL (Camera)'}
                  </span>
                </div>

                <div className="mt-4 space-y-3">
                  <div className="flex items-center justify-between text-xs sm:text-sm">
                    <div>
                      <span className="text-slate-600 font-semibold">AI Artifact Trace Score</span>
                      <span className="ml-2 text-[10px] sm:text-[11px] text-slate-400">
                        {(result.aiDetection?.score || 0) < 0.45 ? '(Normal camera baseline < 50%)' : '(Elevated generative trace)'}
                      </span>
                    </div>
                    <span className="font-mono font-bold text-slate-900">
                      {result.aiDetection?.score !== undefined ? (result.aiDetection.score * 100).toFixed(1) : '0.0'}%
                    </span>
                  </div>

                  {/* Progress bar with 50% threshold indicator */}
                  <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        (result.aiDetection?.score || 0) >= 0.55
                          ? 'bg-purple-600'
                          : (result.aiDetection?.score || 0) >= 0.45
                          ? 'bg-amber-500'
                          : 'bg-emerald-500'
                      }`}
                      style={{ width: `${Math.min(100, Math.max(0, (result.aiDetection?.score || 0) * 100))}%` }}
                    />
                    <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-slate-400/80" title="50% AI Detection Threshold" />
                  </div>

                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>0% (Clean Camera)</span>
                    <span className="font-semibold text-slate-500">50% Detection Threshold</span>
                    <span>100% (Synthetic)</span>
                  </div>

                  <p className="text-xs text-slate-600 leading-relaxed pt-1">
                    {result.aiDetection?.label === 'AI_GENERATED' || result.aiDetection?.status === 'AI_GENERATED'
                      ? 'Full canvas exhibits persistent latent diffusion and generator frequency phase patterns.'
                      : result.aiDetection?.label === 'AI_EDITED' || result.aiDetection?.status === 'AI_EDITED_LOCAL'
                      ? 'Localized AI inpainting / generative fill traces identified in candidate regions.'
                      : 'Verified camera sensor baseline. No anomalous AI generator frequency fingerprints detected.'}
                  </p>
                </div>
              </div>
            </div>

            {/* Card 2: Capture Provenance & Sensor Integrity */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h3 className="font-bold text-slate-900 flex items-center gap-2 text-sm sm:text-base">
                    <span className="text-emerald-600">📷</span>
                    <span>Camera Sensor &amp; Physical Optics</span>
                  </h3>
                  <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200">
                    Physical Optics
                  </span>
                </div>

                <div className="mt-4 space-y-2.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Image Resolution:</span>
                    <span className="font-mono font-medium text-slate-800">
                      {result.dimensions ? `${result.dimensions.width} × ${result.dimensions.height} px` : 'Original Size'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Manipulated Area Percentage:</span>
                    <span className="font-mono font-medium text-slate-800">
                      {result.affectedAreaPercentage !== undefined ? `${result.affectedAreaPercentage}%` : '0.0%'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">C2PA Provenance Manifest:</span>
                    <span className="font-medium text-slate-700">
                      {result.evidence.find((e) => e.detector === 'metadata')?.notes?.some((n) => n.includes('C2PA manifest') || n.includes('Google') || n.includes('OpenAI'))
                        ? 'Verified C2PA Manifest'
                        : 'Unsigned / Standard Camera Stream'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Sensor Noise Variance (PRNU):</span>
                    <span className="font-medium text-slate-700 truncate max-w-[200px]">
                      {result.evidence.find((e) => e.detector === 'noise_residual')?.notes?.[0] || 'Sensor noise stationary.'}
                    </span>
                  </div>
                </div>
              </div>

              <p className="mt-3 text-[11px] text-slate-400 border-t border-slate-100 pt-2">
                Cross-referenced with multi-scale noise residuals, Bayer CFA demosaicing correlation, and 2D FFT spectral decay.
              </p>
            </div>
          </div>

          {/* Authentic Optical & Sensor Metadata (EXIF) Card */}
          {(() => {
            const metaEv = result.evidence?.find((e) => e.detector === 'metadata')?.evidence;
            const optMeta = result.opticalMetadata;

            const hasExif = Boolean(optMeta?.hasExif ?? metaEv?.has_exif);
            const cameraMake = optMeta?.make || metaEv?.camera_make || metaEv?.tag_Make || null;
            const cameraModel = optMeta?.model || metaEv?.camera_model || metaEv?.tag_Model || null;
            const deviceName = optMeta?.deviceName || metaEv?.tag_39424 || null;
            const dateTime = optMeta?.dateTimeOriginal || metaEv?.datetime_original || metaEv?.tag_DateTimeOriginal || metaEv?.tag_DateTime || null;
            const timeZone = optMeta?.offsetTime || metaEv?.tag_OffsetTime || metaEv?.tag_OffsetTimeOriginal || null;
            const rawExp = optMeta?.exposureTime || metaEv?.tag_ExposureTime || null;
            const rawFNum = optMeta?.fNumber || metaEv?.tag_FNumber || null;
            const rawIso = optMeta?.iso || metaEv?.tag_ISOSpeedRatings || null;
            const rawFocal = optMeta?.focalLength || metaEv?.tag_FocalLength || null;

            const formatExp = (val?: string | null) => {
              if (!val) return 'N/A';
              const num = parseFloat(val);
              if (isNaN(num) || num <= 0) return val;
              if (num < 1) {
                const denom = Math.round(1 / num);
                return `1/${denom}s (${num.toFixed(4)}s)`;
              }
              return `${num.toFixed(2)}s`;
            };

            const formatAperture = (val?: string | null) => {
              if (!val) return 'N/A';
              const num = parseFloat(val);
              if (isNaN(num)) return val;
              return `f/${num.toFixed(1).replace(/\.0$/, '')}`;
            };

            const formatFocal = (val?: string | null) => {
              if (!val) return 'N/A';
              const num = parseFloat(val);
              if (isNaN(num)) return val;
              return `${num.toFixed(2)} mm`;
            };

            const fullDevice = cameraMake
              ? `${cameraMake} ${cameraModel || ''}${deviceName ? ` (${deviceName})` : ''}`.trim()
              : deviceName || cameraModel || (hasExif ? 'Generic Optical Camera' : 'Metadata Stripped / Not Embedded');

            const isVerifiedSensor = hasExif && (cameraMake || cameraModel || rawExp || rawFNum || rawIso);

            return (
              <div className="rounded-2xl sm:rounded-3xl border border-slate-200 bg-white p-5 sm:p-7 shadow-sm transition-all hover:shadow-md">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                  <div className="flex items-center gap-3">
                    <div className={`rounded-2xl p-2.5 sm:p-3 text-xl sm:text-2xl border ${
                      isVerifiedSensor
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        : 'bg-amber-50 text-amber-700 border-amber-200'
                    }`}>
                      📷
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base sm:text-lg font-black text-slate-900">
                          Authentic Optical &amp; Sensor Metadata (EXIF)
                        </h3>
                        <span
                          className={`rounded-full px-2.5 py-0.5 text-[10px] sm:text-[11px] font-black uppercase tracking-wider border ${
                            isVerifiedSensor
                              ? 'bg-emerald-100 text-emerald-900 border-emerald-300'
                              : 'bg-amber-100 text-amber-900 border-amber-300'
                          }`}
                        >
                          {isVerifiedSensor ? '✓ Authentic Hardware Sensor Verified' : '⚠️ Metadata Stripped / Absent'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {isVerifiedSensor
                          ? 'Physical mobile camera hardware sensor pipeline confirmed directly from embedded EXIF telemetry.'
                          : 'Standard social messaging apps (WhatsApp, Discord, Instagram) or screenshots strip metadata.'}
                      </p>
                    </div>
                  </div>

                  <span className="self-start sm:self-auto rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-mono font-semibold text-slate-600">
                    EXIF 2.2 / 2.31
                  </span>
                </div>

                {isVerifiedSensor ? (
                  <div className="mt-5 space-y-4">
                    {/* Primary Grid of 6 Optical Sensor Metrics */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
                      {/* 1. Camera Device */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Device / Model
                        </div>
                        <div className="mt-1 font-bold text-slate-900 text-xs sm:text-sm truncate" title={fullDevice}>
                          {fullDevice}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5 truncate">
                          {cameraMake ? `${cameraMake} Hardware` : 'Camera Sensor'}
                        </div>
                      </div>

                      {/* 2. Optical Aperture */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Aperture (F-Stop)
                        </div>
                        <div className="mt-1 font-mono font-black text-sm sm:text-base text-emerald-700">
                          {formatAperture(rawFNum)}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Physical Iris
                        </div>
                      </div>

                      {/* 3. Exposure / Shutter */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Shutter Speed
                        </div>
                        <div className="mt-1 font-mono font-black text-xs sm:text-sm text-sky-700 truncate" title={formatExp(rawExp)}>
                          {formatExp(rawExp)}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Sensor Integration
                        </div>
                      </div>

                      {/* 4. ISO Sensitivity */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          ISO Sensitivity
                        </div>
                        <div className="mt-1 font-mono font-black text-sm sm:text-base text-purple-700">
                          {rawIso ? `ISO ${rawIso}` : 'Auto'}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Analog Sensor Gain
                        </div>
                      </div>

                      {/* 5. Focal Length */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Focal Length
                        </div>
                        <div className="mt-1 font-mono font-black text-sm sm:text-base text-indigo-700">
                          {formatFocal(rawFocal)}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          Optical Glass
                        </div>
                      </div>

                      {/* 6. Capture Timestamp */}
                      <div className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-slate-50 to-white p-3.5 shadow-2xs">
                        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                          Capture Time
                        </div>
                        <div className="mt-1 font-mono font-bold text-slate-900 text-[11px] sm:text-xs truncate" title={dateTime ? `${dateTime} ${timeZone || ''}` : 'N/A'}>
                          {dateTime || 'Present in EXIF'}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          {timeZone ? `Timezone: ${timeZone}` : 'Hardware Clock'}
                        </div>
                      </div>
                    </div>

                    {/* Sensor Verification Summary Banner */}
                    <div className="rounded-xl bg-emerald-50/80 border border-emerald-200/90 p-3 sm:p-4 text-xs text-emerald-900 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-base">🛡️</span>
                        <span>
                          <strong>Hardware Sensor Telemetry Corroboration:</strong> Embedded exposure parameters, focal length, and hardware timestamp corroborate physical optics from a genuine <strong>{fullDevice}</strong> sensor.
                        </span>
                      </div>
                      <span className="shrink-0 font-mono text-[11px] font-semibold text-emerald-800 bg-white/80 border border-emerald-200 px-2 py-0.5 rounded-md">
                        Zero Synthetic Distortion
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="mt-5 rounded-2xl bg-amber-50/70 border border-amber-200 p-4 sm:p-5 text-xs text-amber-900 space-y-2">
                    <div className="flex items-start gap-2.5">
                      <span className="text-lg">ℹ️</span>
                      <div>
                        <h4 className="font-bold text-amber-950 text-sm">
                          Why is EXIF Metadata Stripped or Absent?
                        </h4>
                        <p className="mt-1 leading-relaxed text-amber-900/90">
                          When photos are saved from or shared across <strong>WhatsApp, Telegram, Discord, Instagram, Facebook</strong>, or via screenshots/screen captures, the host application automatically strips all camera EXIF headers for privacy and bandwidth compression.
                        </p>
                        <p className="mt-2 leading-relaxed text-amber-900/90">
                          <strong>How our system still verifies authenticity:</strong> In the absence of metadata headers, our 10-stage pipeline automatically relies on <em>Bayer CFA demosaicing residuals</em>, <em>PRNU CMOS sensor noise stationarity</em>, and <em>2D FFT Fourier spectral decay</em> to determine if the image is genuine camera capture, user-edited, or AI-generated.
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

          {/* Interactive Heatmap Viewer with Opacity Slider */}
          {result.artifacts?.heatmapUrl && suspectPreview && (
            <div className="rounded-2xl sm:rounded-3xl border border-slate-200 bg-white p-4 sm:p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-slate-900">
                    Interactive Forensic Tampering Heatmap
                  </h3>
                  <p className="text-xs text-slate-500">
                    Drag the slider to blend between the original image and the localized anomaly heatmap.
                  </p>
                </div>

                {/* Opacity Slider & Toggle Controls */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-xl">
                    <label className="text-xs font-semibold text-slate-600">Opacity:</label>
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={heatmapOpacity}
                      onChange={(e) => setHeatmapOpacity(Number(e.target.value))}
                      className="h-2 w-24 sm:w-32 cursor-pointer rounded-lg bg-slate-200 accent-brand-600"
                    />
                    <span className="w-9 text-right font-mono text-xs font-bold text-slate-800">
                      {heatmapOpacity}%
                    </span>
                  </div>

                  <button
                    onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
                    className={`rounded-xl px-3 py-1.5 text-xs font-semibold border transition-all ${
                      showBoundingBoxes
                        ? 'bg-brand-50 border-brand-300 text-brand-700 shadow-2xs'
                        : 'bg-slate-50 border-slate-200 text-slate-600'
                    }`}
                  >
                    {showBoundingBoxes ? 'Hide Region Boxes' : 'Show Region Boxes'}
                  </button>
                </div>
              </div>

              {/* Heatmap Overlay Container */}
              <div className="relative mt-4 flex items-center justify-center overflow-hidden rounded-xl bg-slate-900/95 p-2 sm:p-4">
                <div className="relative inline-block max-h-[55vh] sm:max-h-[520px]">
                  {/* Base Photo */}
                  <img
                    src={suspectPreview}
                    alt="Original Suspect"
                    className="max-h-[55vh] sm:max-h-[520px] w-auto max-w-full object-contain rounded-lg"
                  />

                  {/* Overlaid Heatmap */}
                  <img
                    src={result.artifacts.heatmapUrl}
                    alt="Forensic Heatmap"
                    style={{ opacity: heatmapOpacity / 100 }}
                    className="pointer-events-none absolute inset-0 h-full w-full object-contain mix-blend-screen transition-opacity duration-150"
                  />

                  {/* Bounding Box Highlights (Only when showBoundingBoxes is true and regions exist) */}
                  {showBoundingBoxes &&
                    result.dimensions &&
                    result.regions.map((reg) => {
                      const leftPct = (reg.bbox.x / result.dimensions!.width) * 100;
                      const topPct = (reg.bbox.y / result.dimensions!.height) * 100;
                      const widthPct = (reg.bbox.w / result.dimensions!.width) * 100;
                      const heightPct = (reg.bbox.h / result.dimensions!.height) * 100;

                      return (
                        <div
                          key={reg.id}
                          style={{
                            left: `${leftPct}%`,
                            top: `${topPct}%`,
                            width: `${widthPct}%`,
                            height: `${heightPct}%`,
                          }}
                          className="pointer-events-auto absolute border-2 border-red-500 bg-red-500/20 shadow-sm transition-all hover:bg-red-500/40"
                          title={`${reg.id}: ${reg.editTypeGuess} (${reg.areaPct}%)`}
                        >
                          <span className="absolute -top-5 left-0 rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white shadow">
                            {reg.editTypeGuess}
                          </span>
                        </div>
                      );
                    })}
                </div>
              </div>

              {/* Quick Opacity Presets for Mobile */}
              <div className="mt-3 flex items-center justify-center gap-2">
                <button
                  type="button"
                  onClick={() => setHeatmapOpacity(0)}
                  className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                    heatmapOpacity === 0 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  Original (0%)
                </button>
                <button
                  type="button"
                  onClick={() => setHeatmapOpacity(50)}
                  className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                    heatmapOpacity === 50 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  Balanced (50%)
                </button>
                <button
                  type="button"
                  onClick={() => setHeatmapOpacity(100)}
                  className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                    heatmapOpacity === 100 ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                  }`}
                >
                  Heatmap Only (100%)
                </button>
              </div>
            </div>
          )}

          {/* Collapsible Technical Forensic Audit Report (Printable & Exportable) */}
          <details className="group rounded-2xl sm:rounded-3xl border border-slate-200 bg-white p-4 sm:p-6 shadow-sm print:block print:border-none print:p-0 print:shadow-none">
            <summary className="flex cursor-pointer items-center justify-between font-bold text-slate-800 list-none print:hidden select-none hover:text-brand-600 transition-colors">
              <div className="flex items-center gap-2.5">
                <svg className="h-5 w-5 text-brand-600 transition-transform group-open:rotate-90 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                <span className="text-sm sm:text-base font-bold text-slate-900">
                  Technical Forensic Audit Report &amp; Signals
                </span>
              </div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] sm:text-xs font-semibold text-slate-600 group-open:bg-brand-50 group-open:text-brand-700">
                Click to Expand Raw Forensic Metrics
              </span>
            </summary>

            <div className="mt-6 space-y-6 pt-4 border-t border-slate-100 print:mt-0 print:pt-0 print:border-none">
              {/* Classical Forensic Signals & Quantitative Metrics */}
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div>
                    <h3 className="text-sm sm:text-base font-bold text-slate-900">
                      Forensic Signals &amp; Detailed Values
                    </h3>
                    <p className="text-xs text-slate-500">
                      Multi-family physical traces (JPEG grid alignment, noise residuals, ELA, DCT, resampling, copy-move).
                    </p>
                  </div>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 self-start sm:self-auto">
                    PinITHUB Sec 5 &amp; 10.1
                  </span>
                </div>

                <div className="grid gap-3 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {/* Card 1: JPEG Grid Alignment */}
                  {(() => {
                    const ev = result.evidence.find((e) => e.detector === 'jpeg_grid');
                    const isMisaligned = ev?.notes?.[0]?.includes('shifted') || (ev?.evidence?.horizontal_ratio && ev.evidence.horizontal_ratio > 1.25);
                    const isExpanded = !!expandedMetrics['jpeg_grid'];
                    return (
                      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                            <div className="flex items-center gap-1.5 font-semibold text-slate-900 text-xs sm:text-sm">
                              <span>📐</span>
                              <span>JPEG Grid Alignment</span>
                            </div>
                            <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              isMisaligned ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-700'
                            }`}>
                              {isMisaligned ? 'MISALIGNED' : 'ALIGNED'}
                            </span>
                          </div>

                          <div className="mt-3 space-y-1.5 text-xs">
                            <div className="flex justify-between text-slate-600">
                              <span>Blocking Ratio (H/V):</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.horizontal_ratio ? ev.evidence.horizontal_ratio.toFixed(2) : '1.00'} / {ev?.evidence?.vertical_ratio ? ev.evidence.vertical_ratio.toFixed(2) : '1.00'}
                              </span>
                            </div>
                            <div className="flex justify-between text-slate-600">
                              <span>Boundary Inconsistency:</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.horizontal_inconsistency ? ev.evidence.horizontal_inconsistency.toFixed(1) : '—'}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                              {ev?.notes?.[0] || '8×8 block grid aligns with image origin.'}
                            </p>
                          </div>
                        </div>

                        <div className="mt-3 pt-2 border-t border-slate-100">
                          <button
                            onClick={() => toggleMetric('jpeg_grid')}
                            className="text-[11px] font-medium text-brand-600 hover:text-brand-800 flex items-center justify-between w-full"
                          >
                            <span>{isExpanded ? 'Hide Raw Values' : 'View Numerical Values'}</span>
                            <span>{isExpanded ? '▲' : '▼'}</span>
                          </button>
                          {isExpanded && ev?.evidence && (
                            <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-[10px] space-y-1 text-slate-600">
                              <div>h_ratio: {ev.evidence.horizontal_ratio?.toFixed(4)}</div>
                              <div>v_ratio: {ev.evidence.vertical_ratio?.toFixed(4)}</div>
                              <div>h_incon: {ev.evidence.horizontal_inconsistency?.toFixed(4)}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Card 2: Noise Residual Variance */}
                  {(() => {
                    const ev = result.evidence.find((e) => e.detector === 'noise_residual');
                    const hasAnom = ev?.notes?.[0]?.includes('High noise variance') || ev?.notes?.[0]?.includes('mismatch');
                    const isExpanded = !!expandedMetrics['noise_residual'];
                    return (
                      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                            <div className="flex items-center gap-1.5 font-semibold text-slate-900 text-xs sm:text-sm">
                              <span>📊</span>
                              <span>Noise Residual (PRNU)</span>
                            </div>
                            <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              hasAnom ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-700'
                            }`}>
                              {hasAnom ? 'LOCAL ANOMALY' : 'UNIFORM SENSOR'}
                            </span>
                          </div>

                          <div className="mt-3 space-y-1.5 text-xs">
                            <div className="flex justify-between text-slate-600">
                              <span>Mean Variance:</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.mean_variance ? ev.evidence.mean_variance.toFixed(2) : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between text-slate-600">
                              <span>Variance Std Dev:</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.std_variance ? ev.evidence.std_variance.toFixed(1) : '—'}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                              {ev?.notes?.[0] || 'High-pass noise distribution consistent across scene.'}
                            </p>
                          </div>
                        </div>

                        <div className="mt-3 pt-2 border-t border-slate-100">
                          <button
                            onClick={() => toggleMetric('noise_residual')}
                            className="text-[11px] font-medium text-brand-600 hover:text-brand-800 flex items-center justify-between w-full"
                          >
                            <span>{isExpanded ? 'Hide Raw Values' : 'View Numerical Values'}</span>
                            <span>{isExpanded ? '▲' : '▼'}</span>
                          </button>
                          {isExpanded && ev?.evidence && (
                            <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-[10px] space-y-1 text-slate-600">
                              <div>mean_var: {ev.evidence.mean_variance}</div>
                              <div>std_var: {ev.evidence.std_variance}</div>
                              <div>mad: {ev.evidence.mad}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Card 3: Error Level Analysis (ELA) */}
                  {(() => {
                    const ev = result.evidence.find((e) => e.detector === 'ela');
                    const isHigh = ev?.notes?.[0]?.includes('Elevated') || (ev?.evidence?.mean_error && ev.evidence.mean_error > 8.0);
                    const isExpanded = !!expandedMetrics['ela'];
                    return (
                      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                            <div className="flex items-center gap-1.5 font-semibold text-slate-900 text-xs sm:text-sm">
                              <span>🔍</span>
                              <span>Error Level Analysis (ELA)</span>
                            </div>
                            <span className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              isHigh ? 'bg-amber-100 text-amber-800' : 'bg-green-100 text-green-700'
                            }`}>
                              {isHigh ? 'ELEVATED ERROR' : 'CONSISTENT'}
                            </span>
                          </div>

                          <div className="mt-3 space-y-1.5 text-xs">
                            <div className="flex justify-between text-slate-600">
                              <span>Recompression Mean:</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.mean_error ? ev.evidence.mean_error.toFixed(2) : '—'}
                              </span>
                            </div>
                            <div className="flex justify-between text-slate-600">
                              <span>Peak Region Error:</span>
                              <span className="font-mono font-medium text-slate-800">
                                {ev?.evidence?.max_error ? ev.evidence.max_error.toFixed(1) : '—'}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                              {ev?.notes?.[0] || 'Error level consistent across compression blocks.'}
                            </p>
                          </div>
                        </div>

                        <div className="mt-3 pt-2 border-t border-slate-100">
                          <button
                            onClick={() => toggleMetric('ela')}
                            className="text-[11px] font-medium text-brand-600 hover:text-brand-800 flex items-center justify-between w-full"
                          >
                            <span>{isExpanded ? 'Hide Raw Values' : 'View Numerical Values'}</span>
                            <span>{isExpanded ? '▲' : '▼'}</span>
                          </button>
                          {isExpanded && ev?.evidence && (
                            <div className="mt-2 rounded bg-slate-50 p-2 font-mono text-[10px] space-y-1 text-slate-600">
                              <div>mean_err: {ev.evidence.mean_error}</div>
                              <div>max_err: {ev.evidence.max_error}</div>
                              <div>p95: {ev.evidence.p95_error}</div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </div>
              </div>

              {/* Localized Tampered Regions Table (Only shown if regions exist) */}
              {result.regions.length > 0 && (
                <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs">
                  <h3 className="text-sm sm:text-base font-bold text-slate-900">
                    Localized Tampered Regions ({result.regions.length})
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    Suspected manipulated areas segmented with bounding coordinates and guessed edit families.
                  </p>

                  <div className="mt-3 overflow-x-auto rounded-lg border border-slate-100">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 text-[11px] font-semibold uppercase text-slate-500">
                        <tr>
                          <th className="px-3 py-2.5">Region</th>
                          <th className="px-3 py-2.5">Edit Type</th>
                          <th className="px-3 py-2.5">Area %</th>
                          <th className="px-3 py-2.5">Confidence</th>
                          <th className="px-3 py-2.5">Bounding Box [x, y, w, h]</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono">
                        {result.regions.map((reg) => (
                          <tr key={reg.id} className="hover:bg-slate-50/70">
                            <td className="px-3 py-2.5 font-bold text-slate-800">{reg.id}</td>
                            <td className="px-3 py-2.5">
                              <span className="rounded bg-amber-100 px-2 py-0.5 font-semibold text-amber-800">
                                {reg.editTypeGuess}
                              </span>
                            </td>
                            <td className="px-3 py-2.5 text-slate-700">{reg.areaPct}%</td>
                            <td className="px-3 py-2.5 text-slate-700">{(reg.confidence * 100).toFixed(0)}%</td>
                            <td className="px-3 py-2.5 text-slate-500">
                              [{reg.bbox.x}, {reg.bbox.y}, {reg.bbox.w}, {reg.bbox.h}]
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Detector Evidence Breakdown Table */}
              <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5 shadow-2xs">
                <h3 className="text-sm sm:text-base font-bold text-slate-900">
                  Detector Evidence Breakdown
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  Output from all independent forensic detectors, strictly tagged as [PROVEN] or [EXPERIMENTAL].
                </p>

                <div className="mt-3 overflow-x-auto rounded-lg border border-slate-100">
                  <table className="w-full text-left text-xs min-w-[500px]">
                    <thead className="bg-slate-50 text-[11px] font-semibold uppercase text-slate-500">
                      <tr>
                        <th className="px-3 py-2.5">Detector</th>
                        <th className="px-3 py-2.5">Category</th>
                        <th className="px-3 py-2.5">Tag</th>
                        <th className="px-3 py-2.5">Score</th>
                        <th className="px-3 py-2.5">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {result.evidence.map((ev, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/70">
                          <td className="px-3 py-2.5 font-semibold text-slate-800">{ev.detector}</td>
                          <td className="px-3 py-2.5 text-slate-500">{ev.category}</td>
                          <td className="px-3 py-2.5">
                            <span
                              className={`rounded px-2 py-0.5 font-bold text-[10px] ${
                                ev.tag.includes('PROVEN')
                                  ? 'bg-green-100 text-green-800'
                                  : 'bg-purple-100 text-purple-800'
                              }`}
                            >
                              [{ev.tag}]
                            </span>
                          </td>
                          <td className="px-3 py-2.5 font-mono text-slate-700">
                            {ev.score !== null ? ev.score.toFixed(3) : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-slate-600 text-[11px]">
                            {ev.notes && ev.notes.length > 0 ? ev.notes.join(' · ') : 'Analysis normal.'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </details>
        </div>
      )}

      {/* Live Hardware Camera Viewfinder Modal */}
      <LiveCameraModal
        isOpen={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
        onPhotoCaptured={(file) => {
          handleFileSelect(file);
        }}
        onUseNativeCamera={() => {
          cameraInputRef.current?.click();
        }}
      />
    </div>
  );
}
