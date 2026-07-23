"use client";

import { MapPin, SlidersHorizontal, Star } from "lucide-react";
import { useState } from "react";
import { fetchJson } from "../lib/api";

type ExplorerRow = {
  id: string;
  name: string;
  entity_type: string;
  subtype?: string | null;
  description?: string | null;
};

type ExplorerPayload = { total: number; rows: ExplorerRow[] };

export default function ExplorerPanel() {
  const [type, setType] = useState("Organization");
  const [rating, setRating] = useState("0");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ExplorerPayload | null>(null);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ entity_type: type, geocoded: "true", limit: "6" });
      if (Number(rating) > 0) params.set("min_rating", rating);
      setData(await fetchJson<ExplorerPayload>(`/api/kg/query?${params.toString()}`));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="explorer-panel" aria-label="Explorar datos verificados">
      <header>
        <div>
          <span className="eyebrow"><SlidersHorizontal size={14} /> Explorar el grafo</span>
          <h2>Datos para recorrer</h2>
        </div>
        <button className="explorer-refresh" type="button" onClick={() => void load()} disabled={loading}>
          {loading ? "Consultando…" : `${data?.total ?? "—"} hallazgos · actualizar`}
        </button>
      </header>
      <div className="explorer-controls">
        <label>Tipo
          <select value={type} onChange={(event) => setType(event.target.value)}>
            <option value="Organization">Comercios</option>
            <option value="Facility">Lugares y servicios</option>
            <option value="Transport">Transporte</option>
            <option value="HistoricalRecord">Cultura e historia</option>
          </select>
        </label>
        <label>Rating mínimo
          <select value={rating} onChange={(event) => setRating(event.target.value)}>
            <option value="0">Cualquiera</option>
            <option value="4">4.0+</option>
            <option value="4.5">4.5+</option>
          </select>
        </label>
      </div>
      <div className="explorer-results" aria-live="polite">
        {loading ? <p>Consultando datos verificados…</p> : data?.rows.map((item) => (
          <a key={item.id} href={`/entity/${item.id}`} className="explorer-item">
            <span><MapPin size={15} /> {item.subtype?.replaceAll("_", " ") || item.entity_type}</span>
            <strong>{item.name}</strong>
            <small>{item.description || "Ver ficha y fuentes"}</small>
          </a>
        ))}
        {!loading && data?.rows.length === 0 ? <p>No hay resultados para esos filtros.</p> : null}
      </div>
      <footer><Star size={14} /> Solo muestra entidades activas, canónicas y georreferenciadas.</footer>
    </section>
  );
}
