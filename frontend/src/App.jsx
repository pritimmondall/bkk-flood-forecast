import { useState, useMemo } from "react";
import { LandingPage } from "./components/landing/LandingPage";
import { DashboardStateProvider } from "./context/DashboardStateContext";
import { DashboardHeader } from "./components/layout/DashboardHeader";
import { DashboardLayout } from "./components/layout/DashboardLayout";
import { useForecast } from "./hooks/useForecast";

function DashboardScreen() {
  const { forecastModelParameters } = useForecast();
  const [isDemoMode, setIsDemoMode] = useState(true);

  const riskParam = forecastModelParameters.find((p) => p.id === "ml-risk-score");
  const riskScore = riskParam ? parseFloat(riskParam.value) : 0;
  
  const bgThemeClass = useMemo(() => {
    if (riskScore >= 60) return 'bg-red-950';
    if (riskScore >= 50) return 'bg-orange-950';
    return 'bg-slate-900';
  }, [riskScore]);

  return (
    <div className={`flex flex-col transition-colors duration-1000 ${bgThemeClass} text-slate-100 md:h-screen md:overflow-hidden`}>
      <DashboardHeader isDemoMode={isDemoMode} setIsDemoMode={setIsDemoMode} />
      <DashboardLayout isDemoMode={isDemoMode} />
    </div>
  );
}

function App() {
  const [currentPage, setCurrentPage] = useState("landing");
  if (currentPage === "landing") {
    return <LandingPage onLogin={() => setCurrentPage("dashboard")} />;
  }
  return (
    <DashboardStateProvider>
      <DashboardScreen />
    </DashboardStateProvider>
  );
}

export default App;
