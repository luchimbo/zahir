import { SearchEntity } from "../lib/types";

export default function StructuredResults({ results }: { results: SearchEntity[] }) {
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
