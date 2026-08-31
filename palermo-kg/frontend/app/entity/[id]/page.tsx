"use client";

import {
  ArrowLeft,
  Boxes,
  CalendarClock,
  ExternalLink,
  FileText,
  GitBranch,
  Link as LinkIcon,
  MapPin,
  Network,
  ShieldCheck,
  Tags
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

type Entity = {
  id: string;
  name: string;
  entity_type: string;
  subtype?: string | null;
  description?: string | null;
  lat?: string | number | null;
  lng?: string | number | null;
  importance?: number | null;
  origin_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type EntityProperty = {
  key: string;
  value: string;
  value_type?: string;
  valid_from?: string | null;
  valid_until?: string | null;
  confidence?: number | string | null;
  origins?: string[] | null;
  last_seen_at?: string | null;
  source_name?: string | null;
  source_url?: string | null;
};

type Relationship = {
  relationship_type: string;
  direction?: string | null;
  weight?: number | string | null;
  confidence?: number | string | null;
  related_id: string;
  related_name: string;
  related_type: string;
  relation_side?: "incoming" | "outgoing";
};

type EntityPayload = {
  entity: Entity;
  properties: EntityProperty[];
  relationships: Relationship[];
  tags: string[];
};

type Phase = "loading" | "ready" | "error";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? "No se pudo consultar la entidad");
  }
  return payload;
}

function sourceHost(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "fuente";
  }
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return date.toLocaleDateString("es-AR", { year: "numeric", month: "short", day: "2-digit" });
}

function formatConfidence(value?: number | string | null) {
  if (value === undefined || value === null) return "sin confidence";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return `${Math.round(number * 100)}% confidence`;
}

function groupProperties(properties: EntityProperty[]) {
  const groups = new Map<string, EntityProperty[]>();
  for (const property of properties) {
    const rows = groups.get(property.key) ?? [];
    rows.push(property);
    groups.set(property.key, rows);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function propertyCategory(key: string) {
  if (key.startsWith("urban_") || key.startsWith("buildable_") || ["hydric_risk", "heritage_catalogued", "future_widening", "future_opening"].includes(key)) return "Urbanismo y restricciones";
  if (["address", "phone", "website", "neighborhood", "commune"].includes(key)) return "Ubicación y contacto";
  if (key.startsWith("indec_") || key.startsWith("census_") || key === "population" || key === "households" || key === "dwellings") return "Demografía";
  if (key.startsWith("school_") || key === "education_offer" || key === "education_level") return "Educación";
  if (key.startsWith("historical_") || key === "sinca_category") return "Cultura histórica";
  if (key === "geometry_geojson" || key.startsWith("georef_")) return "Geografía";
  return "Datos verificados";
}

function collectSources(payload: EntityPayload | null) {
  if (!payload) return [];
  const sources = new Map<string, { url: string; host: string; count: number }>();

  function add(url?: string | null) {
    if (!url) return;
    const current = sources.get(url);
    if (current) {
      current.count += 1;
      return;
    }
    sources.set(url, { url, host: sourceHost(url), count: 1 });
  }

  add(payload.entity.origin_url);
  for (const property of payload.properties) {
    for (const origin of property.origins ?? []) add(origin);
  }

  return [...sources.values()].sort((a, b) => b.count - a.count || a.host.localeCompare(b.host));
}

function compactId(id: string) {
  return `${id.slice(0, 8)}...${id.slice(-6)}`;
}

export default function EntityPage() {
  const params = useParams<{ id: string }>();
  const entityId = params.id;
  const [phase, setPhase] = useState<Phase>("loading");
  const [payload, setPayload] = useState<EntityPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;

    fetchJson<EntityPayload>(`/api/kg/entity/${entityId}`)
      .then((nextPayload) => {
        if (disposed) return;
        setPayload(nextPayload);
        setPhase("ready");
      })
      .catch((err) => {
        if (disposed) return;
        setError(err instanceof Error ? err.message : "Error desconocido");
        setPhase("error");
      });

    return () => {
      disposed = true;
    };
  }, [entityId]);

  const propertyGroups = useMemo(
    () => groupProperties(payload?.properties ?? []),
    [payload?.properties]
  );
  const categorizedProperties = useMemo(() => {
    const categories = new Map<string, Array<[string, EntityProperty[]]>>();
    for (const group of propertyGroups) {
      const category = propertyCategory(group[0]);
      categories.set(category, [...(categories.get(category) ?? []), group]);
    }
    return [...categories.entries()];
  }, [propertyGroups]);
  const sourceSummary = useMemo(() => collectSources(payload), [payload]);

  const entity = payload?.entity;
  const lat = entity?.lat === undefined || entity?.lat === null ? null : Number(entity.lat);
  const lng = entity?.lng === undefined || entity?.lng === null ? null : Number(entity.lng);
  const hasCoordinates = Number.isFinite(lat) && Number.isFinite(lng);

  return (
    <main className="kg-page">
      <nav className="topbar" aria-label="Breadcrumb">
        <Link className="back-link" href="/">
          <ArrowLeft size={15} aria-hidden />
          Search
        </Link>
        <span>/</span>
        <span>Entity</span>
        <span>/</span>
        <strong>{compactId(entityId)}</strong>
      </nav>

      <section className="entity-stage">
        {phase === "loading" ? (
          <div className="entity-loading">
            <Network size={22} aria-hidden />
            Cargando entidad...
          </div>
        ) : null}

        {phase === "error" && error ? <div className="error-card">{error}</div> : null}

        {phase === "ready" && entity ? (
          <>
            <header className="entity-hero">
              <div className="entity-title-block">
                <div className="brand-icon">
                  <Boxes size={23} aria-hidden />
                </div>
                <div>
                  <p>{entity.entity_type}{entity.subtype ? ` / ${entity.subtype}` : ""}</p>
                  <h1>{entity.name}</h1>
                </div>
              </div>
              <div className="entity-meta-strip">
                <span>
                  <ShieldCheck size={15} aria-hidden />
                  {entity.importance ?? 0} importance
                </span>
                <span>
                  <FileText size={15} aria-hidden />
                  {propertyGroups.length} propiedades
                </span>
                <span>
                  <GitBranch size={15} aria-hidden />
                  {payload.relationships.length} relaciones
                </span>
                <span>
                  <ExternalLink size={15} aria-hidden />
                  {sourceSummary.length} fuentes
                </span>
              </div>
            </header>

            <section className="entity-summary-grid">
              <article>
                <h2>Perfil</h2>
                <p>{entity.description || "Sin descripción cargada."}</p>
                <dl>
                  <div>
                    <dt>ID</dt>
                    <dd>{entity.id}</dd>
                  </div>
                  <div>
                    <dt>Actualizado</dt>
                    <dd>{formatDate(entity.updated_at) || "sin fecha"}</dd>
                  </div>
                  {hasCoordinates ? (
                    <div>
                      <dt>Coordenadas</dt>
                      <dd>{lat!.toFixed(6)}, {lng!.toFixed(6)}</dd>
                    </div>
                  ) : null}
                </dl>
                {entity.origin_url ? (
                  <a className="entity-source-link" href={entity.origin_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} aria-hidden />
                    {sourceHost(entity.origin_url)}
                  </a>
                ) : null}
              </article>

              <article>
                <h2>
                  <Tags size={17} aria-hidden />
                  Tags
                </h2>
                {payload.tags.length ? (
                  <div className="entity-tags">
                    {payload.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                ) : (
                  <p>Sin tags cargados.</p>
                )}
              </article>

              <article>
                <h2>
                  <ExternalLink size={17} aria-hidden />
                  Fuentes
                </h2>
                {sourceSummary.length ? (
                  <div className="entity-source-list">
                    {sourceSummary.slice(0, 8).map((source) => (
                      <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                        <span>{source.host}</span>
                        <small>{source.count} refs</small>
                        <ExternalLink size={13} aria-hidden />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p>Sin fuentes directas cargadas.</p>
                )}
              </article>
            </section>

            <section className="entity-section">
              <h2>
                <FileText size={17} aria-hidden />
                Propiedades verificadas
              </h2>
              {entity.entity_type === "HistoricalRecord" ? <p className="entity-warning">Registro histórico: no representa una actividad o estado actual.</p> : null}
              {payload.properties.some((property) => property.source_name === "sinca") ? <p className="entity-warning">Datos culturales SINCA: fuente histórica; confirmar vigencia antes de usarla como estado actual.</p> : null}
              {payload.properties.some((property) => ["refes_historical", "transporte_rmba", "cep_xxi", "enacom_context"].includes(property.source_name ?? "")) ? <p className="entity-warning">Dato histórico o agregado: verificar período y cobertura geográfica antes de interpretarlo como estado actual de CABA.</p> : null}
              <div className="property-groups">
                {categorizedProperties.map(([category, groups]) => (
                  <div key={category} className="property-category">
                    <h3>{category}</h3>
                    {groups.map(([key, rows]) => (
                  <article key={key} className="property-group">
                    <header>
                      <strong>{key}</strong>
                      <span>{rows.length}</span>
                    </header>
                    {rows.map((property, index) => (
                      <div className="property-row" key={`${key}-${index}-${property.value}`}>
                        <p>{property.value}</p>
                        <div className="property-meta">
                          <span>{property.value_type || "string"}</span>
                          <span>{formatConfidence(property.confidence)}</span>
                          {property.valid_from ? <span>desde {formatDate(property.valid_from)}</span> : null}
                          {property.valid_until ? <span>hasta {formatDate(property.valid_until)}</span> : <span>vigente</span>}
                          {property.last_seen_at ? (
                            <span>
                              <CalendarClock size={13} aria-hidden />
                              visto {formatDate(property.last_seen_at)}
                            </span>
                          ) : null}
                          {property.source_name ? <span>fuente: {property.source_name}</span> : null}
                        </div>
                        {property.origins?.length ? (
                          <div className="source-stack entity-sources">
                            {property.origins.map((origin) => (
                              <a key={origin} href={origin} target="_blank" rel="noreferrer">
                                <span>{sourceHost(origin)}</span>
                                <small>origin</small>
                                <ExternalLink size={13} aria-hidden />
                              </a>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                  </article>
                    ))}
                  </div>
                ))}
              </div>
            </section>

            <section className="entity-section">
              <h2>
                <GitBranch size={17} aria-hidden />
                Relaciones
              </h2>
              {payload.relationships.length ? (
                <div className="relationship-list">
                  {payload.relationships.map((relationship) => (
                    <a key={`${relationship.relationship_type}-${relationship.related_id}`} href={`/entity/${relationship.related_id}`}>
                      <span>{relationship.relation_side === "incoming" ? "RECIBE" : relationship.relationship_type}</span>
                      <strong>{relationship.related_name}</strong>
                      <small>{relationship.related_type} · {formatConfidence(relationship.confidence)}</small>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="structured-empty">No hay relaciones cargadas.</div>
              )}
            </section>

            {hasCoordinates ? (
              <section className="entity-section">
                <h2>
                  <MapPin size={17} aria-hidden />
                  Ubicación
                </h2>
                <EntityMap name={entity.name} lat={lat!} lng={lng!} />
                <a
                  className="entity-map-link"
                  href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=17/${lat}/${lng}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <LinkIcon size={16} aria-hidden />
                  Abrir coordenadas en OpenStreetMap
                </a>
              </section>
            ) : null}
          </>
        ) : null}
      </section>
    </main>
  );
}

function EntityMap({ name, lat, lng }: { name: string; lat: number; lng: number }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    let disposed = false;
    let mapInstance: import("leaflet").Map | null = null;

    async function mountMap() {
      const L = await import("leaflet");
      if (disposed || !containerRef.current) return;

      mapInstance = L.map(containerRef.current, {
        zoomControl: true,
        attributionControl: true,
        scrollWheelZoom: false
      }).setView([lat, lng], 16);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(mapInstance);

      L.circleMarker([lat, lng], {
        radius: 8,
        color: "#3f342e",
        weight: 2,
        fillColor: "#db8b12",
        fillOpacity: 0.9
      })
        .addTo(mapInstance)
        .bindPopup(`<strong>${name}</strong><br/>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    }

    void mountMap();

    return () => {
      disposed = true;
      if (mapInstance) mapInstance.remove();
    };
  }, [lat, lng, name]);

  return <div className="map-frame entity-map-frame" ref={containerRef} />;
}
