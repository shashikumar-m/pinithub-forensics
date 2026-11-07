import React, { useRef, useEffect, useState, useCallback } from 'react';

export interface Forensic3DSurfaceViewerProps {
  heatmapUrl?: string;
  suspectPreview?: string;
  dimensions?: { width: number; height: number };
}

type RenderStyle = 'shaded' | 'wireframe' | 'hybrid';

export const Forensic3DSurfaceViewer: React.FC<Forensic3DSurfaceViewerProps> = ({
  heatmapUrl,
  suspectPreview,
  dimensions,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [rotX, setRotX] = useState<number>(38); // degrees pitch
  const [rotY, setRotY] = useState<number>(-42); // degrees yaw
  const [zoom, setZoom] = useState<number>(1.15);
  const [elevationScale, setElevationScale] = useState<number>(1.8);
  const [renderStyle, setRenderStyle] = useState<RenderStyle>('hybrid');
  const [autoRotate, setAutoRotate] = useState<boolean>(true);
  const [peakStats, setPeakStats] = useState<{ maxVal: number; peakX: number; peakY: number }>({
    maxVal: 0,
    peakX: 0,
    peakY: 0,
  });

  const isDraggingRef = useRef<boolean>(false);
  const lastMousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const heightDataRef = useRef<Float32Array | null>(null);
  const gridDim = 56; // 56x56 grid = 3,136 vertices

  // Sample elevation data from heatmap (or fallback to suspect luminosity)
  useEffect(() => {
    const srcUrl = heatmapUrl || suspectPreview;
    if (!srcUrl) return;

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const offCanvas = document.createElement('canvas');
      offCanvas.width = gridDim;
      offCanvas.height = gridDim;
      const ctx = offCanvas.getContext('2d');
      if (!ctx) return;

      ctx.drawImage(img, 0, 0, gridDim, gridDim);
      const imgData = ctx.getImageData(0, 0, gridDim, gridDim);
      const data = imgData.data;

      const heights = new Float32Array(gridDim * gridDim);
      let maxVal = 0;
      let peakIdx = 0;

      for (let i = 0; i < gridDim * gridDim; i++) {
        const r = data[i * 4];
        const g = data[i * 4 + 1];
        const b = data[i * 4 + 2];

        // If heatmapUrl: red channel represents anomaly heat
        // If suspect image: calculate luminance disparity
        let val = heatmapUrl ? (r * 0.75 + g * 0.25) / 255.0 : (0.299 * r + 0.587 * g + 0.114 * b) / 255.0;

        // Apply slight non-linear contrast so tampering peaks stand out sharply
        val = Math.pow(val, 1.4);
        heights[i] = val;

        if (val > maxVal) {
          maxVal = val;
          peakIdx = i;
        }
      }

      heightDataRef.current = heights;
      const px = dimensions ? Math.round(((peakIdx % gridDim) / gridDim) * dimensions.width) : Math.round(((peakIdx % gridDim) / gridDim) * 512);
      const py = dimensions ? Math.round((Math.floor(peakIdx / gridDim) / gridDim) * dimensions.height) : Math.round((Math.floor(peakIdx / gridDim) / gridDim) * 512);

      setPeakStats({
        maxVal: Math.round(maxVal * 100),
        peakX: px,
        peakY: py,
      });
    };
    img.src = srcUrl;
  }, [heatmapUrl, suspectPreview, dimensions]);

  // Main 3D Render Loop
  const render3D = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const heights = heightDataRef.current;
    if (!heights) {
      ctx.fillStyle = '#64748b';
      ctx.font = '12px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('EXTRACTING 3D SPECTRAL MESH...', width / 2, height / 2);
      return;
    }

    const radX = (rotX * Math.PI) / 180;
    const radY = (rotY * Math.PI) / 180;
    const cosX = Math.cos(radX);
    const sinX = Math.sin(radX);
    const cosY = Math.cos(radY);
    const sinY = Math.sin(radY);

    const scale = Math.min(width, height) * 0.65 * zoom;
    const cx = width / 2;
    const cy = height / 2 + 30;
    const elev = elevationScale * 75;

    // Projected vertices array
    const projX = new Float32Array(gridDim * gridDim);
    const projY = new Float32Array(gridDim * gridDim);
    const projZ = new Float32Array(gridDim * gridDim);

    for (let gy = 0; gy < gridDim; gy++) {
      for (let gx = 0; gx < gridDim; gx++) {
        const idx = gy * gridDim + gx;
        const normX = gx / (gridDim - 1) - 0.5;
        const normZ = gy / (gridDim - 1) - 0.5;
        const normY = -heights[idx] * (elev / scale); // negative Y is up

        // 3D Rotation (yaw around Y, pitch around X)
        // 1. Rotate around Y
        const x1 = normX * cosY + normZ * sinY;
        const z1 = -normX * sinY + normZ * cosY;
        const y1 = normY;

        // 2. Rotate around X
        const y2 = y1 * cosX - z1 * sinX;
        const z2 = y1 * sinX + z1 * cosX;
        const x2 = x1;

        // 3. Perspective Projection
        const fov = 2.4;
        const depth = z2 + fov;
        const invDepth = 1.0 / (depth > 0.1 ? depth : 0.1);

        projX[idx] = cx + x2 * scale * invDepth;
        projY[idx] = cy + y2 * scale * invDepth;
        projZ[idx] = z2;
      }
    }

    // Color interpolation function
    const getThermalColor = (h: number, alpha: number) => {
      if (h < 0.25) {
        // Dark Navy -> Cyan
        const t = h / 0.25;
        const r = Math.round(15 + t * 6);
        const g = Math.round(23 + t * 160);
        const b = Math.round(42 + t * 180);
        return `rgba(${r},${g},${b},${alpha})`;
      } else if (h < 0.60) {
        // Cyan -> Green/Amber
        const t = (h - 0.25) / 0.35;
        const r = Math.round(21 + t * 224);
        const g = Math.round(183 + t * 30);
        const b = Math.round(222 - t * 180);
        return `rgba(${r},${g},${b},${alpha})`;
      } else {
        // Amber -> Radiant Red/Magenta (Tampering Peak)
        const t = (h - 0.60) / 0.40;
        const r = Math.round(245 + t * 10);
        const g = Math.round(158 - t * 110);
        const b = Math.round(11 + t * 90);
        return `rgba(${r},${g},${b},${alpha})`;
      }
    };

    // Draw Mesh Quads sorted back-to-front (Painter's Algorithm)
    type Quad = { i0: number; i1: number; i2: number; i3: number; depth: number; avgH: number };
    const quads: Quad[] = [];

    for (let gy = 0; gy < gridDim - 1; gy++) {
      for (let gx = 0; gx < gridDim - 1; gx++) {
        const i0 = gy * gridDim + gx;
        const i1 = gy * gridDim + (gx + 1);
        const i2 = (gy + 1) * gridDim + (gx + 1);
        const i3 = (gy + 1) * gridDim + gx;

        const depth = (projZ[i0] + projZ[i1] + projZ[i2] + projZ[i3]) * 0.25;
        const avgH = (heights[i0] + heights[i1] + heights[i2] + heights[i3]) * 0.25;
        quads.push({ i0, i1, i2, i3, depth, avgH });
      }
    }

    // Sort descending by depth (draw furthest first)
    quads.sort((a, b) => b.depth - a.depth);

    // Draw quads
    for (const q of quads) {
      ctx.beginPath();
      ctx.moveTo(projX[q.i0], projY[q.i0]);
      ctx.lineTo(projX[q.i1], projY[q.i1]);
      ctx.lineTo(projX[q.i2], projY[q.i2]);
      ctx.lineTo(projX[q.i3], projY[q.i3]);
      ctx.closePath();

      if (renderStyle === 'shaded' || renderStyle === 'hybrid') {
        ctx.fillStyle = getThermalColor(q.avgH, renderStyle === 'hybrid' ? 0.72 : 0.95);
        ctx.fill();
      }

      if (renderStyle === 'wireframe' || renderStyle === 'hybrid') {
        ctx.strokeStyle = q.avgH > 0.6 ? '#f43f5e' : q.avgH > 0.3 ? '#06b6d4' : '#334155';
        ctx.lineWidth = q.avgH > 0.6 ? 1.0 : 0.5;
        ctx.stroke();
      }
    }

    // Draw Base Reference Wireframe Grid (Bounding Floor Box)
    const floorCorners = [
      0,
      gridDim - 1,
      gridDim * gridDim - 1,
      gridDim * (gridDim - 1),
    ];
    ctx.beginPath();
    ctx.moveTo(projX[floorCorners[0]], projY[floorCorners[0]]);
    ctx.lineTo(projX[floorCorners[1]], projY[floorCorners[1]]);
    ctx.lineTo(projX[floorCorners[2]], projY[floorCorners[2]]);
    ctx.lineTo(projX[floorCorners[3]], projY[floorCorners[3]]);
    ctx.closePath();
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.4)';
    ctx.lineWidth = 1.2;
    ctx.stroke();
  }, [rotX, rotY, zoom, elevationScale, renderStyle]);

  // Animation Loop for Auto-Rotation
  useEffect(() => {
    let animId: number;
    const loop = () => {
      if (autoRotate && !isDraggingRef.current) {
        setRotY((prev) => (prev + 0.35) % 360);
      }
      render3D();
      animId = requestAnimationFrame(loop);
    };
    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, [autoRotate, render3D]);

  // Mouse Interaction Handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    isDraggingRef.current = true;
    lastMousePosRef.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    const dx = e.clientX - lastMousePosRef.current.x;
    const dy = e.clientY - lastMousePosRef.current.y;
    lastMousePosRef.current = { x: e.clientX, y: e.clientY };

    setRotY((y) => (y + dx * 0.6) % 360);
    setRotX((x) => Math.max(-10, Math.min(80, x - dy * 0.5)));
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    setZoom((z) => Math.max(0.6, Math.min(2.5, Number((z + delta).toFixed(2)))));
  };

  return (
    <div className="relative flex flex-col items-center justify-center w-full bg-slate-950 rounded-xl overflow-hidden select-none">
      {/* 3D Viewport Controls & Telemetry HUD */}
      <div className="absolute top-3 left-3 right-3 z-20 flex flex-wrap items-center justify-between gap-2 pointer-events-auto">
        {/* Left Telemetry HUD */}
        <div className="bg-slate-950/85 backdrop-blur-xs border border-slate-800 px-3 py-1.5 rounded-xl font-mono text-[11px] flex items-center gap-3 text-slate-300 shadow-md">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
            <span className="text-slate-400">PEAK ANOMALY:</span>
            <span className="text-rose-400 font-bold">{peakStats.maxVal}%</span>
          </span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-400">
            LOCATION: <span className="text-cyan-300 font-semibold">[X: {peakStats.peakX}, Y: {peakStats.peakY}]</span>
          </span>
        </div>

        {/* Right 3D Tactical Mode Controls */}
        <div className="bg-slate-950/85 backdrop-blur-xs border border-slate-800 p-1 rounded-xl flex items-center gap-1 shadow-md">
          <button
            type="button"
            onClick={() => setAutoRotate(!autoRotate)}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-mono transition-colors ${
              autoRotate
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {autoRotate ? '⏸ PAUSE ORBIT' : '▶ AUTO ORBIT'}
          </button>

          <button
            type="button"
            onClick={() => {
              setRotX(38);
              setRotY(-42);
              setZoom(1.15);
              setElevationScale(1.8);
            }}
            className="px-2 py-1 rounded-lg text-[11px] font-mono text-slate-400 hover:text-white transition-colors"
            title="Reset 3D Camera"
          >
            RESET
          </button>

          <div className="h-3 w-px bg-slate-800" />

          {/* Shading Style Switcher */}
          <button
            type="button"
            onClick={() => setRenderStyle('hybrid')}
            className={`px-2 py-1 rounded-lg text-[10px] font-mono transition-colors ${
              renderStyle === 'hybrid' ? 'bg-slate-800 text-cyan-300 font-bold' : 'text-slate-400'
            }`}
          >
            HYBRID
          </button>
          <button
            type="button"
            onClick={() => setRenderStyle('shaded')}
            className={`px-2 py-1 rounded-lg text-[10px] font-mono transition-colors ${
              renderStyle === 'shaded' ? 'bg-slate-800 text-cyan-300 font-bold' : 'text-slate-400'
            }`}
          >
            SOLID
          </button>
          <button
            type="button"
            onClick={() => setRenderStyle('wireframe')}
            className={`px-2 py-1 rounded-lg text-[10px] font-mono transition-colors ${
              renderStyle === 'wireframe' ? 'bg-slate-800 text-cyan-300 font-bold' : 'text-slate-400'
            }`}
          >
            MESH
          </button>
        </div>
      </div>

      {/* Main 3D Canvas */}
      <canvas
        ref={canvasRef}
        width={780}
        height={480}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className="w-full max-h-[58vh] h-[440px] cursor-grab active:cursor-grabbing block"
      />

      {/* Bottom Floating Altitude Slider & Legend */}
      <div className="absolute bottom-3 left-4 right-4 z-20 flex flex-wrap items-center justify-between gap-3 pointer-events-auto bg-slate-950/85 backdrop-blur-xs border border-slate-800/80 px-4 py-2 rounded-xl text-xs font-mono text-slate-400">
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-400">ELEVATION SCALE:</span>
          <input
            type="range"
            min="0.5"
            max="3.5"
            step="0.1"
            value={elevationScale}
            onChange={(e) => setElevationScale(Number(e.target.value))}
            className="h-1.5 w-24 sm:w-32 cursor-pointer rounded-lg bg-slate-800 accent-cyan-400"
          />
          <span className="text-cyan-300 font-bold">{elevationScale.toFixed(1)}×</span>
        </div>

        {/* Thermal Elevation Color Gradient Legend */}
        <div className="flex items-center gap-2 text-[10px]">
          <span>BASELINE (FLAT)</span>
          <div className="h-2 w-24 rounded-full bg-gradient-to-r from-slate-900 via-cyan-500 via-emerald-400 to-rose-500 border border-slate-700" />
          <span className="text-rose-400 font-bold">PEAK TAMPER</span>
        </div>
      </div>
    </div>
  );
};

export default Forensic3DSurfaceViewer;
