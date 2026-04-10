import React, { useState, useEffect } from 'react';
import { Shield, Terminal, Activity, AlertTriangle, Cpu, Network } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const App = () => {
  const [status, setStatus] = useState("LOADING...");
  const [integrityLevel, setIntegrityLevel] = useState(100);
  const [logs, setLogs] = useState([
    { id: 1, type: 'init', msg: 'S.O.H.-X KERNEL_LOADED' },
    { id: 2, type: 'prot', msg: 'PROTOCOL Ω-9 ACTIVE' }
  ]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setStatus("S.O.H.-X ONLINE [Ω-9 ACTIVE]");
    }, 1500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="min-h-screen bg-black text-green-500 font-mono p-6 selection:bg-green-900 selection:text-white">
      {/* HUD Header */}
      <header className="border-b-2 border-green-900 pb-4 mb-8 flex justify-between items-end backdrop-blur-md sticky top-0 bg-black/80 z-50">
        <div className="flex items-center gap-4">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          >
            <Shield className="text-red-600 w-10 h-10" />
          </motion.div>
          <div>
            <h1 className="text-3xl font-black tracking-widest uppercase">S.O.H.-X CORETEX</h1>
            <div className="flex gap-2 text-[10px] text-green-700">
              <span className="animate-pulse">● DEPLOYED</span>
              <span>● KERNEL_ID: BLINDADO_ST-H</span>
            </div>
          </div>
        </div>
        
        <div className="text-right flex flex-col gap-1">
          <div className="flex items-center justify-end gap-2 text-xs">
            <Network size={12} className="text-cyan-500" />
            <span className="text-cyan-400">STATUS: {status}</span>
          </div>
          <div className="flex items-center justify-end gap-2 text-xs">
            <Cpu size={12} className="text-yellow-500" />
            <span className="text-yellow-400">RESILIENCE: {integrityLevel}%</span>
          </div>
        </div>
      </header>

      {/* Main Tactical Grid */}
      <main className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        
        {/* Intelligence Feed (Terminal) */}
        <section className="lg:col-span-3 space-y-4">
          <div className="bg-gray-950 border border-green-900 rounded-lg p-5 shadow-[0_0_15px_rgba(0,50,0,0.3)]">
            <div className="flex items-center justify-between mb-4 border-b border-green-900/50 pb-2">
              <div className="flex items-center gap-2">
                <Terminal size={18} />
                <span className="text-sm font-bold">TERMINAL Ω-9 OPERATIONAL FEED</span>
              </div>
              <Activity size={16} className="text-red-500 animate-pulse" />
            </div>
            
            <div className="h-[400px] overflow-y-auto space-y-2 text-xs">
              <AnimatePresence>
                {logs.map((log) => (
                  <motion.div 
                    key={log.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex gap-2"
                  >
                    <span className="text-green-800">[{new Date().toLocaleTimeString()}]</span>
                    <span className={log.type === 'alert' ? 'text-red-500' : 'text-green-400'}>
                      {log.msg}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
              <div className="text-gray-600 animate-pulse">_ CURSOR_BLINK...</div>
            </div>
          </div>
        </section>

        {/* Sidebar Controls & Meters */}
        <aside className="space-y-6">
          {/* Defensive Modules */}
          <div className="bg-gray-900/40 border-l-4 border-red-600 p-4 rounded shadow-lg">
            <h2 className="text-sm font-bold mb-3 flex items-center gap-2">
              <Shield size={16} className="text-red-500" /> DEFENSIVE_UNITS
            </h2>
            <div className="space-y-3 text-[11px]">
              <div className="flex justify-between items-center bg-black/40 p-2 rounded">
                <span>Allen-Bradley Shield</span>
                <span className="bg-green-900 text-green-300 px-2 py-0.5 rounded text-[9px]">NOMINAL</span>
              </div>
              <div className="flex justify-between items-center bg-black/40 p-2 rounded">
                <span>Ghost AIS Detect</span>
                <span className="bg-cyan-900 text-cyan-300 px-2 py-0.5 rounded text-[9px]">ACTIVE</span>
              </div>
              <div className="flex justify-between items-center bg-black/40 p-2 rounded">
                <span>SCADA_TOKEN_FIREWALL</span>
                <span className="bg-blue-900 text-blue-300 px-2 py-0.5 rounded text-[9px]">LOCKED</span>
              </div>
            </div>
          </div>

          {/* Integrity Lock Warning */}
          <div className="bg-yellow-950/20 border border-yellow-900/50 p-4 rounded text-xs space-y-2">
            <div className="flex items-center gap-2 text-yellow-500 font-bold">
              <AlertTriangle size={16} />
              <span>PROTOCOLO Ω-9: INTEGRITY LOCK</span>
            </div>
            <p className="text-yellow-700 leading-relaxed italic">
              Operações ofensivas contra ativos civis (hospitais, saneamento, energia residencial) estão 
              <b> fisicamente impossibilitadas</b> via Kernel Blindado.
            </p>
          </div>

          {/* Infrastructure Metrics */}
          <div className="bg-black border border-green-900/30 p-4 rounded">
            <div className="text-[10px] text-green-800 mb-2 uppercase tracking-widest">Global Resilience</div>
            <div className="w-full bg-green-900/20 h-1 rounded-full mb-4">
              <motion.div 
                className="bg-green-500 h-full rounded-full shadow-[0_0_8px_#22c55e]"
                initial={{ width: 0 }}
                animate={{ width: "98%" }}
                transition={{ duration: 2 }}
              />
            </div>
            <div className="flex justify-between text-[9px]">
              <span>UPTIME: 99.999%</span>
              <span>THREATS_MITIGATED: 0</span>
            </div>
          </div>
        </aside>

      </main>

      {/* Footer Branding */}
      <footer className="mt-8 pt-4 border-t border-green-900/30 text-[9px] text-green-900 text-center tracking-[0.3em] uppercase">
        S.O.H.-X AI CORE - Strait of Hormuz Defensive System - Protocolo Ω-9
      </footer>
    </div>
  );
};

export default App;
