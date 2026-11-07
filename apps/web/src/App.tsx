import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Home from './pages/Home';
import Protect from './pages/Protect';
import Vault from './pages/Vault';
import Investigation from './pages/Investigation';
import History from './pages/History';

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900 antialiased selection:bg-brand-500 selection:text-white">
      {/* Top and Mobile Bottom Navbar */}
      <Navbar />

      {/* Main Content Area - extra bottom padding on mobile for sticky bottom bar */}
      <main className="flex-1 pb-20 md:pb-10">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/protect" element={<Protect />} />
          <Route path="/vault" element={<Vault />} />
          <Route path="/investigation" element={<Investigation />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white py-6 text-xs text-slate-500 hidden md:block">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6">
          <div className="flex items-center gap-2">
            <span className="font-bold text-slate-800">PINITHUB Forensics</span>
            <span>—</span>
            <span>Multi-Source AI &amp; Optical Sensor Integrity Verification</span>
          </div>
          <div className="flex items-center gap-4 text-slate-400">
            <span>UNet • EfficientNet • DCT 2D-FFT • PRNU • ELA • SIFT</span>
            <span>•</span>
            <span>Zero-Retention In-Memory Processing</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
