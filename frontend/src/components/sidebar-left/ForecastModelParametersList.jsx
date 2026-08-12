import { useState, useMemo } from 'react';
import { Cpu, CheckCircle, XCircle } from 'lucide-react';
import { useForecast } from '../../hooks/useForecast';
import { SectionHeader } from '../shared/SectionHeader';

export function ForecastModelParametersList({ liveFloodData, isDemoMode }) {
  const [isExpanded, setIsExpanded] = useState(true);
  const { forecastModelParameters } = useForecast();

  const averageProbability = useMemo(() => {
    const dataArray = Array.isArray(liveFloodData) ? liveFloodData : (liveFloodData?.predictions || []);
    const avgRisk = dataArray.length > 0 ? (dataArray.reduce((sum, d) => sum + (d.probability || 0), 0) / dataArray.length) * 100 : 0;
    return avgRisk.toFixed(2);
  }, [liveFloodData]);

  const currentTemp = (liveFloodData && liveFloodData.length > 0 && liveFloodData[0].temperature) 
      ? Math.round(liveFloodData[0].temperature) 
      : '--';
  const upstreamFlow = isDemoMode ? '2,450' : '960';

  // Merge realistic data
  const updatedParameters = useMemo(() => {
    let params = forecastModelParameters.filter(p => p.id !== 'ml-risk-score' && p.id !== 'live-temp');
    
    // Apply demo mode overwrites
    params = params.map(p => {
      let finalValue = p.value;
      let finalNormal = p.withinNormalRange;

      if (p.label === 'Rainfall Accumulation') {
        finalValue = isDemoMode ? '58' : '0';
        finalNormal = !isDemoMode;
      } else if (p.label === 'Soil Moisture Index') {
        finalValue = isDemoMode ? '0.87' : '0.45';
        finalNormal = !isDemoMode;
      } else if (p.label === 'Surface Runoff Coeff.') {
        finalValue = isDemoMode ? '0.72' : '0.30';
        finalNormal = !isDemoMode;
      } else if (p.label === 'Upstream River Flow') {
        finalValue = upstreamFlow;
        finalNormal = !isDemoMode;
      }

      return {
        ...p,
        value: finalValue,
        withinNormalRange: finalNormal
      };
    });

    params.unshift({
      id: 'ml-risk-score',
      label: 'Average Risk Score',
      value: averageProbability,
      unit: '%',
      withinNormalRange: averageProbability < 50
    });

    params.unshift({
      id: 'live-temp',
      label: 'Current Temperature',
      value: currentTemp,
      unit: '°C',
      withinNormalRange: true
    });

    return params;
  }, [forecastModelParameters, averageProbability, isDemoMode, currentTemp, upstreamFlow]);

  const outOfRangeCount = updatedParameters.filter((p) => !p.withinNormalRange).length;

  return (
    <section className='dashboard-card flex-shrink-0'>
      <SectionHeader
        title='Model Parameters'
        subtitle='AI hydrological inputs'
        icon={<Cpu className='h-4 w-4' />}
        isExpanded={isExpanded}
        onToggleExpand={() => setIsExpanded((prev) => !prev)}
        trailing={
          <span className='rounded-full border border-red-500/40 bg-red-500/20 px-1.5 py-0.5 text-xs text-red-400'>
            {outOfRangeCount} abnormal
          </span>
        }
      />
      <div
        className={`overflow-hidden transition-all duration-300 ${isExpanded ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}`}
        aria-hidden={!isExpanded}
      >
        <div className='mt-1 space-y-1.5'>
          {updatedParameters.map((param) => (
            <div
              key={param.id}
              className='flex items-center justify-between border-b border-slate-700/40 py-1.5 last:border-0'
            >
              <div className='flex min-w-0 items-center gap-2'>
                {param.withinNormalRange ? (
                  <CheckCircle className='h-3.5 w-3.5 flex-shrink-0 text-green-400' />
                ) : (
                  <XCircle className='h-3.5 w-3.5 flex-shrink-0 text-red-400' />
                )}
                <span className='truncate text-xs text-slate-400'>{param.label}</span>
              </div>
              <span
                className={`ml-2 font-mono text-xs font-semibold whitespace-nowrap ${param.withinNormalRange ? 'text-green-400' : 'text-red-400'}`}
              >
                {param.value}
                {param.unit ? ` ${param.unit}` : ''}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
