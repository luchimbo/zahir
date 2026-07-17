import { Network } from "lucide-react";
import { MentionedEntity } from "../lib/types";
import { entityIcon } from "../lib/format";

export default function MentionedEntities({ entities }: { entities: MentionedEntity[] }) {
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
