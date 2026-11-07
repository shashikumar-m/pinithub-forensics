import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import Protect from './pages/Protect';
import Vault from './pages/Vault';
import Investigation from './pages/Investigation';
import History from './pages/History';

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100 antialiased selection:bg-cyan-500 selection:text-slate-950 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]">
      {/* Top and Mobile Bottom Navbar */}
      <Navbar />

      {/* Main Content Area - extra bottom padding on mobile for sticky bottom bar */}
      <main className="flex-1 pb-20 md:pb-12">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/protect" element={<Protect />} />
          <Route path="/vault" element={<Vault />} />
          <Route path="/investigation" element={<Investigation />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>

      {/* Cyber-Forensic Operations Terminal Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950/90 py-5 text-xs text-slate-400 hidden md:block font-mono backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#22d3ee] animate-pulse" />
            <span className="font-bold text-slate-200 tracking-wider">PINITHUB FORENSIC WORKSTATION</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400 text-[11px]">CYBER-DEFENSE &amp; SENSOR PROVENANCE DIVISION</span>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-slate-400">
            <span className="text-cyan-400 font-semibold">PRNU • CFA • 2D-FFT • DCT • BIOMETRICS • C2PA</span>
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400">ZERO-RETENTION IN-MEMORY VAULT</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
