"use client";

import { Activity, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { fetchJson } from "../lib/api";

type Run = { source_name: string; status: string; completed_at?: string | null; error_message?: string | null };
type Payload = { totals: { entities: number; active_properties: number; synced_sources: number; sources: number }; latest_runs: Run[] };

export default function OperationsPanel() {
  const [data, setData] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true);
    try { setData(await fetchJson<Payload>("/api/kg/insights/operations")); }
    finally { setLoading(false); }
  }
  return <section className="operations-panel">
    <header><div><span className="eyebrow"><Activity size={14} /> Operaciones</span><h2>Pulso del grafo</h2></div>
      <button type="button" onClick={() => void refresh()} disabled={loading}><RefreshCw size={15} className={loading ? "spin" : ""} /> {loading ? "Actualizando" : "Ver estado"}</button></header>
    {data ? <><div className="ops-metrics"><b>{data.totals.entities}<small>entidades</small></b><b>{data.totals.active_properties}<small>hechos activos</small></b><b>{data.totals.synced_sources}/{data.totals.sources}<small>fuentes al día</small></b></div>
      <div className="ops-runs">{data.latest_runs.slice(0, 5).map((run) => <div key={run.source_name}><span className={`status ${run.status}`}>{run.status}</span><strong>{run.source_name}</strong><small>{run.error_message || run.completed_at || "En curso"}</small></div>)}</div></> : <p><ShieldCheck size={15} /> Consultá fuentes, cobertura y últimas ejecuciones desde un solo lugar.</p>}
  </section>;
}
