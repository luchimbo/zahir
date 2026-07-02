-- ============================================================
-- 03_entities.sql
-- Tabla principal del knowledge graph.
-- Cada fila es una entidad del mundo real en Palermo.
--
-- REGLAS:
--   - canonical_id NULL = esta entidad es la versión canónica (usar en queries)
--   - canonical_id != NULL = esta entidad es un duplicado; ignorar en queries normales
--     El Entity Resolver asigna canonical_id antes de insertar duplicados.
--   - nunca eliminar entidades; usar is_active = false para "borrar" lógicamente
--   - lat y lng deben estar ambos presentes o ambos NULL (constraint lo garantiza)
--   - all_names: array con variantes del nombre para búsqueda y deduplicación
--     Ej: ["El Desnivel", "Desnivel Palermo", "Rest. El Desnivel"]
--   - types: array para entidades que pertenecen a múltiples tipos
--     Ej: ["Organization", "LegalEntity"]
--   - importance 0-100: se calcula con job nocturno basado en nb_incoming_edges
--   - nb_incoming_edges: se actualiza automáticamente via trigger en relationships
-- ============================================================

CREATE TABLE entities (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  text NOT NULL,
    all_names             text[] DEFAULT '{}',
    entity_type           text NOT NULL REFERENCES entity_types(name) ON UPDATE CASCADE,
    types                 text[] DEFAULT '{}',
    subtype               text,
    description           text,
    lat                   numeric(10,7),
    lng                   numeric(10,7),
    is_active             boolean DEFAULT true,
    importance            smallint DEFAULT 0 CHECK (importance BETWEEN 0 AND 100),
    nb_incoming_edges     integer DEFAULT 0 CHECK (nb_incoming_edges >= 0),
    canonical_id          uuid REFERENCES entities(id),
    classifier_model      text,
    classifier_confidence numeric(3,2) CHECK (classifier_confidence BETWEEN 0 AND 1),
    origin_url            text,
    created_at            timestamp DEFAULT now(),
    updated_at            timestamp DEFAULT now(),

    CONSTRAINT lat_lng_together CHECK (
        (lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL)
    ),
    CONSTRAINT no_self_reference CHECK (canonical_id != id)
);
