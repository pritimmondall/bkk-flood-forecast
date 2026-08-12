import { useEffect, useRef } from 'react'
import L from 'leaflet'

const COLOURS = { none: '#2d6a4f', low: '#b08900', moderate: '#cc6600', high: '#b3241f' }

/**
 * District polygons shaded by the share of that district's sensors alerting.
 *
 * WHY POLYGONS AND NOT PINS. Every station coordinate in this project is a
 * district centroid — all sensors in a district share one point. Drawing them
 * as pins would place several markers on a spot where none of the sensors
 * actually is, which reads as precision the data does not have.
 *
 * A shaded district says "some sensors here are alerting" and nothing more,
 * which is exactly what we know. The API returns `is_flood_extent: false` for
 * the same reason and the legend repeats it, because a coloured map is the
 * easiest thing in this whole system to over-read.
 */
export default function FloodMap({ geo, risk, onSelectDistrict, selected }) {
  const el = useRef(null)
  const map = useRef(null)
  const layer = useRef(null)

  useEffect(() => {
    if (map.current || !el.current) return
    map.current = L.map(el.current, { zoomControl: true }).setView([13.75, 100.52], 11)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap, &copy; CARTO', maxZoom: 18,
    }).addTo(map.current)
  }, [])

  useEffect(() => {
    if (!map.current || !geo) return
    if (layer.current) layer.current.remove()

    const byName = {}
    ;(risk?.districts || []).forEach((d) => { byName[d.district] = d })

    layer.current = L.geoJSON(geo, {
      style: (f) => {
        const d = byName[f.properties.name]
        const isSel = selected === f.properties.name
        return {
          color: isSel ? '#4a9eff' : '#3a444f',
          weight: isSel ? 2.5 : 1,
          // Districts with no sensors are drawn hollow rather than green.
          // "No data" and "no flooding" must not look the same.
          fillColor: d ? COLOURS[d.level] || '#2d6a4f' : '#1a2027',
          fillOpacity: d ? 0.62 : 0.18,
        }
      },
      onEachFeature: (f, lyr) => {
        const d = byName[f.properties.name]
        lyr.bindTooltip(
          d
            ? `<b>${f.properties.name}</b><br/>${d.alerting} of ${d.stations} sensors alerting` +
              `<br/><span style="opacity:.7">deepest now: ${
                d.max_depth_cm == null ? 'no reading' : d.max_depth_cm.toFixed(1) + ' cm'
              }</span>`
            : `<b>${f.properties.name}</b><br/><i>no flood sensors</i>`,
          { sticky: true }
        )
        lyr.on('click', () => onSelectDistrict(d ? f.properties.name : null))
      },
    }).addTo(map.current)
  }, [geo, risk, selected, onSelectDistrict])

  return (
    <div style={{ position: 'relative', height: '100%' }}>
      <div id="map" ref={el} />
      <div className="legend">
        <div><span className="sw" style={{ background: COLOURS.none }} /> no sensor alerting</div>
        <div><span className="sw" style={{ background: COLOURS.low }} /> up to a third</div>
        <div><span className="sw" style={{ background: COLOURS.moderate }} /> a third to two thirds</div>
        <div><span className="sw" style={{ background: COLOURS.high }} /> most or all</div>
        <div><span className="sw" style={{ background: '#1a2027', border: '1px solid #3a444f' }} /> no flood sensors</div>
        {/* `note`, not a bare div: `.legend div` is display:flex for the swatch
            rows, and applying that to a paragraph makes each text node and the
            <b> a separate flex item — the sentence renders as scattered
            fragments. This is the one caveat on the map that most needs to be
            readable, so it gets its own class. */}
        <div className="note muted">
          Shading is the share of a district&apos;s few sensors, <b>not a flood extent</b>.
          When a district genuinely floods, typically only about a third of its
          sensors register it.
        </div>
      </div>
    </div>
  )
}
