// Thin fetch layer. Every call goes through here so a backend that is down
// produces one recognisable error rather than five different blank panels.
//
// WHY THE ERROR IS AN OBJECT AND NOT A STRING
// The first version threw `new Error("404 /api/forecast {...}")` and the UI
// rendered every failure as "Cannot reach the API — start the backend". That
// advice is wrong in the most common case: the backend answered perfectly well
// and said *this timestamp is outside the replay window*. Being told to start a
// server that is already running sends you looking in the wrong place.
//
// So the two cases are separated at the source. `kind: "offline"` means the
// fetch itself failed — nothing is listening. `kind: "http"` means the service
// replied and disagreed with the request, and `detail` carries its reason.

export class ApiError extends Error {
  constructor({ kind, status, path, detail }) {
    super(detail || `${status} ${path}`)
    this.name = 'ApiError'
    this.kind = kind          // "offline" | "http"
    this.status = status      // undefined when offline
    this.path = path
    this.detail = detail      // the service's own explanation, when it gave one
  }
}

const get = async (path) => {
  let r
  try {
    r = await fetch(path)
  } catch (e) {
    throw new ApiError({ kind: 'offline', path, detail: e.message })
  }

  if (!r.ok) {
    const body = await r.text().catch(() => '')
    let detail = body.slice(0, 300)
    try {
      const parsed = JSON.parse(body)
      if (parsed?.detail) detail = typeof parsed.detail === 'string'
        ? parsed.detail : JSON.stringify(parsed.detail)
    } catch { /* not JSON — keep the raw text */ }
    throw new ApiError({ kind: 'http', status: r.status, path, detail })
  }
  return r.json()
}

export const api = {
  available: () => get('/api/available'),
  modelCard: () => get('/api/model-card'),
  districts: () => get('/api/geo/districts'),
  forecast: (ts, mode = 'replay') => {
    const p = new URLSearchParams({ mode })
    if (mode === 'replay' && ts) p.set('ts', ts)
    return get(`/api/forecast?${p}`)
  },
  risk: (ts, mode = 'replay') => {
    const p = new URLSearchParams({ mode })
    if (mode === 'replay' && ts) p.set('ts', ts)
    return get(`/api/risk?${p}`)
  },
  alerts: (ts, mode = 'replay') => {
    const p = new URLSearchParams({ mode })
    if (mode === 'replay' && ts) p.set('ts', ts)
    return get(`/api/alerts?${p}`)
  },
  observations: (ts, hours = 24) =>
    get(`/api/observations?ts=${encodeURIComponent(ts)}&hours=${hours}`),
  history: (code, ts, hours = 24) =>
    get(`/api/history/${code}?ts=${encodeURIComponent(ts)}&hours=${hours}`),
  hotspots: (top = 15) => get(`/api/hotspots?top=${top}`),
  liveStatus: () => get('/api/live/status'),
}
