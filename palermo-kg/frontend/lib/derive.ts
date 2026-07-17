import { ExplainabilityItem, MentionedEntity, NaturalPayload } from "./types";

export function deriveMentioned(payload: NaturalPayload | null): MentionedEntity[] {
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

export function deriveExplainability(payload: NaturalPayload | null): ExplainabilityItem[] {
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
