import { useEffect, useState } from "react";
import axios from "axios";

import { MapContainer, TileLayer } from "react-leaflet";

import "leaflet/dist/leaflet.css";

function App() {
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    axios
      .get("http://localhost:8000/health")
      .then((res) => {
        if (res.data.status === "ok") {
          setConnected(true);
        }
      })
      .catch(console.error);
  }, []);

  return (
    <div style={{ padding: 20 }}>
      <h1>Flood Prediction</h1>

      <h3>
        Backend:
        {connected ? " ✅ Connected" : " ❌ Not Connected"}
      </h3>

      <MapContainer
        center={[13.7563, 100.5018]}
        zoom={11}
        style={{
          height: "600px",
          width: "100%",
        }}
      >
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      </MapContainer>
    </div>
  );
}

export default App;