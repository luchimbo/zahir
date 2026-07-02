"use client";

import {
  ArrowRight,
  Building2,
  Database,
  ExternalLink,
  FileSearch,
  Loader2,
  MapPin,
  Search,
  ShieldCheck,
  Sparkles,
  Tags
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

type Property = {
  key: string;
  value: string;
  value_type?: string;
  confidence?: number;
  origins?: string[];
  valid_from?: string | null;
  valid_until?: string | null;
};

type SearchEntity = {
  id: string;
  name: string;
  entity_type: string;
  subtype?: string | null;
  description?: string | null;
  importance?: number | null;
  score?: number | null;
  properties?: Property[];
};

type SearchPayload = {
  query: string;
  results: SearchEntity[];
};

type EntityDetail = {
  entity: SearchEntity & {
    lat?: string | number | null;
    lng?: string | number | null;
    origin_url?: string | null;
  };
  properties: Property[];
  relationships: Array<{
    relationship_type: string;
    related_name: string;
    related_type: string;
    confidence?: number;
  }>;
  tags: string[];
};

type Mode = "search" | "query";

const quickSearches = [
  "Don Julio",
  "parrilla Palermo",
  "plaza serrano",
  "farmacia Palermo",
  "subte Palermo"
];

const quickQueries = [
  { label: "Restaurantes", entity_type: "Organization", subtype: "restaurant" },
  { label: "Bares", entity_type: "Organization", subtype: "bar" },
  { label: "Cafes", entity_type: "Organization", subtype: "cafe" },
  { label: "Farmacias", entity_type: "Facility", subtype: "farmacia" },
  { label: "Subte", entity_type: "Transport", subtype: "estacion_subte" },
  { label: "IGJ SA", entity_type: "LegalEntity", subtype: "SA" }
];

const visiblePropertyKeys = new Set([
  "address",
  "rating",
  "review_count",
  "phone",
  "website",
  "hours_open",
  "price_range",
  "cuisine_type",
  "source_url",
  "estado",
  "cuit"
]);

function formatPercent(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "s/d";
  return `${Math.round(value * 100)}%`;
}

function pickProperties(properties: Property[] = []) {
  const priority = properties.filter((prop) => visiblePropertyKeys.has(prop.key));
  return (priority.length ? priority : properties).slice(0, 6);
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? "No se pudo consultar la API");
  }
  return payload;
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("search");
  const [query, setQuery] = useState("Don Julio");
  const [results, setResults] = useState<SearchEntity[]>([]);
  const [selected, setSelected] = useState<EntityDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState("Listo para consultar");

  const resultStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const result of results) {
      counts.set(result.entity_type, (counts.get(result.entity_type) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([type, count]) => `${type}: ${count}`)
      .join(" / ");
  }, [results]);

  async function runSearch(nextQuery = query) {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;

    setMode("search");
    setQuery(trimmed);
    setLoading(true);
    setError(null);
    setSelected(null);
    setLastAction(`Busqueda: ${trimmed}`);

    try {
      const payload = await fetchJson<SearchPayload>(
        `/api/kg/search?q=${encodeURIComponent(trimmed)}`
      );
      setResults(payload.results ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function runQuery(entityType: string, subtype?: string) {
    setMode("query");
    setLoading(true);
    setError(null);
    setSelected(null);
    setLastAction(`${entityType}${subtype ? ` / ${subtype}` : ""}`);

    const params = new URLSearchParams({
      entity_type: entityType,
      limit: "25"
    });
    if (subtype) params.set("subtype", subtype);

    try {
      const payload = await fetchJson<{ rows: SearchEntity[] }>(
        `/api/kg/query?${params.toString()}`
      );
      setResults(payload.rows ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function loadEntity(entityId: string) {
    setDetailLoading(true);
    setError(null);

    try {
      const payload = await fetchJson<EntityDetail>(`/api/kg/entity/${entityId}`);
      setSelected(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setDetailLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch();
  }

  return (
    <main className="shell">
      <section className="masthead">
        <div>
          <p className="eyebrow">
            <Database size={16} aria-hidden />
            Palermo Knowledge Graph
          </p>
          <h1>Workbench de datos verificados</h1>
        </div>
        <div className="status-pill">
          <ShieldCheck size={16} aria-hidden />
          Neon activo / FastAPI local
        </div>
      </section>

      <section className="workspace">
        <aside className="control-panel">
          <div className="panel-title">
            <FileSearch size={18} aria-hidden />
            Consulta
          </div>

          <form className="search-form" onSubmit={onSubmit}>
            <label htmlFor="kg-search">Texto libre</label>
            <div className="search-box">
              <Search size={18} aria-hidden />
              <input
                id="kg-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ej: Don Julio, plaza serrano, farmacia"
              />
              <button type="submit" aria-label="Buscar">
                {loading && mode === "search" ? (
                  <Loader2 className="spin" size={18} aria-hidden />
                ) : (
                  <ArrowRight size={18} aria-hidden />
                )}
              </button>
            </div>
          </form>

          <div className="chip-grid" aria-label="Busquedas rapidas">
            {quickSearches.map((item) => (
              <button key={item} type="button" onClick={() => void runSearch(item)}>
                {item}
              </button>
            ))}
          </div>

          <div className="panel-title compact">
            <Tags size={18} aria-hidden />
            Colecciones
          </div>
          <div className="query-list">
            {quickQueries.map((item) => (
              <button
                key={`${item.entity_type}-${item.subtype}`}
                type="button"
                onClick={() => void runQuery(item.entity_type, item.subtype)}
              >
                <span>{item.label}</span>
                <small>{item.entity_type}</small>
              </button>
            ))}
          </div>
        </aside>

        <section className="result-panel">
          <div className="result-header">
            <div>
              <p className="eyebrow subtle">
                <Sparkles size={15} aria-hidden />
                {lastAction}
              </p>
              <h2>{results.length} resultados</h2>
            </div>
            <span>{resultStats || "Sin agrupacion"}</span>
          </div>

          {error ? <div className="notice error">{error}</div> : null}
          {loading ? <LoadingRows /> : null}

          {!loading && !error && results.length === 0 ? (
            <div className="notice">No hay resultados para esta consulta.</div>
          ) : null}

          <div className="results-list">
            {results.map((result) => (
              <button
                key={result.id}
                type="button"
                className="result-row"
                onClick={() => void loadEntity(result.id)}
              >
                <span className="type-icon">
                  {result.entity_type === "Organization" ? (
                    <Building2 size={18} aria-hidden />
                  ) : (
                    <MapPin size={18} aria-hidden />
                  )}
                </span>
                <span className="result-main">
                  <strong>{result.name}</strong>
                  <span>
                    {result.entity_type}
                    {result.subtype ? ` / ${result.subtype}` : ""}
                  </span>
                  {result.properties?.length ? (
                    <span className="property-strip">
                      {pickProperties(result.properties)
                        .map((prop) => `${prop.key}: ${prop.value}`)
                        .join("  |  ")}
                    </span>
                  ) : null}
                </span>
                <span className="confidence">
                  {mode === "search" ? formatPercent(result.score ?? undefined) : result.importance ?? "s/d"}
                </span>
              </button>
            ))}
          </div>
        </section>

        <aside className="detail-panel">
          <div className="panel-title">
            <Database size={18} aria-hidden />
            Entidad
          </div>

          {detailLoading ? (
            <div className="detail-empty">
              <Loader2 className="spin" size={24} aria-hidden />
              Cargando entidad
            </div>
          ) : selected ? (
            <EntityPanel detail={selected} />
          ) : (
            <div className="detail-empty">Selecciona un resultado</div>
          )}
        </aside>
      </section>
    </main>
  );
}

function EntityPanel({ detail }: { detail: EntityDetail }) {
  const origin = detail.entity.origin_url;
  const location =
    detail.entity.lat && detail.entity.lng
      ? `${detail.entity.lat}, ${detail.entity.lng}`
      : null;

  return (
    <div className="entity-detail">
      <div>
        <h3>{detail.entity.name}</h3>
        <p>
          {detail.entity.entity_type}
          {detail.entity.subtype ? ` / ${detail.entity.subtype}` : ""}
        </p>
      </div>

      {location ? (
        <div className="fact-line">
          <MapPin size={16} aria-hidden />
          {location}
        </div>
      ) : null}

      {origin ? (
        <a className="origin-link" href={origin} target="_blank" rel="noreferrer">
          Fuente principal
          <ExternalLink size={15} aria-hidden />
        </a>
      ) : null}

      {detail.tags.length ? (
        <div className="tag-row">
          {detail.tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      ) : null}

      <div className="property-table">
        {detail.properties.slice(0, 18).map((prop) => (
          <div key={`${prop.key}-${prop.value}`}>
            <span>{prop.key}</span>
            <strong>{prop.value}</strong>
            <small>confianza {formatPercent(prop.confidence)}</small>
          </div>
        ))}
      </div>

      {detail.relationships.length ? (
        <div className="relationships">
          <h4>Relaciones</h4>
          {detail.relationships.slice(0, 8).map((rel) => (
            <p key={`${rel.relationship_type}-${rel.related_name}`}>
              {rel.relationship_type}: {rel.related_name}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="loading-stack" aria-label="Cargando">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="skeleton-row" key={index} />
      ))}
    </div>
  );
}
