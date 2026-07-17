"use client";

import { useEffect, useRef } from "react";
import { MapPin } from "lucide-react";
import { MentionedEntity } from "../lib/types";

export default function CoordinateMap({ entities }: { entities: MentionedEntity[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current || entities.length === 0) return;
    let disposed = false;
    let mapInstance: import("leaflet").Map | null = null;

    async function mountMap() {
      const L = await import("leaflet");
      if (disposed || !containerRef.current) return;

      const points = entities
        .map((entity) => ({
          entity,
          lat: Number(entity.lat),
          lng: Number(entity.lng)
        }))
        .filter((point) => Number.isFinite(point.lat) && Number.isFinite(point.lng));

      if (!points.length) return;

      mapInstance = L.map(containerRef.current, {
        zoomControl: true,
        attributionControl: true,
        scrollWheelZoom: false
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(mapInstance);

      const bounds = L.latLngBounds([]);
      points.forEach((point, index) => {
        const marker = L.circleMarker([point.lat, point.lng], {
          radius: 8,
          color: "#3f342e",
          weight: 2,
          fillColor: index === 0 ? "#db8b12" : "#1aa7e8",
          fillOpacity: 0.85
        }).addTo(mapInstance as import("leaflet").Map);
        marker.bindPopup(`<strong>${point.entity.name}</strong><br/>${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}`);
        bounds.extend([point.lat, point.lng]);
      });

      if (points.length === 1) {
        mapInstance.setView([points[0].lat, points[0].lng], 15);
      } else {
        mapInstance.fitBounds(bounds, { padding: [28, 28], maxZoom: 15 });
      }
    }

    void mountMap();

    return () => {
      disposed = true;
      if (mapInstance) mapInstance.remove();
    };
  }, [entities]);

  if (!entities.length) return null;

  return (
    <section className="map-section">
      <h2>
        <MapPin size={17} aria-hidden />
        Mapa de coordenadas
        <span>{entities.length}</span>
      </h2>
      <div className="map-frame" ref={containerRef} />
      <p>Los marcadores representan centroides o puntos aproximados provistos por las fuentes del grafo.</p>
    </section>
  );
}
