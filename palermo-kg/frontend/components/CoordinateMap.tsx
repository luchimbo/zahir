"use client";

import { useEffect, useRef } from "react";
import { MapPin } from "lucide-react";
import { MentionedEntity } from "../lib/types";

const escapeHtml = (value: string) => value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char] ?? char);

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

      const clusters = new Map<string, typeof points>();
      points.forEach((point) => {
        const key = `${point.lat.toFixed(3)}:${point.lng.toFixed(3)}`;
        clusters.set(key, [...(clusters.get(key) ?? []), point]);
      });
      const bounds = L.latLngBounds([]);
      [...clusters.values()].forEach((cluster, index) => {
        const lat = cluster.reduce((sum, point) => sum + point.lat, 0) / cluster.length;
        const lng = cluster.reduce((sum, point) => sum + point.lng, 0) / cluster.length;
        const marker = L.circleMarker([lat, lng], {
          radius: Math.min(18, 7 + cluster.length * 2),
          color: "#3f342e",
          weight: 2,
          fillColor: index === 0 ? "#db8b12" : "#1aa7e8",
          fillOpacity: 0.85
        }).addTo(mapInstance as import("leaflet").Map);
        const names = cluster.slice(0, 5).map((point) => escapeHtml(point.entity.name)).join("<br/>");
        marker.bindPopup(cluster.length > 1 ? `<strong>${cluster.length} entidades</strong><br/>${names}` : `<strong>${names}</strong><br/>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
        bounds.extend([lat, lng]);
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
