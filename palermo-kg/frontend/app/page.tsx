"use client";

import {
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  Clipboard,
  History,
  Info,
  Loader2,
  Network,
  Search,
  Sparkles,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import CoordinateMap from "../components/CoordinateMap";
import ExplorerPanel from "../components/ExplorerPanel";
import Explainability from "../components/Explainability";
import GraphLoader from "../components/GraphLoader";
import MentionedEntities from "../components/MentionedEntities";
import OperationsPanel from "../components/OperationsPanel";
import StructuredResults from "../components/StructuredResults";
import { fetchJson } from "../lib/api";
import { deriveExplainability, deriveMentioned } from "../lib/derive";
import { renderMarkdown } from "../lib/format";
import { GeographiesPayload, NaturalPayload, Phase, SearchEntity, SearchPayload } from "../lib/types";

const SUGGESTIONS = [
  "Qué parques gratuitos hay en Caballito?",
  "Qué museos hay en San Telmo?",
  "Qué habilitaciones tipo café hay en Villa Crespo?",
  "Qué monumentos hay en Recoleta?",
  "Qué ferias o mercados hay en Palermo?"
];

const HISTORY_KEY = "caba-kg-search-history";

export default function Home() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [naturalPayload, setNaturalPayload] = useState<NaturalPayload | null>(null);
  const [structuredResults, setStructuredResults] = useState<SearchEntity[]>([]);
  const [history, setHistory] = useState<string[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(saved) ? saved.slice(0, 8) : [];
    } catch {
      return [];
    }
  });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [structuredOpen, setStructuredOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [geographies, setGeographies] = useState<GeographiesPayload | null>(null);
  const [neighborhood, setNeighborhood] = useState("");
  const [commune, setCommune] = useState("");

  useEffect(() => {
    void fetchJson<GeographiesPayload>("/api/kg/geographies")
      .then(setGeographies)
      .catch(() => setGeographies(null));
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
      const geographyParams = new URLSearchParams();
      if (neighborhood) geographyParams.set("neighborhood", neighborhood);
      else if (commune) geographyParams.set("commune", commune);
      const scope = geographyParams.toString();
      const suffix = scope ? `&${scope}` : "";
      const [natural, search] = await Promise.all([
        fetchJson<NaturalPayload>(
          `/api/kg/search/natural?q=${encodeURIComponent(trimmed)}&max_entities=6${suffix}`
        ),
        fetchJson<SearchPayload>(
          `/api/kg/search?q=${encodeURIComponent(trimmed)}&limit=10&min_score=0.2${suffix}`
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
        <span>CABA Knowledge Search</span>
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
              <h1>CABA Knowledge Search</h1>
              <p>Datos verificables de los 48 barrios, con citas, entidades y explicación.</p>
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
              placeholder="¿Qué querés saber sobre CABA?"
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
          <div className="geography-controls" aria-label="Filtros geográficos">
            <label>
              Barrio
              <select value={neighborhood} onChange={(event) => { setNeighborhood(event.target.value); if (event.target.value) setCommune(""); }} disabled={phase === "loading"}>
                <option value="">Toda CABA</option>
                {geographies?.neighborhoods.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}
              </select>
            </label>
            <label>
              Comuna
              <select value={commune} onChange={(event) => { setCommune(event.target.value); if (event.target.value) setNeighborhood(""); }} disabled={phase === "loading"}>
                <option value="">Todas</option>
                {geographies?.communes.map((item) => <option key={item.slug} value={item.commune ?? ""}>{item.name}</option>)}
              </select>
            </label>
            <span>{neighborhood ? "Barrio oficial" : commune ? "Filtro por comuna" : "Cobertura: toda CABA"}</span>
          </div>
          {submittedQuery ? (
            <div className="submitted-chip">{submittedQuery}</div>
          ) : null}
        </form>

        {phase === "idle" ? (
          <>
            <div className="suggestion-stack" aria-label="Preguntas sugeridas">
              {SUGGESTIONS.map((item) => (
                <button key={item} type="button" onClick={() => void submitSearch(item)}>
                  {item}
                </button>
              ))}
            </div>
            <ExplorerPanel />
            <OperationsPanel />
          </>
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
