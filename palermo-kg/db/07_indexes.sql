-- ============================================================
-- 07_indexes.sql
-- Índices para performance en queries frecuentes.
-- Ejecutar después de crear todas las tablas.
-- ============================================================

-- entities: filtros frecuentes
CREATE INDEX ON entities(entity_type);
CREATE INDEX ON entities(subtype);
CREATE INDEX ON entities(is_active);
CREATE INDEX ON entities(canonical_id);         -- detectar/excluir duplicados

-- entities: arrays (GIN para operadores @>, &&, etc.)
CREATE INDEX ON entities USING GIN(all_names);
CREATE INDEX ON entities USING GIN(types);

-- entities: búsqueda fuzzy por nombre (pg_trgm — requiere 00_extensions)
CREATE INDEX ON entities USING GIN(name gin_trgm_ops);

-- entities: queries geográficas de proximidad
CREATE INDEX ON entities(lat, lng) WHERE lat IS NOT NULL;

-- properties: acceso por entidad + clave
CREATE INDEX ON properties(entity_id, key);
CREATE INDEX ON properties(entity_id, valid_until);   -- filtrar propiedades activas
CREATE INDEX ON properties(source_id);

-- tags
CREATE INDEX ON tags(entity_id);
CREATE INDEX ON tags(tag);

-- relationships: traversal del grafo
CREATE INDEX ON relationships(from_entity_id);
CREATE INDEX ON relationships(to_entity_id);
CREATE INDEX ON relationships(relationship_type);
