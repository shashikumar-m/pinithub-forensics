import ForensicsDashboard from '../components/ForensicsDashboard';

export default function Home() {
  return (
    <div className="mx-auto max-w-7xl px-3 sm:px-6 py-4 sm:py-8 space-y-8 sm:space-y-12">
      {/* Hero Section */}
      <section className="text-center max-w-4xl mx-auto pt-2 sm:pt-4">
        {/* Capability Pill */}
        <div className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-brand-50 to-indigo-50 border border-brand-200/80 px-3.5 py-1 text-xs font-semibold text-brand-700 shadow-sm mb-3">
          <span className="flex h-2 w-2 rounded-full bg-brand-500 animate-pulse" />
          <span>Multi-Engine Generative &amp; Optical Camera Analysis</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-black text-slate-900 tracking-tight leading-tight">
          Image Authenticity &amp;{' '}
          <span className="bg-gradient-to-r from-brand-600 via-indigo-600 to-cyan-500 bg-clip-text text-transparent">
            AI Tampering Detection
          </span>
        </h1>

        <p className="mt-3 text-sm sm:text-lg text-slate-600 max-w-2xl mx-auto leading-relaxed">
          Instantly verify whether an image is a genuine camera capture, synthetic AI media (Canva, Gemini, ChatGPT/DALL-E, Midjourney), or locally tampered with inpainting or splicing.
        </p>

        {/* Feature Badges Row */}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-[11px] sm:text-xs text-slate-500">
          <span className="rounded-md bg-white border border-slate-200 px-2.5 py-1 font-medium shadow-2xs">
            📷 Physical Camera Sensor Noise (PRNU)
          </span>
          <span className="rounded-md bg-white border border-slate-200 px-2.5 py-1 font-medium shadow-2xs">
            ✨ Synthetic Frequency Artifacts (2D FFT)
          </span>
          <span className="rounded-md bg-white border border-slate-200 px-2.5 py-1 font-medium shadow-2xs">
            🔍 JPEG Error Level Analysis (ELA)
          </span>
          <span className="rounded-md bg-white border border-slate-200 px-2.5 py-1 font-medium shadow-2xs">
            🛡️ C2PA Manifest &amp; EXIF Provenance
          </span>
        </div>
      </section>

      {/* Main Interactive Live Forensics Engine */}
      <section>
        <ForensicsDashboard />
      </section>
    </div>
  );
}
