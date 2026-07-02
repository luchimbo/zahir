-- ============================================================
-- 11_query_log.sql
-- Radar de demanda: registra consultas y gaps de cobertura.
-- ============================================================

CREATE TABLE IF NOT EXISTS query_log (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text            text,
    query_mode            text NOT NULL CHECK (query_mode IN ('search', 'query', 'entity_search', 'retrieve_entity')),
    entity_type           text,
    subtype               text,
    tag                   text,
    result_count          integer NOT NULL DEFAULT 0 CHECK (result_count >= 0),
    entity_types_returned text[] DEFAULT '{}',
    is_gap                boolean GENERATED ALWAYS AS (result_count = 0) STORED,
    source                text DEFAULT 'api',
    created_at            timestamp DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_log_created_at_idx
    ON query_log(created_at DESC);

CREATE INDEX IF NOT EXISTS query_log_is_gap_idx
    ON query_log(is_gap, created_at DESC);

CREATE INDEX IF NOT EXISTS query_log_query_mode_idx
    ON query_log(query_mode);

CREATE INDEX IF NOT EXISTS query_log_query_text_trgm_idx
    ON query_log USING GIN(query_text gin_trgm_ops);
