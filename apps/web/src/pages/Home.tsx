import { Link } from 'react-router-dom';
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

      {/* Dedicated Forensic Workspaces */}
      <section className="pt-8 border-t border-slate-200/80">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Dedicated Forensic Workspaces</h2>
            <p className="text-xs text-slate-500">Full audit trail, registered reference images, and cryptographic sealing.</p>
          </div>
          <span className="text-xs font-semibold text-brand-600 bg-brand-50 border border-brand-200 px-2.5 py-1 rounded-full">
            Enterprise Module
          </span>
        </div>

        <div className="grid gap-4 sm:gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <Link
            to="/protect"
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:shadow-md hover:border-brand-400 hover:-translate-y-0.5 flex flex-col justify-between"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600 mb-3 group-hover:bg-brand-600 group-hover:text-white transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-brand-600 transition-colors">
                Protect &amp; Register Vault
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-600 leading-relaxed">
                Register original raw photos directly into the tamper-proof vault with cryptographic SHA-256 signatures before distribution.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-semibold text-brand-600 gap-1">
              <span>Register new image</span>
              <svg className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          <Link
            to="/investigation"
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:shadow-md hover:border-indigo-400 hover:-translate-y-0.5 flex flex-col justify-between"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 mb-3 group-hover:bg-indigo-600 group-hover:text-white transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">
                Reference Investigation
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-600 leading-relaxed">
                Perform dual-image homography registration, exact pixel difference maps, crop boundary analysis, and platform travel simulations.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-semibold text-indigo-600 gap-1">
              <span>Open investigation workspace</span>
              <svg className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          <Link
            to="/vault"
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:shadow-md hover:border-cyan-400 hover:-translate-y-0.5 flex flex-col justify-between sm:col-span-2 lg:col-span-1"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-50 text-cyan-600 mb-3 group-hover:bg-cyan-600 group-hover:text-white transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-900 group-hover:text-cyan-600 transition-colors">
                Vault &amp; Sealed Records
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-600 leading-relaxed">
                Audit cryptographically sealed original records with immutable timestamp chains, camera EXIF hashes, and tamper logs.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-semibold text-cyan-600 gap-1">
              <span>View sealed records</span>
              <svg className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>
        </div>
      </section>
    </div>
  );
}
