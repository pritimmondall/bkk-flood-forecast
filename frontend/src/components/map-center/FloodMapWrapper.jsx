import { useMemo } from 'react';
import Map from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { FloodHeatmap } from './FloodHeatmap';
import { useDashboardState } from '../../context/DashboardStateContext';

export function FloodMapWrapper({ liveFloodData }) {
  const { isLiveModelActive } = useDashboardState();
  
  return (
    <div className="h-full w-full rounded-xl overflow-hidden shadow-lg border border-slate-700 relative bg-slate-800 flex flex-col">
      <Map
        initialViewState={{
          longitude: 100.5018,
          latitude: 13.7563,
          zoom: 10.5
        }}
        mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        style={{ width: '100%', height: '100%' }}
      >
        <FloodHeatmap liveFloodData={liveFloodData} modelActive={isLiveModelActive !== undefined ? isLiveModelActive : true} />
      </Map>
    </div>
  );
}
