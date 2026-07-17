import { ExternalLink, Sparkles } from "lucide-react";
import { ExplainabilityItem } from "../lib/types";
import { sourceHost } from "../lib/format";

export default function Explainability({ items }: { items: ExplainabilityItem[] }) {
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
