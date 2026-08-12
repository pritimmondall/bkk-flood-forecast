<<<<<<< HEAD
import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import FloodMap from './FloodMap.jsx'
import { Summary, StationTable, StationChart, CityChart, ForecastVsObserved,
         Hotspots, Alerts, Limits, LiveStatus }
  from './Panels.jsx'

// A real flood: 29 stations alerting, 25 already under water. Opening on a
// quiet timestamp makes a working dashboard look broken, and the last
// available stamp (31 December) is dry season.
const DEMO_TS = '2025-11-13 03:00:00'

/**
 * Say what actually went wrong.
 */
function ErrorBanner({ err, window_, onReset }) {
  const outOfRange = err.kind === 'http' && err.status === 404 &&
                     /no data at this timestamp/i.test(err.detail || '')

  if (outOfRange) {
    return (
      <div className="err">
        <b>No data at that time.</b> This service replays history — it has no
        readings for a date outside the archive.
        {window_ && (
          <div className="muted" style={{ marginTop: 6 }}>
            Available: <code>{window_.first}</code> to <code>{window_.last}</code>,
            every {window_.cadence_minutes} minutes.
          </div>
        )}
        <div style={{ marginTop: 8 }}>
          <button className="primary" onClick={onReset}>
            Go to a real flood — {DEMO_TS}
          </button>
        </div>
      </div>
    )
  }

  if (err.kind === 'offline') {
    return (
      <div className="err">
        <b>Cannot reach the API.</b> <code>{err.detail}</code>
        <div className="muted" style={{ marginTop: 6 }}>
          Start the backend: <code>uvicorn backend.app.main:app --reload</code>
        </div>
      </div>
    )
  }

  return (
    <div className="err">
      <b>The API returned an error.</b>{' '}
      <code>{err.status} {err.path}</code>
      <div className="muted" style={{ marginTop: 6 }}>{err.detail}</div>
    </div>
  )
}

export default function App() {
  const [mode, setMode] = useState('replay')  // 'replay' | 'live'
  const [ts, setTs] = useState(DEMO_TS)
  const [pending, setPending] = useState(DEMO_TS)
  const [geo, setGeo] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [risk, setRisk] = useState(null)
  const [alerts, setAlerts] = useState(null)
  const [obs, setObs] = useState(null)
  const [hotspots, setHotspots] = useState(null)
  const [card, setCard] = useState(null)
  const [district, setDistrict] = useState(null)
  const [station, setStation] = useState(null)
  const [history, setHistory] = useState(null)
  const [tab, setTab] = useState('now')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [window_, setWindow] = useState(null)
  const [liveStatus, setLiveStatus] = useState(null)

  const isLive = mode === 'live'

  // Static, fetched once.
  useEffect(() => {
    Promise.all([api.districts(), api.hotspots(15), api.modelCard(), api.available()])
      .then(([g, h, c, w]) => { setGeo(g); setHotspots(h); setCard(c); setWindow(w) })
      .catch((e) => setErr(e))
  }, [])

  // Fetch live status when switching to live mode
  useEffect(() => {
    if (isLive) {
      api.liveStatus().then(setLiveStatus).catch(() => setLiveStatus(null))
    }
  }, [isLive])

  // Everything that depends on the mode and replay clock.
  useEffect(() => {
    let cancelled = false
    setBusy(true); setErr(null)
    Promise.all([
      api.forecast(ts, mode),
      api.risk(ts, mode),
      api.alerts(ts, mode),
      ...(isLive ? [] : [api.observations(ts, 24)]),
    ])
      .then((results) => {
        if (cancelled) return
        const [f, r, a, o] = results
        setForecast(f); setRisk(r); setAlerts(a)
        if (!isLive) setObs(o)
      })
      .catch((e) => {
        if (cancelled) return
        setErr(e)
        setForecast(null); setRisk(null); setAlerts(null); setObs(null)
        setHistory(null)
      })
      .finally(() => !cancelled && setBusy(false))
    return () => { cancelled = true }
  }, [ts, mode])

  // Live auto-refresh every 5 minutes
  useEffect(() => {
    if (!isLive) return
    const id = setInterval(() => {
      Promise.all([api.forecast(null, 'live'), api.risk(null, 'live'), api.alerts(null, 'live')])
        .then(([f, r, a]) => { setForecast(f); setRisk(r); setAlerts(a) })
        .catch(() => {})
      api.liveStatus().then(setLiveStatus).catch(() => {})
    }, 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [isLive])

  useEffect(() => {
    if (!station || isLive) { setHistory(null); return }
    api.history(station, ts, 24).then(setHistory).catch((e) => setErr(e))
  }, [station, ts, isLive])

  const step = useCallback((minutes) => {
    const d = new Date(ts.replace(' ', 'T') + 'Z')
    d.setUTCMinutes(d.getUTCMinutes() + minutes)
    const next = d.toISOString().slice(0, 19).replace('T', ' ')
    setTs(next); setPending(next)
  }, [ts])

  const toggleMode = useCallback(() => {
    setMode(m => m === 'replay' ? 'live' : 'replay')
    setErr(null)
    setForecast(null); setRisk(null); setAlerts(null)
    setObs(null); setHistory(null)
  }, [])

  return (
    <div className="app">
      {/* Mode banner */}
      {isLive ? (
        <div className="banner banner--live">
          <span className="pill pill--live">Live</span>
          <span>
            <b>LIVE — PARTIAL DATA.</b> Catches about <b>1 flood in 20</b> (5% event POD).
            Missing BMA rain gauges and road sensors.
          </span>
          <span className="spacer" />
          {forecast?.cold_start && (
            <span className="pill pill--warn">Cold Start</span>
          )}
          <span className="pill">CAP status: {alerts?.cap_status || 'Test'}</span>
          <button className="mode-toggle" onClick={toggleMode}>
            Switch to Replay
          </button>
        </div>
      ) : (
        <div className="banner">
          <span className="pill">Replay</span>
          <span>
            <b>Historical data, not a live feed.</b> Showing what the system
            would have said at the time below. 53% event POD.
          </span>
          <span className="spacer" />
          <span className="pill">CAP status: {alerts?.cap_status || 'Test'}</span>
          <button className="mode-toggle" onClick={toggleMode}>
            Switch to Live
          </button>
        </div>
      )}

      <header>
        <h1>Bangkok Flood Forecast</h1>
        <span className="muted">
          {forecast ? `${forecast.tier_cm} cm · ${forecast.horizon_hours} h ahead` : ''}
          {isLive && forecast?.timestamp ? ` · ${forecast.timestamp}` : ''}
        </span>
        <span className="spacer" />
        {!isLive && (
          <div className="controls">
            <button onClick={() => step(-60)} title="back one hour">‹ 1h</button>
            <button onClick={() => step(-15)}>‹ 15m</button>
            <input value={pending} onChange={(e) => setPending(e.target.value)}
                   style={{ width: 176 }} />
            <button className="primary" onClick={() => setTs(pending)}>Go</button>
            <button onClick={() => step(15)}>15m ›</button>
            <button onClick={() => step(60)} title="forward one hour">1h ›</button>
            <button onClick={() => { setTs(DEMO_TS); setPending(DEMO_TS) }}
                    title="a real flood event">Flood event</button>
          </div>
        )}
        {isLive && (
          <div className="controls">
            <span className="live-indicator">● Live</span>
            <span className="muted" style={{ fontSize: '0.85em' }}>
              Auto-refreshes every 5 min
            </span>
          </div>
        )}
      </header>

      {err && <ErrorBanner err={err} window_={window_}
                           onReset={() => { setTs(DEMO_TS); setPending(DEMO_TS); setMode('replay') }} />}

      {/* Performance badge */}
      {isLive && forecast?.mode_performance && (
        <div className="perf-badge perf-badge--live">
          Event POD: <b>{(forecast.mode_performance.event_pod * 100).toFixed(1)}%</b>
          {' · '}Precision: <b>{(forecast.mode_performance.precision * 100).toFixed(0)}%</b>
          {' · '}<span className="muted">{forecast.mode_performance.plain_english}</span>
        </div>
      )}

      <main>
        <FloodMap geo={geo} risk={risk} selected={district}
                  onSelectDistrict={(d) => { setDistrict(d); setStation(null) }} />

        <div className="side">
          {busy && <p className="muted">Loading{isLive ? ' live data' : ` ${ts}`}…</p>}

          <div className="tabs">
            <button aria-selected={tab === 'now'} onClick={() => setTab('now')}>Snapshot</button>
            {!isLive && (
              <button aria-selected={tab === 'trends'} onClick={() => setTab('trends')}>Trends</button>
            )}
            <button aria-selected={tab === 'alerts'} onClick={() => setTab('alerts')}>Alerts</button>
            {isLive && (
              <button aria-selected={tab === 'status'} onClick={() => setTab('status')}>Live Status</button>
            )}
            <button aria-selected={tab === 'limits'} onClick={() => setTab('limits')}>Limits</button>
          </div>

          {district && (
            <p className="muted" style={{ marginTop: 0 }}>
              Filtered to <b>{district}</b> ·{' '}
              <a href="#" onClick={(e) => { e.preventDefault(); setDistrict(null) }}
                 style={{ color: '#4a9eff' }}>clear</a>
            </p>
          )}

          {tab === 'now' && <>
            <Summary forecast={forecast} />
            {history && <StationChart history={history} />}
            <StationTable forecast={forecast} district={district}
                          onSelect={setStation} selectedStation={station} />
          </>}

          {tab === 'trends' && !isLive && <>
            <ForecastVsObserved obs={obs} />
            <CityChart obs={obs} />
            <Hotspots hotspots={hotspots} onSelect={(s) => { setStation(s); setTab('now') }} />
          </>}

          {tab === 'alerts' && <Alerts alerts={alerts} />}
          {tab === 'status' && isLive && <LiveStatus status={liveStatus} />}
          {tab === 'limits' && <Limits card={card} mode={mode} forecast={forecast} />}
        </div>
      </main>
    </div>
  )
}
=======
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
>>>>>>> 977641cc39ef29cfe39959f8fa6625c9dc98eb3d
