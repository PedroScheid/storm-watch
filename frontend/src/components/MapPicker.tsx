// Mapa Leaflet + OpenStreetMap para escolher/trocar o local monitorado.

import { useEffect, useRef } from "react";
import L from "leaflet";

interface Props {
  lat: number;
  lon: number;
  onPick: (lat: number, lon: number) => void;
}

export default function MapPicker({ lat, lon, onPick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current).setView([lat, lon], 10);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    const marker = L.marker([lat, lon], { draggable: true }).addTo(map);
    marker.on("dragend", () => {
      const p = marker.getLatLng();
      onPick(p.lat, p.lng);
    });
    map.on("click", (e: L.LeafletMouseEvent) => {
      marker.setLatLng(e.latlng);
      onPick(e.latlng.lat, e.latlng.lng);
    });

    mapRef.current = map;
    markerRef.current = marker;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reposiciona quando lat/lon mudam por fora (ex.: "usar localização atual").
  useEffect(() => {
    if (mapRef.current && markerRef.current) {
      markerRef.current.setLatLng([lat, lon]);
      mapRef.current.setView([lat, lon]);
    }
  }, [lat, lon]);

  return <div ref={containerRef} className="map" aria-label="Mapa para escolher o local" />;
}
