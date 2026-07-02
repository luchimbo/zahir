-- ============================================================
-- 05_relationships.sql
-- Relaciones entre entidades del grafo.
--
-- REGLAS:
--   - from_entity_id → relationship_type → to_entity_id
--   - no se permiten relaciones de una entidad consigo misma (constraint)
--   - relationship_type debe ser uno de los valores del CHECK.
--     Para agregar un tipo nuevo: modificar el CHECK + documentar en RULES.md
--   - direction 'directed' = A→B (default)
--                'bidirectional' = A↔B (ej: NEAR)
--   - confidence: igual que en properties (0.5 = 1 fuente, 1.0 = 3+)
--   - al insertar una relación, el trigger actualiza nb_incoming_edges en entities
--   - al eliminar una relación, el trigger decrementa nb_incoming_edges
--
-- Tipos de relación disponibles:
--   LOCATED_IN   → entidad está ubicada en un lugar (restaurante en Palermo Soho)
--   NEAR         → entidad está cerca de otra (bidirectional)
--   BELONGS_TO   → entidad pertenece a otra (sucursal → empresa madre)
--   OFFERS       → entidad ofrece algo (restaurante → tipo de cocina)
--   CONNECTS_TO  → transporte conecta puntos
--   OWNED_BY     → entidad es propiedad de otra (local → persona/empresa)
--   PART_OF      → componente de un todo (subbarrio → barrio)
--   RELATED_TO   → relación genérica cuando no aplica otra
-- ============================================================

CREATE TABLE relationships (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type text NOT NULL,
    to_entity_id      uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    weight            numeric DEFAULT 1.0,
    confidence        numeric(3,2) DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    origins           text[] DEFAULT '{}',
    direction         text DEFAULT 'directed' CHECK (direction IN ('directed','bidirectional')),
    created_at        timestamp DEFAULT now(),

    CONSTRAINT no_self_relationship CHECK (from_entity_id != to_entity_id),
    CONSTRAINT valid_relationship_type CHECK (relationship_type IN (
        'LOCATED_IN', 'NEAR', 'BELONGS_TO', 'OFFERS',
        'CONNECTS_TO', 'OWNED_BY', 'PART_OF', 'RELATED_TO'
    ))
);
