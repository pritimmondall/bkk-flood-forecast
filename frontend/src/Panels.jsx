import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
         ReferenceLine, BarChart, Bar, Legend } from 'recharts'

const hhmm = (t) => (t || '').slice(11, 16)

/**
 * WHY THIS HEADING IS A TIMESTAMP AND NOT "RIGHT NOW"
 *
 * It used to say "Right now". On a page whose banner says REPLAY and whose
 * clock says 13 November 2025, "right now" is simply false — and it is false in
 * the one direction this project cannot afford. Someone glancing at the panel
 * reads "25 flooded now" as twenty-five streets under water this minute.
 *
 * What the panel actually shows is the instantaneous state at the selected
 * timestamp, as opposed to the Trends tab which shows a window around it. So
 * the heading is the timestamp itself. There is no wording that means "now" in
 * a replay, and inventing one was the mistake.
 */
export function Summary({ forecast }) {
  const c = forecast?.counts
  if (!c) return null
  const t = forecast.timestamp || ''
  return (
    <div className="card">
      <h2>
        At {t.slice(0, 16) || 'the selected time'}
        <span className="muted" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
          replayed
        </span>
      </h2>
      <div className="stat-row">
        <div className="stat"><div className="n" style={{ color: '#cc6600' }}>{c.alerting}</div>
          <div className="l">alerting</div></div>
        <div className="stat"><div className="n" style={{ color: '#b3241f' }}>{c.flooded_now}</div>
          <div className="l">already flooded</div></div>
        <div className="stat"><div className="n" style={{ color: '#8b98a5' }}>{c.sensor_offline}</div>
          <div className="l">offline</div></div>
        <div className="stat"><div className="n">{c.total}</div>
          <div className="l">sensors</div></div>
      </div>
      <p className="muted" style={{ margin: '10px 0 0' }}>
        &quot;Alerting&quot; means the model expected water to reach{' '}
        {forecast.tier_cm} cm within {forecast.horizon_hours} hour of that moment.
        About 84% of alerts do not become floods.
      </p>
    </div>
  )
}

export function StationTable({ forecast, district, onSelect, selectedStation }) {
  let rows = forecast?.stations || []
  if (district) rows = rows.filter((s) => s.district === district)
  // Interesting first: flooded, then alerting, then by depth.
  rows = [...rows].sort((a, b) => {
    const rank = (s) => (s.status === 'flooded_now' ? 0 : s.alert ? 1 : s.status === 'sensor_offline' ? 3 : 2)
    return rank(a) - rank(b) || (b.depth_now_cm ?? -1) - (a.depth_now_cm ?? -1)
  })
  return (
    <div className="card">
      <h2>Sensors {district ? `— ${district}` : ''}</h2>
      {rows.length === 0 && <p className="muted">No sensors here.</p>}
      {rows.length > 0 && (
        <table>
          <thead><tr><th>Station</th><th>Depth</th><th>Chance</th></tr></thead>
          <tbody>
            {rows.slice(0, 40).map((s) => (
              <tr key={s.station_code} className="click"
                  onClick={() => onSelect(s.station_code)}
                  style={selectedStation === s.station_code
                    ? { outline: '1px solid #4a9eff' } : undefined}>
                <td>
                  <span className={'dot ' + (s.status === 'flooded_now' ? 'd-flooded'
                    : s.status === 'sensor_offline' ? 'd-offline'
                    : s.alert ? 'd-moderate' : 'd-clear')} />
                  {s.station_code}
                  {!district && <span className="muted"> · {s.district}</span>}
                </td>
                <td>{s.depth_now_cm == null
                  ? <span className="muted">offline</span>
                  : `${s.depth_now_cm.toFixed(1)} cm`}</td>
                <td>{s.status === 'flooded_now'
                  ? <span className="muted">already flooded</span>
                  : s.probability == null ? <span className="muted">—</span>
                  : `${(s.probability * 100).toFixed(1)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted" style={{ marginBottom: 0 }}>
        Depth predictions are deliberately not shown — the depth model failed its
        accuracy check.
      </p>
    </div>
  )
}

export function StationChart({ history }) {
  if (!history?.series?.length) return null
  const tier = history.tiers_cm?.advisory ?? 15
  return (
    <div className="card">
      <h2>{history.station_code} — last {history.window_hours} h</h2>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={history.series} margin={{ top: 4, right: 6, bottom: 0, left: -22 }}>
          <XAxis dataKey="ts" tickFormatter={hhmm} stroke="#8b98a5" fontSize={11}
                 minTickGap={40} />
          <YAxis stroke="#8b98a5" fontSize={11} />
          <Tooltip contentStyle={{ background: '#1a2027', border: '1px solid #2a333d' }}
                   labelFormatter={(t) => t} />
          <ReferenceLine y={tier} stroke="#b3241f" strokeDasharray="4 3"
                         label={{ value: `${tier} cm`, fill: '#b3241f', fontSize: 10 }} />
          <Line type="monotone" dataKey="depth_cm" stroke="#4a9eff" dot={false}
                strokeWidth={2} name="depth (cm)" />
          <Line type="monotone" dataKey="rain_mm_1h" stroke="#5faa35" dot={false}
                strokeWidth={1.4} name="rain (mm/h)" />
        </LineChart>
      </ResponsiveContainer>
      <p className="muted" style={{ margin: 0 }}>
        Blue: measured depth. Green: district rainfall. Both observed — no
        forecast line is drawn, because the model outputs a probability rather
        than a depth curve.
      </p>
    </div>
  )
}

export function CityChart({ obs }) {
  if (!obs?.series?.length) return null
  return (
    <div className="card">
      <h2>City-wide, last {obs.window_hours} h</h2>
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={obs.series} margin={{ top: 4, right: 6, bottom: 0, left: -22 }}>
          <XAxis dataKey="ts" tickFormatter={hhmm} stroke="#8b98a5" fontSize={11}
                 minTickGap={40} />
          <YAxis stroke="#8b98a5" fontSize={11} />
          <Tooltip contentStyle={{ background: '#1a2027', border: '1px solid #2a333d' }} />
          <Bar dataKey="rain_mm_1h" fill="#5faa35" name="rain mm/h" />
          <Bar dataKey="stations_over_15cm" fill="#cc6600" name="sensors over 15 cm" />
        </BarChart>
      </ResponsiveContainer>
      <p className="muted" style={{ margin: 0 }}>
        Canal level and flow are city-wide averages — canal sensor codes name
        canals, not districts, so they cannot be shown per district.
      </p>
    </div>
  )
}

/**
 * GFS forecast rain against what the gauges actually measured.
 *
 * This panel exists because GFS is inside the model but was invisible on the
 * screen, so nobody could see how much to trust it. It is the one input we most
 * want people to be sceptical of, which makes it the one that should be easiest
 * to inspect.
 *
 * ONE AXIS, deliberately. Both series are millimetres of rain in the same hour,
 * so they belong on the same scale — putting a second y-axis under one of them
 * is the standard way to make two unrelated shapes look correlated.
 *
 * ALIGNED TO VALID TIME by the API: `rain_fcst_mm_1h` has been shifted onto the
 * hour it describes, so a gap between the lines is real disagreement rather
 * than a one-hour offset. See `_align_forecast_to_valid_time` in serving.py.
 *
 * Colours are the validated dark-surface pair (CVD ΔE 9.9): observed #5faa35,
 * forecast #d55181, with the forecast dashed so identity never rests on colour
 * alone.
 */
export function ForecastVsObserved({ obs }) {
  const rows = (obs?.series || []).filter((r) => r.rain_fcst_mm_1h != null)
  if (!rows.length) return null

  const wet = rows.filter((r) => (r.rain_mm_1h ?? 0) >= 0.1 || (r.rain_fcst_mm_1h ?? 0) >= 0.1)
  const peakObs = Math.max(0, ...rows.map((r) => r.rain_mm_1h ?? 0))
  const peakFc = Math.max(0, ...rows.map((r) => r.rain_fcst_mm_1h ?? 0))

  return (
    <div className="card">
      <h2>Forecast rain vs measured rain</h2>
      <p className="muted" style={{ margin: '0 0 8px' }}>
        GFS is one of the model&apos;s 50 inputs. This is how well it did over the
        last {obs.window_hours} h, city-wide.
      </p>
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={rows} margin={{ top: 4, right: 6, bottom: 0, left: -22 }}>
          <XAxis dataKey="ts" tickFormatter={hhmm} stroke="#8b98a5" fontSize={11}
                 minTickGap={40} />
          <YAxis stroke="#8b98a5" fontSize={11}
                 label={{ value: 'mm/h', angle: -90, position: 'insideLeft',
                          fill: '#8b98a5', fontSize: 11, offset: 32 }} />
          <Tooltip contentStyle={{ background: '#1a2027', border: '1px solid #2a333d' }}
                   labelFormatter={(t) => t} />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
          <Line type="monotone" dataKey="rain_mm_1h" name="measured (BMA gauges)"
                stroke="#5faa35" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="rain_fcst_mm_1h" name="forecast (GFS, 13 km)"
                stroke="#d55181" strokeWidth={2} strokeDasharray="5 4" dot={false} />
        </LineChart>
      </ResponsiveContainer>
      <p className="muted" style={{ margin: '4px 0 0' }}>
        Peak this window — measured <b>{peakObs.toFixed(1)}</b> mm/h,
        forecast <b>{peakFc.toFixed(1)}</b> mm/h, over {wet.length} wet steps.
        Across 1.38 million district-hours the two correlate at <b>0.014</b> on
        wet hours. GFS can tell that the region is wet; at 13 km it cannot tell
        which district, because Bangkok&apos;s storm cells are 2–5 km across.
        It still earns its place: it adds about 7 caught floods per 100.
      </p>
    </div>
  )
}

export function Hotspots({ hotspots, onSelect }) {
  if (!hotspots?.hotspots) return null
  return (
    <div className="card">
      <h2>Floods most often, 2019–2025</h2>
      <table>
        <thead><tr><th>Station</th><th>Hours ≥15 cm</th><th>Deepest</th></tr></thead>
        <tbody>
          {hotspots.hotspots.slice(0, 10).map((h) => (
            <tr key={h.station_code} className="click" onClick={() => onSelect(h.station_code)}>
              <td>{h.station_code}<span className="muted"> · {h.district}</span></td>
              <td>{h.hours_over_15cm.toFixed(0)}</td>
              <td>{h.deepest_cm?.toFixed(0)} cm</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted" style={{ marginBottom: 0 }}>{hotspots.coverage_note}</p>
    </div>
  )
}

export function Alerts({ alerts }) {
  if (!alerts) return null
  return (
    <div className="card">
      <h2>CAP alerts <span className="pill">{alerts.cap_status}</span></h2>
      {alerts.count === 0 && <p className="muted">No alerts at this time.</p>}
      {alerts.count > 0 && (
        <>
          <p style={{ margin: '0 0 8px' }}>{alerts.count} message(s) would be issued.</p>
          <table>
            <thead><tr><th>Station</th><th>Severity</th><th>Urgency</th></tr></thead>
            <tbody>
              {alerts.alerts.slice(0, 12).map((a) => (
                <tr key={a.identifier}>
                  <td>{a.identifier.split('-')[1]}</td>
                  <td>{a.info.severity}</td>
                  <td>{a.info.urgency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <p className="muted" style={{ marginBottom: 0 }}>
        Status is <b>{alerts.cap_status}</b>. These are not public warnings and
        must not be issued as such without written BMA authorisation.
      </p>
    </div>
  )
}

export function Limits({ card, mode, forecast }) {
  if (!card) return null
  const p = card.performance
  const isLive = mode === 'live'
  const lp = forecast?.mode_performance
  return (
    <div className="card">
      <h2>What this system can and cannot do</h2>

      {isLive && lp && (
        <div className="live-perf-block">
          <h3 style={{ color: '#ff6b35', margin: '0 0 8px' }}>Live Mode Performance</h3>
          <div className="stat-row" style={{ marginBottom: 10 }}>
            <div className="stat"><div className="n" style={{ color: '#ff6b35' }}>
              {(lp.event_pod * 100).toFixed(1)}%</div>
              <div className="l">floods caught (live)</div></div>
            <div className="stat"><div className="n" style={{ color: '#ff6b35' }}>
              {(lp.precision * 100).toFixed(0)}%</div>
              <div className="l">alerts real (live)</div></div>
          </div>
          <p className="muted" style={{ margin: '0 0 12px' }}>
            {lp.plain_english}
          </p>
        </div>
      )}

      <h3 style={{ margin: '0 0 8px' }}>
        {isLive ? 'Replay Mode Performance (for comparison)' : 'Replay Mode Performance'}
      </h3>
      <div className="stat-row" style={{ marginBottom: 10 }}>
        <div className="stat"><div className="n">{Math.round(p.event_pod * 100)}%</div>
          <div className="l">floods caught early</div></div>
        <div className="stat"><div className="n">{Math.round(p.precision * 100)}%</div>
          <div className="l">alerts that are real</div></div>
        <div className="stat"><div className="n">{p.median_warning_minutes}m</div>
          <div className="l">typical warning</div></div>
      </div>
      <ul className="caveats">
        {card.known_limitations.slice(0, 5).map((l, i) => <li key={i}>{l}</li>)}
      </ul>
    </div>
  )
}

export function LiveStatus({ status }) {
  if (!status) return <div className="card"><p className="muted">Loading live status…</p></div>
  const cold = status.cold_start
  const sources = status.collector?.sources || []
  return (
    <div className="card">
      <h2>
        Live Collection Status
        {cold && <span className="pill pill--warn" style={{ marginLeft: 8 }}>Cold Start</span>}
      </h2>

      {cold && (
        <p style={{ color: '#ff6b35', margin: '0 0 12px' }}>
          ⚠ Less than 24 hours of collected data. Predictions are near-meaningless
          until lookback features have enough history.
        </p>
      )}

      <table style={{ width: '100%' }}>
        <thead><tr><th>Source</th><th>Status</th><th>Rows</th><th>Last Reading</th></tr></thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.source}>
              <td><b>{s.source}</b></td>
              <td style={{ color: s.ok ? '#3ab795' : '#b3241f' }}>
                {s.ok ? '✓ OK' : s.skipped ? '— Skipped' : '✗ Failed'}
              </td>
              <td>{s.rows ?? '—'}</td>
              <td className="muted">{s.latest_reading || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={{ marginTop: 16 }}>Available Features</h3>
      <ul className="caveats" style={{ columns: 1 }}>
        {(status.features_populated || []).map((f, i) => (
          <li key={i} style={{ color: '#3ab795' }}>✓ {f}</li>
        ))}
      </ul>

      <h3>Missing Features</h3>
      <ul className="caveats" style={{ columns: 1 }}>
        {(status.features_nan || []).map((f, i) => (
          <li key={i} style={{ color: '#8b98a5' }}>✗ {f}</li>
        ))}
      </ul>

      <h3>Missing Sources</h3>
      <ul className="caveats" style={{ columns: 1 }}>
        {(status.missing_sources || []).map((s, i) => (
          <li key={i} style={{ color: '#b3241f' }}>{s}</li>
        ))}
      </ul>
    </div>
  )
}
