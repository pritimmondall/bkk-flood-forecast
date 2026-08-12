import { useMemo } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp } from "lucide-react";
import { DARK_TOOLTIP_STYLE, DARK_CURSOR_STYLE, AXIS_TICK_COLOR, AXIS_LINE_COLOR, CHART_COLORS, COMPACT_MARGIN, GRID_STROKE } from "../../lib/chart";
import { SectionHeader } from "../shared/SectionHeader";
import { forecastStations } from "../../lib/floodApi";

function RiskTooltip({ active, label, payload }) {
  if (!active || !payload?.length) return null;
  const risk = payload.find((p) => p.name === "Risk Score" || p.dataKey === "riskScore");
  return (
    <div style={DARK_TOOLTIP_STYLE} className="rounded-lg px-3 py-2 text-xs">
      <p className="mb-1 text-slate-400">{label}</p>
      {risk && (
        <span className="font-mono font-bold text-orange-400">
          {risk.value}% flood risk
        </span>
      )}
    </div>
  );
}

export function ForecastRiskAreaChart({ liveFloodData }) {
  const liveArea = useMemo(() => {
    const stations = forecastStations(liveFloodData);
    const averageRisk = (horizon) => stations.length
      ? stations.reduce((sum, station) => sum + (station.horizons?.[horizon]?.risk_pct?.ge15cm || 0), 0) / stations.length
      : 0;
    const risk = (horizon) => Number(averageRisk(horizon).toFixed(1));

    return [
      { time: 'Now', riskScore: 0, upperBound: 0, lowerBound: 0 },
      { time: '+1h', riskScore: risk('1h'), upperBound: risk('1h'), lowerBound: 0 },
      { time: '+3h', riskScore: risk('3h'), upperBound: risk('3h'), lowerBound: 0 },
      { time: '+6h', riskScore: risk('6h'), upperBound: risk('6h'), lowerBound: 0 }
    ];
  }, [liveFloodData]);

  const currentRisk = liveArea.length > 0 ? liveArea[0].riskScore : 0;
  const peakRisk = liveArea.length > 0 ? Math.max(...liveArea.map(d => d.riskScore)) : 0;

  return (
    <section className="dashboard-card flex flex-shrink-0 flex-col" style={{ minHeight: "160px" }}>
      <SectionHeader
        title="Forecast Risk Score"
        subtitle="AI model confidence band — next 3 hours"
        icon={<TrendingUp className="h-4 w-4" />}
        trailing={
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500">
              Now: <span className="font-mono font-bold text-orange-400">{currentRisk}%</span>
            </span>
            <span className="text-xs text-slate-500">
              Peak: <span className="font-mono font-bold text-red-400">{peakRisk}%</span>
            </span>
          </div>
        }
      />
      <div className="flex-1" style={{ minHeight: "110px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={liveArea} margin={COMPACT_MARGIN}>
            <defs>
              <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity={0.45} />
                <stop offset="40%" stopColor="#f97316" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="upperBandGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.18} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" tick={{ fill: AXIS_TICK_COLOR, fontSize: 9 }} axisLine={{ stroke: AXIS_LINE_COLOR }} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fill: AXIS_TICK_COLOR, fontSize: 9 }} axisLine={{ stroke: AXIS_LINE_COLOR }} tickLine={false} tickFormatter={(v) => `${v}%`} width={28} />
            <Tooltip content={<RiskTooltip />} cursor={DARK_CURSOR_STYLE} />
            {liveArea.length > 0 && (
              <>
                <Area type="monotone" dataKey="upperBound" name="Upper Bound" stroke="none" fill="url(#upperBandGradient)" fillOpacity={1} />
                <Area type="monotone" dataKey="riskScore" name="Risk Score" stroke={CHART_COLORS.riskArea} strokeWidth={2.5} fill="url(#riskGradient)" fillOpacity={1} dot={false} activeDot={{ r: 5, fill: "#f97316", strokeWidth: 0 }} style={{ filter: "drop-shadow(0px 4px 8px rgba(239,68,68,0.5))" }} />
                <Area type="monotone" dataKey="lowerBound" name="Lower Bound" stroke="none" fill="#0f172a" fillOpacity={1} />
              </>
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
