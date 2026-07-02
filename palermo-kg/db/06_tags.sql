-- ============================================================
-- 06_tags.sql
-- Tags libres para clasificación flexible de entidades.
--
-- REGLAS:
--   - tag siempre lowercase (constraint lo garantiza)
--   - tag sin espacios; usar guión para separar palabras: "pet-friendly", "sin-tacc"
--   - no se puede repetir el mismo tag en la misma entidad (UNIQUE lo garantiza)
--   - se eliminan automáticamente si se elimina la entidad (ON DELETE CASCADE)
-- ============================================================

CREATE TABLE tags (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    tag       text NOT NULL,

    CONSTRAINT tag_format CHECK (tag = lower(tag) AND tag NOT LIKE '% %'),
    UNIQUE (entity_id, tag)
);
