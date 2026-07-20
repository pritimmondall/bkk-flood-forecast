import { useState, useEffect } from "react";
import { Shield, Radio, LayoutDashboard, Bell, Package, FileText, Clock } from "lucide-react";
import { useDashboardState } from "../../context/DashboardStateContext";
import { API_URL, DEMO_TIMESTAMP } from "../../lib/floodApi";

const NAV_TABS = [{ id: "dashboard", label: "Dashboard", Icon: LayoutDashboard }, { id: "alerts", label: "Alerts", Icon: Bell }, { id: "resources", label: "Resources", Icon: Package }, { id: "reports", label: "Reports", Icon: FileText }];

export function DashboardHeader({ isDemoMode, setIsDemoMode }) {
  const { activeNavTab, setActiveNavTab } = useDashboardState();
  const [currentTime, setCurrentTime] = useState(() => new Date());

  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const formattedTime = currentTime.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Bangkok" });
  const formattedDate = currentTime.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "Asia/Bangkok" });

  return (
    <div className="relative z-50 w-full px-4 pt-4 pb-2">
      <header className="flex h-14 w-full items-center justify-between gap-2 xl:gap-4 rounded-2xl border border-white/10 bg-slate-900/60 backdrop-blur-md px-3 xl:px-4 shadow-2xl shadow-black/40 overflow-x-auto [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        <div className="flex min-w-0 flex-shrink-0 items-center gap-2 xl:gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-blue-500/30 bg-blue-600/20">
            <Shield className="h-4 w-4 text-blue-400" />
          </div>
          <div className="hidden min-w-0 md:block">
            <div className="text-sm leading-tight font-bold whitespace-nowrap text-slate-100">BANGKOK FLOOD COMMAND</div>
            <div className="text-xs leading-tight whitespace-nowrap text-slate-500">AI Urban Flood Forecasting System v3.1</div>
          </div>
          
          <div className={`flex items-center gap-1.5 rounded-full border px-2 py-1 ${isDemoMode ? 'border-orange-500/30 bg-orange-500/10' : 'border-green-500/30 bg-green-500/10'}`}>
            <span className="relative flex h-2 w-2">
              <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${isDemoMode ? 'bg-orange-400' : 'bg-green-400'}`}></span>
              <span className={`relative inline-flex h-2 w-2 rounded-full ${isDemoMode ? 'bg-orange-500' : 'bg-green-500'}`}></span>
            </span>
            <Radio className={`h-3 w-3 ${isDemoMode ? 'text-orange-400' : 'text-green-400'}`} />
            <span className={`hidden text-xs font-medium sm:inline ${isDemoMode ? 'text-orange-400' : 'text-green-400'}`}>{isDemoMode ? 'DEMO' : 'LIVE'}</span>
          </div>

          <div className="ml-2 xl:ml-4 flex items-center gap-2 border-l border-white/10 pl-2 xl:pl-4">
            <span className={`text-xs font-semibold ${isDemoMode ? 'text-slate-500' : 'text-green-400'}`}>Live Wx</span>
            <button
              onClick={() => setIsDemoMode(!isDemoMode)}
              className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors duration-300 focus:outline-none ${isDemoMode ? 'bg-orange-500/50' : 'bg-green-500/50'}`}>
              <span className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform duration-300 ${isDemoMode ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
            <span className={`text-xs font-semibold ${isDemoMode ? 'text-orange-400' : 'text-slate-500'}`}>Sim Demo</span>
            <button
              onClick={() => {
                // CAP is currently generated for replay timestamps only.
                window.open(`${API_URL}/cap?ts=${encodeURIComponent(DEMO_TIMESTAMP)}&station=FL.RTW.08`, '_blank');
              }}
              className="ml-2 xl:ml-3 flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-600/20 px-2 xl:px-3 py-1.5 text-xs font-medium text-purple-400 transition-all duration-300 hover:bg-purple-500/30 hover:shadow-[0_0_15px_rgba(168,85,247,0.4)] hover:text-purple-300 whitespace-nowrap"
            >
              <span>📡</span> <span className="hidden xl:inline">Broadcast </span>CAP Alert
            </button>
          </div>
        </div>

        <nav className="flex items-center gap-1" role="tablist">
          {NAV_TABS.map(({ id, label, Icon }) => {
            const isActive = activeNavTab === id;
            return (
              <button key={id} onClick={() => setActiveNavTab(id)} className={`flex items-center gap-1.5 rounded-lg px-2 xl:px-3 py-1.5 text-xs font-medium whitespace-nowrap transition-all duration-150 ${isActive ? 'border border-blue-500/40 bg-blue-600/20 text-blue-400' : 'border border-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200'}`}>
                <Icon className="h-3.5 w-3.5" /><span className="hidden md:inline">{label}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex flex-shrink-0 items-center gap-2 xl:gap-3">
          
          {/* THE FIX: Loading directly from the local public folder to bypass external server blocks */}
          <div className="flex items-center gap-2 xl:gap-3 mr-2 xl:mr-4">
            <img 
              src="/tsri-logo.jpeg" 
              alt="TSRI Logo" 
              className="h-7 xl:h-10 object-contain bg-white px-1.5 py-1 rounded-sm" 
            />
            <img 
              src="/kmitl-logo.jpeg" 
              alt="KMITL Engineering" 
              className="h-7 xl:h-10 object-contain bg-white px-1.5 py-1 rounded-sm" 
            />
          </div>

          <div className="hidden flex-col items-end lg:flex">
            <div className="flex items-center gap-1.5 font-mono text-xs text-slate-100"><Clock className="h-3.5 w-3.5 text-slate-500" /><span>{formattedTime} ICT</span></div>
            <span className="text-xs text-slate-500">{formattedDate}</span>
          </div>
        </div>
      </header>
    </div>
  );
}
