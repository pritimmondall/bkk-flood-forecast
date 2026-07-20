import { useState, useEffect } from 'react';
import { useDashboardState } from '../../context/DashboardStateContext';
import { SituationSummaryMetricsGrid } from '../sidebar-left/SituationSummaryMetricsGrid';
import { ForecastModelParametersList } from '../sidebar-left/ForecastModelParametersList';
import { FloodMapWrapper } from '../map-center/FloodMapWrapper';
import { WaterLevelLineChart } from '../sidebar-right/WaterLevelLineChart';
import { ForecastRiskAreaChart } from '../sidebar-right/ForecastRiskAreaChart';
import { HotspotLocationCardList } from '../sidebar-right/HotspotLocationCardList';
import { RiskTimelineBarChart } from '../sidebar-right/RiskTimelineBarChart';
import { AlertsTabPanel } from './tab-panels/AlertsTabPanel';
import { ResourcesTabPanel } from './tab-panels/ResourcesTabPanel';
import { ReportsTabPanel } from './tab-panels/ReportsTabPanel';
import { getForecastGeoJson } from '../../lib/floodApi';

export function DashboardLayout({ isDemoMode }) {
  const { activeNavTab } = useDashboardState();
  const [liveFloodData, setLiveFloodData] = useState(null);
  const [forecastError, setForecastError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const fetchForecast = async () => {
      try {
        setForecastError(null);
        setLiveFloodData(await getForecastGeoJson({ demo: isDemoMode, signal: controller.signal }));
      } catch (err) {
        if (err.name !== 'AbortError') {
          console.error('Forecast fetch error:', err);
          setForecastError(err.message);
        }
      }
    };
    fetchForecast();
    // Live weather is cached by the API for about ten minutes; polling faster
    // only repeats costly model work. Replay refreshes more often for demos.
    const intervalId = window.setInterval(fetchForecast, isDemoMode ? 60_000 : 10 * 60_000);
    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [isDemoMode]);

  if (activeNavTab === 'alerts') return <AlertsTabPanel liveFloodData={liveFloodData} />;
  if (activeNavTab === 'resources') return <ResourcesTabPanel liveFloodData={liveFloodData} />;
  if (activeNavTab === 'reports') return <ReportsTabPanel liveFloodData={liveFloodData} />;

  return (
    <div className='gap-3 p-3 md:grid md:min-h-0 md:grid-cols-12 md:overflow-hidden'>
      <aside className='col-span-3 flex min-h-0 flex-col gap-3 overflow-y-auto pr-1'>
        <SituationSummaryMetricsGrid liveFloodData={liveFloodData} isDemoMode={isDemoMode} />
        <ForecastModelParametersList liveFloodData={liveFloodData} isDemoMode={isDemoMode} />
      </aside>
      
      <main className='col-span-6 flex min-h-0 flex-col gap-3 overflow-hidden'>
        <FloodMapWrapper liveFloodData={liveFloodData} />
        {forecastError && <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">Forecast API unavailable: {forecastError}</p>}
        <WaterLevelLineChart liveFloodData={liveFloodData} />
      </main>
      
      <aside className='col-span-3 flex min-h-0 flex-col gap-3 overflow-y-auto pr-1'>
        <ForecastRiskAreaChart liveFloodData={liveFloodData} />
        <HotspotLocationCardList liveFloodData={liveFloodData} />
        <RiskTimelineBarChart liveFloodData={liveFloodData} />
      </aside>
    </div>
  );
}
