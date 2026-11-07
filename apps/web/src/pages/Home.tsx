import { Link } from 'react-router-dom';
import ForensicsDashboard from '../components/ForensicsDashboard';

export default function Home() {
  return (
    <div className="mx-auto max-w-7xl px-3 sm:px-6 py-4 sm:py-8 space-y-8 sm:space-y-12">
      {/* Hero Section - Tactical Cyber Forensics Command */}
      <section className="text-center max-w-4xl mx-auto pt-2 sm:pt-4">
        {/* Capability Pill */}
        <div className="inline-flex items-center gap-2 rounded-full bg-slate-900/90 border border-cyan-500/40 px-3.5 py-1 text-xs font-mono font-semibold text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)] mb-3">
          <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_8px_#22d3ee]" />
          <span>CYBER FORENSIC WORKSTATION // MULTI-MODAL SENSOR FUSION</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-black text-slate-100 tracking-tight leading-tight">
          Optical Sensor Integrity &amp;{' '}
          <span className="bg-gradient-to-r from-cyan-400 via-sky-400 to-indigo-400 bg-clip-text text-transparent drop-shadow-[0_0_25px_rgba(6,182,212,0.3)]">
            AI Tampering Detection
          </span>
        </h1>

        <p className="mt-3 text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed font-sans">
          Physical camera sensor fingerprinting, Bayer CFA demosaicing periodicity, Fourier spectral anomalies, facial micro-skin textures, and localized inpainting verification.
        </p>

        {/* Feature Badges Row */}
        <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-[11px] font-mono text-slate-300">
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            📷 Sensor Noise (PRNU)
          </span>
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            🧬 Bayer CFA Demosaicing
          </span>
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            👤 Facial Micro-Texture
          </span>
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            ✨ Fourier Nyquist (2D FFT)
          </span>
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            🔍 JPEG DCT &amp; ELA
          </span>
          <span className="rounded-lg bg-slate-900/80 border border-slate-800 px-2.5 py-1 font-medium shadow-sm hover:border-cyan-500/40 transition-colors">
            🛡️ C2PA Manifest
          </span>
        </div>
      </section>

      {/* Main Interactive Live Forensics Engine */}
      <section>
        <ForensicsDashboard />
      </section>

      {/* Dedicated Forensic Workspaces */}
      <section className="pt-8 border-t border-slate-800/80">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-100 font-mono tracking-wide">
              FORENSIC OPERATIONS &amp; INVESTIGATION SUITE
            </h2>
            <p className="text-xs text-slate-400 font-mono">
              Immutable SHA-256 audit ledger, homography dual-image registration, and tamper logs.
            </p>
          </div>
          <span className="text-xs font-mono font-semibold text-cyan-400 bg-cyan-950/60 border border-cyan-500/40 px-2.5 py-1 rounded-full shadow-[0_0_10px_rgba(6,182,212,0.15)]">
            ACTIVE TERMINAL
          </span>
        </div>

        <div className="grid gap-4 sm:gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <Link
            to="/protect"
            className="group rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl transition-all hover:border-cyan-500/50 hover:bg-slate-900/90 hover:shadow-[0_0_20px_rgba(6,182,212,0.15)] hover:-translate-y-0.5 flex flex-col justify-between"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-950/60 border border-cyan-500/40 text-cyan-400 mb-3 group-hover:scale-105 transition-transform shadow-[0_0_10px_rgba(6,182,212,0.2)]">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-100 group-hover:text-cyan-300 transition-colors font-mono">
                PROTECT &amp; REGISTER VAULT
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-400 leading-relaxed font-sans">
                Register raw camera captures directly into the zero-retention vault with cryptographic SHA-256 signatures before distribution.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-mono font-semibold text-cyan-400 gap-1">
              <span>INITIALIZE REGISTRATION</span>
              <svg className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          <Link
            to="/investigation"
            className="group rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl transition-all hover:border-indigo-500/50 hover:bg-slate-900/90 hover:shadow-[0_0_20px_rgba(99,102,241,0.15)] hover:-translate-y-0.5 flex flex-col justify-between"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-950/60 border border-indigo-500/40 text-indigo-400 mb-3 group-hover:scale-105 transition-transform shadow-[0_0_10px_rgba(99,102,241,0.2)]">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-100 group-hover:text-indigo-300 transition-colors font-mono">
                REFERENCE INVESTIGATION
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-400 leading-relaxed font-sans">
                Perform dual-image homography registration, sub-pixel difference maps, crop boundary analysis, and platform compression simulations.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-mono font-semibold text-indigo-400 gap-1">
              <span>OPEN COMPARISON SUITE</span>
              <svg className="h-3.5 w-3.5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          <Link
            to="/vault"
            className="group rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl transition-all hover:border-emerald-500/50 hover:bg-slate-900/90 hover:shadow-[0_0_20px_rgba(16,185,129,0.15)] hover:-translate-y-0.5 flex flex-col justify-between sm:col-span-2 lg:col-span-1"
          >
            <div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 mb-3 group-hover:scale-105 transition-transform shadow-[0_0_10px_rgba(16,185,129,0.2)]">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                </svg>
              </div>
              <h3 className="text-base font-bold text-slate-100 group-hover:text-emerald-300 transition-colors font-mono">
                SEALED FORENSIC RECORDS
              </h3>
              <p className="mt-1.5 text-xs sm:text-sm text-slate-400 leading-relaxed font-sans">
                Audit cryptographically sealed original records with immutable timestamp chains, camera EXIF hashes, and tamper logs.
              </p>
            </div>
            <div className="mt-4 flex items-center text-xs font-mono font-semibold text-emerald-400 gap-1">
              <span>ACCESS IMMUTABLE VAULT</span>
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
