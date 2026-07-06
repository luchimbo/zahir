"use client";

import {
  ArrowRight,
  Boxes,
  Building2,
  Check,
  ChevronDown,
  ChevronRight,
  Clipboard,
  ExternalLink,
  History,
  Info,
  Loader2,
  MapPin,
  Network,
  Search,
  Sparkles,
  X
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";

type SourceRef = {
  url: string;
  valid_at?: string;
};

type Citation = {
  entity_id: string;
  entity_name: string;
  sources: SourceRef[];
};

type MentionedEntity = {
  id: string;
  name: string;
  type: string;
  subtype?: string | null;
  lat?: number | null;
  lng?: number | null;
  source_count?: number;
  synthetic?: boolean;
};

type ExplainabilityItem = {
  index: number;
  text: string;
  entity_id?: string;
  entity_name?: string;
  lat?: number | null;
  lng?: number | null;
  sources: SourceRef[];
};

type NaturalPayload = {
  query: string;
  answer: string;
  answer_markdown?: string;
  citations: Citation[];
  entities_used: Array<{ id: string; name: string; type: string }>;
  mentioned_entities?: MentionedEntity[];
  explainability?: ExplainabilityItem[];
};

type Property = {
  key: string;
  value: string;
  confidence?: number;
  origins?: string[];
};

type SearchEntity = {
  id: string;
  name: string;
  entity_type: string;
  subtype?: string | null;
  score?: number | null;
  importance?: number | null;
  properties?: Property[];
};

type SearchPayload = {
  query: string;
  results: SearchEntity[];
};

type Phase = "idle" | "loading" | "answered" | "error";

const SUGGESTIONS = [
  "Qué decks gastronómicos hay en Palermo?",
  "Qué zonas tienen más ruido nocturno?",
  "Qué habilitaciones tipo café hay en Palermo?",
  "Qué monumentos hay en Palermo?",
  "Qué ferias o mercados hay en Palermo?"
];

const HISTORY_KEY = "palermo-kg-search-history";

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? "No se pudo consultar la API");
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

function entityIcon(type: string) {
  if (type === "Organization") return <Building2 size={15} aria-hidden />;
  if (type === "Location") return <MapPin size={15} aria-hidden />;
  return <Boxes size={15} aria-hidden />;
}

function inlineMarkdown(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|\[\d+\])/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index === undefined) continue;
    if (match.index > cursor) nodes.push(text.slice(cursor, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={`${match.index}-b`}>{token.slice(2, -2)}</strong>);
    } else if (token.includes("](")) {
      const parsed = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (parsed) {
        nodes.push(
          <a key={`${match.index}-a`} href={parsed[2]} target="_blank" rel="noreferrer">
            {parsed[1]}
          </a>
        );
      }
    } else {
      nodes.push(<span key={`${match.index}-c`} className="citation-mark">{token}</span>);
    }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}

function renderMarkdown(markdown: string) {
  const blocks: ReactNode[] = [];
  const lines = markdown.split(/\r?\n/);
  let listItems: string[] = [];

  function flushList(key: string) {
    if (!listItems.length) return;
    blocks.push(
      <ul key={key}>
        {listItems.map((item, index) => (
          <li key={`${key}-${index}`}>{inlineMarkdown(item)}</li>
        ))}
      </ul>
    );
    listItems = [];
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList(`list-${index}`);
      return;
    }
    if (trimmed.startsWith("## ")) {
      flushList(`list-${index}`);
      blocks.push(<h2 key={index}>{inlineMarkdown(trimmed.slice(3))}</h2>);
      return;
    }
    if (trimmed.startsWith("### ")) {
      flushList(`list-${index}`);
      blocks.push(<h3 key={index}>{inlineMarkdown(trimmed.slice(4))}</h3>);
      return;
    }
    if (trimmed.startsWith("- ")) {
      listItems.push(trimmed.slice(2));
      return;
    }
    flushList(`list-${index}`);
    blocks.push(<p key={index}>{inlineMarkdown(trimmed)}</p>);
  });
  flushList("list-final");
  return blocks;
}

function deriveMentioned(payload: NaturalPayload | null): MentionedEntity[] {
  if (!payload) return [];
  if (payload.mentioned_entities?.length) return payload.mentioned_entities;
  return payload.entities_used.map((entity) => {
    const citation = payload.citations.find((item) => item.entity_id === entity.id);
    return {
      id: entity.id,
      name: entity.name,
      type: entity.type,
      source_count: citation?.sources.length ?? 0
    };
  });
}

function deriveExplainability(payload: NaturalPayload | null): ExplainabilityItem[] {
  if (!payload) return [];
  if (payload.explainability?.length) return payload.explainability;
  return payload.citations.map((citation, index) => ({
    index: index + 1,
    text: `El resultado ${citation.entity_name} se usa porque tiene fuentes verificadas dentro del Knowledge Graph.`,
    entity_id: citation.entity_id,
    entity_name: citation.entity_name,
    sources: citation.sources
  }));
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [naturalPayload, setNaturalPayload] = useState<NaturalPayload | null>(null);
  const [structuredResults, setStructuredResults] = useState<SearchEntity[]>([]);
  const [history, setHistory] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [structuredOpen, setStructuredOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      if (Array.isArray(saved)) setHistory(saved.slice(0, 8));
    } catch {
      setHistory([]);
    }
  }, []);

  const mentioned = useMemo(() => deriveMentioned(naturalPayload), [naturalPayload]);
  const explainability = useMemo(() => deriveExplainability(naturalPayload), [naturalPayload]);
  const answerMarkdown = naturalPayload?.answer_markdown || naturalPayload?.answer || "";
  const mappedEntities = useMemo(
    () => mentioned.filter((entity) => typeof entity.lat === "number" && typeof entity.lng === "number"),
    [mentioned]
  );

  function saveHistory(value: string) {
    const next = [value, ...history.filter((item) => item !== value)].slice(0, 8);
    setHistory(next);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  }

  async function submitSearch(nextQuery = query) {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setSubmittedQuery(trimmed);
    setPhase("loading");
    setError(null);
    setNaturalPayload(null);
    setStructuredResults([]);
    setStructuredOpen(false);
    setCopied(false);
    setHistoryOpen(false);
    saveHistory(trimmed);

    try {
      const [natural, search] = await Promise.all([
        fetchJson<NaturalPayload>(
          `/api/kg/search/natural?q=${encodeURIComponent(trimmed)}&max_entities=6`
        ),
        fetchJson<SearchPayload>(
          `/api/kg/search?q=${encodeURIComponent(trimmed)}&limit=10&min_score=0.2`
        )
      ]);
      setNaturalPayload(natural);
      setStructuredResults(search.results ?? []);
      setPhase("answered");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
      setPhase("error");
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitSearch();
  }

  async function copyAnswer() {
    if (!answerMarkdown) return;
    await navigator.clipboard.writeText(answerMarkdown);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1300);
  }

  return (
    <main className="kg-page">
      <nav className="topbar" aria-label="Breadcrumb">
        <button className="sidebar-toggle" type="button" aria-label="Menu">
          <span />
        </button>
        <span>Playground</span>
        <ChevronRight size={15} aria-hidden />
        <span>Palermo Knowledge Search</span>
        {submittedQuery ? (
          <>
            <ChevronRight size={15} aria-hidden />
            <strong>{submittedQuery}</strong>
          </>
        ) : null}
      </nav>

      <section className={`search-stage ${phase !== "idle" ? "is-active" : ""}`}>
        <header className="hero-header">
          <div className="hero-brand">
            <div className="brand-icon">
              <Network size={23} aria-hidden />
            </div>
            <div>
              <h1>Palermo Knowledge Search</h1>
              <p>Respuestas verificadas en markdown, con citas, entidades y explicación.</p>
            </div>
          </div>

          <div className="history-wrap">
            <button className="history-button" type="button" onClick={() => setHistoryOpen((open) => !open)}>
              <History size={16} aria-hidden />
              History
            </button>
            {historyOpen ? (
              <div className="history-popover">
                {history.length ? (
                  history.map((item) => (
                    <button key={item} type="button" onClick={() => void submitSearch(item)}>
                      {item}
                    </button>
                  ))
                ) : (
                  <span>No hay consultas todavía</span>
                )}
              </div>
            ) : null}
          </div>
        </header>

        <div className="endpoint-row">
          <span>/api/search/natural</span>
          <strong>endpoint</strong>
          <Info size={16} aria-label="Usa datos reales del Knowledge Graph" />
        </div>

        <form className={`query-composer ${phase === "loading" ? "is-loading" : ""}`} onSubmit={onSubmit}>
          <div className="composer-input-row">
            <Search size={22} aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="¿Qué querés saber sobre Palermo?"
              disabled={phase === "loading"}
            />
            {query ? (
              <button className="clear-button" type="button" aria-label="Limpiar" onClick={() => setQuery("")}>
                <X size={17} aria-hidden />
              </button>
            ) : null}
            <button className="submit-button" type="submit" aria-label="Buscar">
              {phase === "loading" ? <Loader2 className="spin" size={20} aria-hidden /> : <ArrowRight size={20} aria-hidden />}
            </button>
          </div>
          {submittedQuery ? (
            <div className="submitted-chip">{submittedQuery}</div>
          ) : null}
        </form>

        {phase === "idle" ? (
          <div className="suggestion-stack" aria-label="Preguntas sugeridas">
            {SUGGESTIONS.map((item) => (
              <button key={item} type="button" onClick={() => void submitSearch(item)}>
                {item}
              </button>
            ))}
          </div>
        ) : null}

        {phase === "loading" ? <GraphLoader /> : null}

        {phase === "error" && error ? (
          <div className="error-card">{error}</div>
        ) : null}

        {phase === "answered" && naturalPayload ? (
          <section className="answer-stack">
            <article className="answer-card">
              <header>
                <span>
                  <Sparkles size={17} aria-hidden />
                  Answer
                </span>
                <button type="button" onClick={() => void copyAnswer()} aria-label="Copiar respuesta">
                  {copied ? <Check size={17} aria-hidden /> : <Clipboard size={17} aria-hidden />}
                </button>
              </header>
              <div className="markdown-body">{renderMarkdown(answerMarkdown)}</div>
            </article>

            <MentionedEntities entities={mentioned} />
            <CoordinateMap entities={mappedEntities} />
            <Explainability items={explainability} />

            <section className="structured-support">
              <button type="button" onClick={() => setStructuredOpen((open) => !open)}>
                <span>Resultados estructurados</span>
                <small>{structuredResults.length} entidades</small>
                <ChevronDown className={structuredOpen ? "open" : ""} size={17} aria-hidden />
              </button>
              {structuredOpen ? <StructuredResults results={structuredResults} /> : null}
            </section>
          </section>
        ) : null}
      </section>
    </main>
  );
}

function GraphLoader() {
  return (
    <div className="graph-loader" aria-label="Buscando">
      <div className="node node-a" />
      <div className="node node-b" />
      <div className="node node-c" />
      <div className="node node-d" />
      <div className="node node-e" />
      <div className="edge edge-1" />
      <div className="edge edge-2" />
      <div className="edge edge-3" />
      <div className="edge edge-4" />
      <p>Buscando en el grafo de Palermo...</p>
    </div>
  );
}

function CoordinateMap({ entities }: { entities: MentionedEntity[] }) {
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

function MentionedEntities({ entities }: { entities: MentionedEntity[] }) {
  if (!entities.length) return null;
  return (
    <section className="mentioned-section">
      <h2>
        <Network size={17} aria-hidden />
        Mentioned Entities
        <span>{entities.length}</span>
      </h2>
      <div className="entity-chip-row">
        {entities.map((entity) => {
          const content = (
            <>
              {entityIcon(entity.type)}
              {entity.name}
            </>
          );
          return entity.synthetic ? (
            <span key={entity.id}>{content}</span>
          ) : (
            <a key={entity.id} href={`/entity/${entity.id}`}>
              {content}
            </a>
          );
        })}
      </div>
    </section>
  );
}

function Explainability({ items }: { items: ExplainabilityItem[] }) {
  if (!items.length) return null;
  return (
    <section className="explain-section">
      <h2>
        <Sparkles size={17} aria-hidden />
        Explainability
      </h2>
      <div className="timeline">
        {items.map((item) => (
          <article key={`${item.index}-${item.entity_id || item.text}`} className="timeline-item">
            <span className="timeline-index">{item.index}</span>
            <p>{item.text}</p>
            <div className="source-stack">
              {item.sources.slice(0, 3).map((source) => (
                <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
                  <span>{sourceHost(source.url)}</span>
                  <small>fuente</small>
                  <ExternalLink size={13} aria-hidden />
                </a>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function StructuredResults({ results }: { results: SearchEntity[] }) {
  if (!results.length) return <div className="structured-empty">No hay resultados estructurados.</div>;
  return (
    <div className="structured-list">
      {results.map((result) => (
        <a key={result.id} href={`/entity/${result.id}`}>
          <strong>{result.name}</strong>
          <span>
            {result.entity_type}
            {result.subtype ? ` / ${result.subtype}` : ""}
          </span>
        </a>
      ))}
    </div>
  );
}
