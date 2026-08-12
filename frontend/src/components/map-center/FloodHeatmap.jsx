import { useMemo } from 'react';
import { Source, Layer, useMap } from 'react-map-gl/maplibre';

export function FloodHeatmap({ modelActive, liveFloodData }) {
  const { current: map } = useMap();

  const geoJsonData = useMemo(() => {
    if (!liveFloodData) return null;
    
    if (liveFloodData.type === 'FeatureCollection' && Array.isArray(liveFloodData.features)) {
      return {
        ...liveFloodData,
        features: liveFloodData.features.map((feature) => ({
          ...feature,
          properties: {
            ...feature.properties,
            // MapLibre heatmaps use a 0–1 weight. The API returns calibrated %.
            probability: (feature.properties?.horizons?.["1h"]?.risk_pct?.ge15cm || 0) / 100
          }
        }))
      };
    }

    if (Array.isArray(liveFloodData)) {
      return {
        type: 'FeatureCollection',
        features: liveFloodData.map(point => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [point.lng || point.longitude || 0, point.lat || point.latitude || 0] },
          properties: { probability: point.probability || point.flood_probability || point.risk || 0 }
        }))
      };
    }
    
    return null;
  }, [liveFloodData]);

    if (!modelActive || !geoJsonData) {
    return null;
  }

  return (
    <Source id="flood-predictions" type="geojson" data={geoJsonData}>
      <Layer 
        id="flood-heatmap-layer"
        type="heatmap"
        source="flood-predictions"
        paint={{
          "heatmap-weight": ["get", "probability"],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 1, 9, 3],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(33,102,172,0)",
            0.2, "rgb(103,169,207)",
            0.4, "rgb(209,229,240)",
            0.6, "rgb(253,219,199)",
            0.8, "rgb(239,138,98)",
            1, "rgb(178,24,43)"
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 30, 9, 70],
          "heatmap-opacity": 0.8
        }}
      />
      <Layer
        id="flood-station-points"
        type="circle"
        source="flood-predictions"
        paint={{
          "circle-radius": 5,
          "circle-color": ["interpolate", ["linear"], ["get", "probability"], 0, "#22c55e", 0.3, "#eab308", 0.6, "#f97316", 1, "#ef4444"],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#f8fafc",
          "circle-opacity": 0.9
        }}
      />
    </Source>
  );
}
