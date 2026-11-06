import React, { useState, useRef, useCallback, useEffect } from 'react';

export interface ForensicRegion {
  id: string;
  bbox: { x: number; y: number; w: number; h: number };
  areaPct: number;
  confidence: number;
  editTypeGuess: string;
}

export interface ForensicWorkstationViewerProps {
  suspectPreview: string;
  heatmapUrl?: string;
  maskUrl?: string;
  dimensions?: { width: number; height: number };
  regions?: ForensicRegion[];
  classification?: string;
  executionMs?: number;
}

type ViewMode = 'blend' | 'curtain' | 'grid' | 'high_contrast';

export const ForensicWorkstationViewer: React.FC<ForensicWorkstationViewerProps> = ({
  suspectPreview,
  heatmapUrl,
  dimensions,
  regions = [],
  executionMs,
}) => {
  const [viewMode, setViewMode] = useState<ViewMode>('blend');
  const [heatmapOpacity, setHeatmapOpacity] = useState<number>(65);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState<boolean>(true);
  const [showGrid, setShowGrid] = useState<boolean>(false);
  const [showLoupe, setShowLoupe] = useState<boolean>(false);
  const [showCrosshairs, setShowCrosshairs] = useState<boolean>(true);
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [curtainPos, setCurtainPos] = useState<number>(50); // percentage 0-100
  const [isDraggingCurtain, setIsDraggingCurtain] = useState<boolean>(false);
  const [activeRegionId, setActiveRegionId] = useState<string | null>(null);

  // Mouse telemetry state
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number; normX: number; normY: number }>({
    x: 0,
    y: 0,
    normX: 0,
    normY: 0,
  });
  const [isHovering, setIsHovering] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  // Calculate coordinates relative to image on mouse move
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!imageRef.current || !containerRef.current) return;
      const rect = imageRef.current.getBoundingClientRect();
      const clientX = e.clientX;
      const clientY = e.clientY;

      if (clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom) {
        const normX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const normY = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));

        const pixelX = dimensions ? Math.round(normX * dimensions.width) : Math.round(normX * 1000);
        const pixelY = dimensions ? Math.round(normY * dimensions.height) : Math.round(normY * 1000);

        setCursorPos({ x: pixelX, y: pixelY, normX, normY });
        setIsHovering(true);

        if (isDraggingCurtain && viewMode === 'curtain') {
          setCurtainPos(Math.round(normX * 100));
        }
      } else {
        setIsHovering(false);
      }
    },
    [dimensions, isDraggingCurtain, viewMode]
  );

  const handleMouseLeave = () => {
    setIsHovering(false);
    setIsDraggingCurtain(false);
  };

  const handleCurtainDragStart = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingCurtain(true);
  };

  useEffect(() => {
    const handleGlobalMouseUp = () => setIsDraggingCurtain(false);
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, []);

  return (
    <div className="rounded-2xl sm:rounded-3xl border border-slate-800 bg-slate-950 text-slate-100 shadow-xl overflow-hidden font-sans transition-all">
      {/* 1. Forensic Workstation Header Toolbar */}
      <div className="border-b border-slate-800/80 bg-slate-900/90 px-4 py-3 sm:px-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-cyan-500" />
            </span>
            <span className="font-mono text-xs font-bold tracking-wider text-cyan-400 uppercase">
              FORENSIC INSPECTION WORKSTATION
            </span>
          </div>

          <span className="hidden sm:inline-block h-3.5 w-px bg-slate-700" />

          <span className="text-[11px] font-mono text-slate-400">
            TELEMETRY: <span className="text-emerald-400 font-semibold">ACTIVE</span>
            {executionMs && <span className="ml-2 text-slate-500">({executionMs}ms)</span>}
          </span>
        </div>

        {/* Tactical View Mode Switcher */}
        <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800">
          <button
            type="button"
            onClick={() => setViewMode('blend')}
            className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition-colors ${
              viewMode === 'blend'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-xs'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            HEATMAP BLEND
          </button>

          <button
            type="button"
            onClick={() => setViewMode('curtain')}
            className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition-colors ${
              viewMode === 'curtain'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-xs'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            SPLIT CURTAIN
          </button>

          <button
            type="button"
            onClick={() => setViewMode('high_contrast')}
            className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition-colors ${
              viewMode === 'high_contrast'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-xs'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            HIGH-PASS EDGE
          </button>
        </div>
      </div>

      {/* 2. Tactical Inspection Secondary Controls */}
      <div className="border-b border-slate-800/60 bg-slate-900/40 px-4 py-2 sm:px-6 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        {/* Left: Heatmap Opacity & Controls */}
        <div className="flex flex-wrap items-center gap-4">
          {viewMode === 'blend' && heatmapUrl && (
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-[11px]">ALPHA BLEND:</span>
              <input
                type="range"
                min="0"
                max="100"
                value={heatmapOpacity}
                onChange={(e) => setHeatmapOpacity(Number(e.target.value))}
                className="h-1.5 w-24 sm:w-32 cursor-pointer rounded-lg bg-slate-800 accent-cyan-400"
              />
              <span className="w-8 text-right font-bold text-cyan-300">{heatmapOpacity}%</span>
            </div>
          )}

          {viewMode === 'curtain' && (
            <div className="flex items-center gap-2 text-slate-400 text-[11px]">
              <span>DIVIDER POSITION:</span>
              <span className="text-cyan-300 font-bold">{curtainPos}%</span>
              <span className="text-slate-500 hidden sm:inline">(DRAG CENTER HANDLE)</span>
            </div>
          )}
        </div>

        {/* Right: Tactical Optical Toggles */}
        <div className="flex items-center gap-2">
          {/* 8x8 DCT Grid Overlay Toggle */}
          <button
            type="button"
            onClick={() => setShowGrid(!showGrid)}
            className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono transition-colors ${
              showGrid
                ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-300'
                : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
            }`}
            title="Overlay 8x8 JPEG Macroblock DCT Grid to spot grid shifts"
          >
            8×8 DCT GRID {showGrid ? 'ON' : 'OFF'}
          </button>

          {/* Subpixel Loupe Magnifier Toggle */}
          <button
            type="button"
            onClick={() => setShowLoupe(!showLoupe)}
            className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono transition-colors ${
              showLoupe
                ? 'bg-amber-500/20 border-amber-500/50 text-amber-300'
                : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
            }`}
            title="Hover magnifier loupe for subpixel edge inspection"
          >
            LOUPE {showLoupe ? 'ON' : 'OFF'}
          </button>

          {/* Crosshair Reticle Toggle */}
          <button
            type="button"
            onClick={() => setShowCrosshairs(!showCrosshairs)}
            className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono transition-colors ${
              showCrosshairs
                ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-300'
                : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
            }`}
            title="Toggle coordinate crosshairs"
          >
            RETICLE
          </button>

          {/* Region Bounding Box Toggle */}
          {regions.length > 0 && (
            <button
              type="button"
              onClick={() => setShowBoundingBoxes(!showBoundingBoxes)}
              className={`px-2.5 py-1 rounded-lg border text-[11px] font-mono transition-colors ${
                showBoundingBoxes
                  ? 'bg-rose-500/20 border-rose-500/50 text-rose-300'
                  : 'border-slate-800 bg-slate-900 text-slate-400 hover:text-slate-200'
              }`}
            >
              REGIONS ({regions.length})
            </button>
          )}

          {/* Zoom Controls */}
          <div className="flex items-center rounded-lg border border-slate-800 bg-slate-900 overflow-hidden">
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.max(1, Number((z - 0.25).toFixed(2))))}
              className="px-2 py-0.5 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Zoom Out"
            >
              −
            </button>
            <span className="px-2 py-0.5 text-[11px] text-cyan-300 font-bold">{Math.round(zoomLevel * 100)}%</span>
            <button
              type="button"
              onClick={() => setZoomLevel((z) => Math.min(2.5, Number((z + 0.25).toFixed(2))))}
              className="px-2 py-0.5 text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Zoom In"
            >
              +
            </button>
          </div>
        </div>
      </div>

      {/* 3. Main Optical Canvas Area */}
      <div
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="relative flex items-center justify-center p-4 sm:p-8 min-h-[420px] max-h-[72vh] overflow-hidden select-none bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px]"
      >
        {/* Tactical Corner Brackets */}
        <div className="pointer-events-none absolute top-3 left-3 w-4 h-4 border-t-2 border-l-2 border-cyan-500/60" />
        <div className="pointer-events-none absolute top-3 right-3 w-4 h-4 border-t-2 border-r-2 border-cyan-500/60" />
        <div className="pointer-events-none absolute bottom-3 left-3 w-4 h-4 border-b-2 border-l-2 border-cyan-500/60" />
        <div className="pointer-events-none absolute bottom-3 right-3 w-4 h-4 border-b-2 border-r-2 border-cyan-500/60" />

        {/* Live Coordinate HUD Overlay (Top Left of Canvas) */}
        <div className="pointer-events-none absolute top-4 left-5 z-20 flex flex-col gap-1 font-mono text-[11px] text-slate-400 bg-slate-950/80 p-2 rounded-lg border border-slate-800 backdrop-blur-xs">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 font-bold">X:</span>
            <span className="w-10 text-right text-slate-100">{isHovering ? cursorPos.x : '---'}</span>
            <span className="text-cyan-400 font-bold ml-1">Y:</span>
            <span className="w-10 text-right text-slate-100">{isHovering ? cursorPos.y : '---'}</span>
          </div>
          <div className="text-[10px] text-slate-500 border-t border-slate-800/80 pt-1">
            CANVAS: {dimensions ? `${dimensions.width}×${dimensions.height}px` : 'AUTO'} | ZOOM: {Math.round(zoomLevel * 100)}%
          </div>
        </div>

        {/* Target Reticle Laser Lines */}
        {showCrosshairs && isHovering && (
          <>
            {/* Horizontal Crosshair Line */}
            <div
              className="pointer-events-none absolute left-0 right-0 z-20 h-px bg-cyan-400/40"
              style={{
                top: imageRef.current
                  ? imageRef.current.offsetTop + cursorPos.normY * imageRef.current.offsetHeight
                  : 0,
              }}
            />
            {/* Vertical Crosshair Line */}
            <div
              className="pointer-events-none absolute top-0 bottom-0 z-20 w-px bg-cyan-400/40"
              style={{
                left: imageRef.current
                  ? imageRef.current.offsetLeft + cursorPos.normX * imageRef.current.offsetWidth
                  : 0,
              }}
            />
          </>
        )}

        {/* Centered Image Container with Zoom */}
        <div
          style={{ transform: `scale(${zoomLevel})`, transformOrigin: 'center center' }}
          className="relative inline-block max-h-[58vh] max-w-full transition-transform duration-100 shadow-2xl"
        >
          {/* Base Suspect Image */}
          <img
            ref={imageRef}
            src={suspectPreview}
            alt="Suspect Image for Forensic Analysis"
            className={`max-h-[58vh] max-w-full w-auto object-contain rounded-md block transition-all ${
              viewMode === 'high_contrast' ? 'filter contrast-[220%] brightness-[90%]' : ''
            }`}
          />

          {/* Mode 1: Alpha Blend Heatmap */}
          {viewMode === 'blend' && heatmapUrl && (
            <img
              src={heatmapUrl}
              alt="Forensic Heatmap Layer"
              style={{ opacity: heatmapOpacity / 100 }}
              className="pointer-events-none absolute inset-0 h-full w-full object-contain mix-blend-screen transition-opacity duration-150"
            />
          )}

          {/* Mode 2: Interactive Split Curtain Comparison */}
          {viewMode === 'curtain' && heatmapUrl && (
            <div
              className="pointer-events-none absolute inset-0 overflow-hidden"
              style={{ clipPath: `inset(0 0 0 ${curtainPos}%)` }}
            >
              <img
                src={heatmapUrl}
                alt="Curtain Heatmap Reveal"
                className="pointer-events-none absolute inset-0 h-full w-full object-contain mix-blend-screen"
              />
            </div>
          )}

          {/* Mode 2: Curtain Draggable Divider Bar */}
          {viewMode === 'curtain' && (
            <div
              onMouseDown={handleCurtainDragStart}
              style={{ left: `${curtainPos}%` }}
              className="pointer-events-auto absolute inset-y-0 -ml-2 w-4 cursor-ew-resize flex items-center justify-center z-30 group"
            >
              <div className="w-0.5 h-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" />
              <div className="absolute h-8 w-8 rounded-full border-2 border-cyan-400 bg-slate-950 flex items-center justify-center shadow-lg text-[10px] text-cyan-300 font-mono font-bold group-hover:scale-110 transition-transform">
                ⇄
              </div>
            </div>
          )}

          {/* 8x8 DCT Macroblock Grid Overlay */}
          {showGrid && (
            <div className="pointer-events-none absolute inset-0 z-10 bg-[linear-gradient(to_right,#06b6d418_1px,transparent_1px),linear-gradient(to_bottom,#06b6d418_1px,transparent_1px)] [background-size:8px_8px]" />
          )}

          {/* Bounding Boxes for Localized Edits */}
          {showBoundingBoxes &&
            dimensions &&
            regions.map((reg, idx) => {
              const leftPct = (reg.bbox.x / dimensions.width) * 100;
              const topPct = (reg.bbox.y / dimensions.height) * 100;
              const widthPct = (reg.bbox.w / dimensions.width) * 100;
              const heightPct = (reg.bbox.h / dimensions.height) * 100;
              const isActive = activeRegionId === reg.id;

              return (
                <div
                  key={reg.id}
                  onClick={() => setActiveRegionId(isActive ? null : reg.id)}
                  style={{
                    left: `${leftPct}%`,
                    top: `${topPct}%`,
                    width: `${widthPct}%`,
                    height: `${heightPct}%`,
                  }}
                  className={`pointer-events-auto absolute border-2 transition-all cursor-pointer ${
                    isActive
                      ? 'border-amber-400 bg-amber-400/30 shadow-[0_0_15px_rgba(251,191,36,0.6)] z-20'
                      : 'border-red-500 bg-red-500/20 hover:bg-red-500/40 z-10'
                  }`}
                >
                  <span className="absolute -top-5 left-0 rounded-md bg-slate-950/90 border border-red-500/80 px-1.5 py-0.5 text-[9px] font-mono font-bold text-red-400 shadow-sm whitespace-nowrap">
                    #{idx + 1} {reg.editTypeGuess} [{reg.areaPct}%]
                  </span>
                </div>
              );
            })}
        </div>

        {/* Floating Subpixel Loupe Magnifier (Follows Cursor) */}
        {showLoupe && isHovering && imageRef.current && (
          <div
            className="pointer-events-none absolute z-40 w-36 h-36 rounded-full border-2 border-amber-400 bg-slate-950 overflow-hidden shadow-[0_0_20px_rgba(251,191,36,0.4)]"
            style={{
              left: cursorPos.normX * imageRef.current.offsetWidth + imageRef.current.offsetLeft + 20,
              top: cursorPos.normY * imageRef.current.offsetHeight + imageRef.current.offsetTop - 72,
            }}
          >
            {/* Magnified Image Projection */}
            <div
              className="absolute w-full h-full"
              style={{
                backgroundImage: `url(${suspectPreview})`,
                backgroundPosition: `${cursorPos.normX * 100}% ${cursorPos.normY * 100}%`,
                backgroundSize: `${dimensions ? dimensions.width * 2.5 : 2000}px`,
                backgroundRepeat: 'no-repeat',
              }}
            />
            {/* Loupe Crosshair Target */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-4 h-4 border border-amber-400/80 rounded-full" />
              <div className="absolute h-full w-px bg-amber-400/40" />
              <div className="absolute w-full h-px bg-amber-400/40" />
            </div>
            <div className="absolute bottom-1 right-2 text-[9px] font-mono text-amber-300 bg-slate-950/90 px-1 rounded">
              3× ZOOM
            </div>
          </div>
        )}
      </div>

      {/* 4. Forensic Region Inspection Strip (When Regions Are Present) */}
      {regions.length > 0 && (
        <div className="border-t border-slate-800 bg-slate-900/70 p-3 sm:p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono font-bold text-slate-300 uppercase flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
              IDENTIFIED ANOMALY REGIONS ({regions.length})
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              CLICK ANY REGION TO HIGHLIGHT ON CANVAS
            </span>
          </div>

          <div className="grid gap-2 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 max-h-36 overflow-y-auto pr-1">
            {regions.map((reg, idx) => {
              const isSelected = activeRegionId === reg.id;
              return (
                <div
                  key={reg.id}
                  onClick={() => setActiveRegionId(isSelected ? null : reg.id)}
                  className={`p-2 rounded-xl border text-xs font-mono cursor-pointer transition-all ${
                    isSelected
                      ? 'border-amber-400 bg-amber-400/10 text-amber-200 shadow-xs'
                      : 'border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between font-bold mb-1">
                    <span className="text-red-400">#{idx + 1}: {reg.editTypeGuess}</span>
                    <span className="text-slate-400 text-[11px]">{reg.areaPct}%</span>
                  </div>
                  <div className="text-[10px] text-slate-500">
                    BBox: [{reg.bbox.x}, {reg.bbox.y}, {reg.bbox.w}×{reg.bbox.h}px]
                  </div>
                  <div className="text-[10px] text-emerald-400 font-semibold mt-0.5">
                    Confidence: {(reg.confidence * 100).toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 5. Telemetry Footer Legend */}
      <div className="border-t border-slate-800/80 bg-slate-950 px-4 py-2 sm:px-6 flex flex-wrap items-center justify-between gap-3 text-[11px] font-mono text-slate-500">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-red-500" />
            <span>LOCALIZED TAMPERING</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-cyan-400" />
            <span>SPECTRAL HEATMAP</span>
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm bg-emerald-400" />
            <span>8×8 DCT MACROBLOCKS</span>
          </span>
        </div>

        <div className="text-slate-500">
          MODE: <span className="text-slate-300 font-bold uppercase">{viewMode}</span> | RENDER: COMPOSITE HEATMAP
        </div>
      </div>
    </div>
  );
};

export default ForensicWorkstationViewer;
