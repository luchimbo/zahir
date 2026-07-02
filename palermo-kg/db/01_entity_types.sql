-- ============================================================
-- 01_entity_types.sql
-- Catálogo de tipos de entidad del knowledge graph.
--
-- REGLAS:
--   - name siempre en PascalCase (ej: "Organization", no "organization")
--   - nunca eliminar un tipo que tenga entidades asociadas
--     (la FK en entities.entity_type lo garantiza con ON UPDATE CASCADE)
--   - para agregar un tipo nuevo: INSERT aquí + documentar en RULES.md
-- ============================================================

CREATE TABLE entity_types (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL,
    description text,
    created_at  timestamp DEFAULT now()
);
