import { useMemo } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ResponsiveContainer } from "recharts";
import { BarChart2 } from "lucide-react";
import { DARK_TOOLTIP_STYLE, DARK_CURSOR_STYLE, AXIS_TICK_COLOR, AXIS_LINE_COLOR, COMPACT_MARGIN, GRID_STROKE } from "../../lib/chart";
import { SectionHeader } from "../shared/SectionHeader";
import { forecastStations } from "../../lib/floodApi";

function barColor(d) {
  if (d.probability >= 80) return "#ef4444"; // critical — red
  if (d.probability >= 60) return "#f97316"; // warning  — orange
  return "#eab308"; // watch    — yellow
}

function RiskTimelineTooltip({ active, label, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const color = barColor(d);
  return (
    <div style={DARK_TOOLTIP_STYLE} className="rounded-lg px-3 py-2 text-xs">
      <p className="mb-1 text-slate-400">{label}</p>
      <span style={{ color }} className="font-mono font-bold">
        {d.probability}% flood probability
      </span>
    </div>
  );
}

export function RiskTimelineBarChart({ liveFloodData }) {
  const liveTimeline = useMemo(() => {
    const stations = forecastStations(liveFloodData);
    const averageRisk = (horizon) => stations.length
      ? stations.reduce((sum, station) => sum + (station.horizons?.[horizon]?.risk_pct?.ge15cm || 0), 0) / stations.length
      : 0;
    return [
      { time: '+1h', probability: Number(averageRisk('1h').toFixed(1)) },
      { time: '+3h', probability: Number(averageRisk('3h').toFixed(1)) },
      { time: '+6h', probability: Number(averageRisk('6h').toFixed(1)) }
    ];
  }, [liveFloodData]);

  const peakProbability = liveTimeline.length > 0 ? Math.max(...liveTimeline.map((d) => d.probability)) : 0;

  // Graceful fallback while fetching
  if (liveTimeline.length === 0) return null;

  return (
    <section className="dashboard-card flex flex-shrink-0 flex-col" style={{ minHeight: "160px" }}>
      <SectionHeader
        title="Risk Timeline"
        subtitle="Flood probability escalation"
        icon={<BarChart2 className="h-4 w-4" />}
        trailing={
          <span className="text-xs font-bold text-red-400">
            Peak: <span className="font-mono">{peakProbability}%</span>
          </span>
        }
      />
      <div className="flex-1" style={{ minHeight: "110px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={liveTimeline} margin={COMPACT_MARGIN} barCategoryGap="20%">
            <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" tick={{ fill: AXIS_TICK_COLOR, fontSize: 9 }} axisLine={{ stroke: AXIS_LINE_COLOR }} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fill: AXIS_TICK_COLOR, fontSize: 9 }} axisLine={{ stroke: AXIS_LINE_COLOR }} tickLine={false} tickFormatter={(v) => `${v}%`} width={28} />
            <Tooltip content={<RiskTimelineTooltip />} cursor={DARK_CURSOR_STYLE} />
            <ReferenceLine y={75} stroke="#ef4444" strokeDasharray="4 2" strokeWidth={1.2} label={{ value: "75%", position: "insideTopRight", fill: "#ef4444", fontSize: 8 }} />
            <Bar dataKey="probability" name="Probability" radius={[3, 3, 0, 0]} style={{ filter: "drop-shadow(0px 2px 6px rgba(249,115,22,0.4))" }}>
              {liveTimeline.map((entry, index) => (
                <Cell fill={barColor(entry)} fillOpacity={0.9} key={`cell-${index}`} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
