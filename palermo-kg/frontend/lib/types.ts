export type SourceRef = {
  url: string;
  valid_at?: string;
};

export type Citation = {
  entity_id: string;
  entity_name: string;
  sources: SourceRef[];
};

export type MentionedEntity = {
  id: string;
  name: string;
  type: string;
  subtype?: string | null;
  lat?: number | null;
  lng?: number | null;
  source_count?: number;
  synthetic?: boolean;
};

export type ExplainabilityItem = {
  index: number;
  text: string;
  entity_id?: string;
  entity_name?: string;
  lat?: number | null;
  lng?: number | null;
  sources: SourceRef[];
};

export type NaturalPayload = {
  query: string;
  answer: string;
  answer_markdown?: string;
  citations: Citation[];
  entities_used: Array<{ id: string; name: string; type: string }>;
  mentioned_entities?: MentionedEntity[];
  explainability?: ExplainabilityItem[];
};

export type Property = {
  key: string;
  value: string;
  confidence?: number;
  origins?: string[];
};

export type SearchEntity = {
  id: string;
  name: string;
  entity_type: string;
  subtype?: string | null;
  score?: number | null;
  importance?: number | null;
  properties?: Property[];
  geography?: { neighborhood?: string | null; commune?: string | null };
};

export type Geography = {
  name: string;
  slug: string;
  level: "city" | "commune" | "neighborhood";
  commune: number | null;
};

export type GeographiesPayload = {
  city: Geography;
  communes: Geography[];
  neighborhoods: Geography[];
};

export type SearchPayload = {
  query: string;
  results: SearchEntity[];
};

export type Phase = "idle" | "loading" | "answered" | "error";
