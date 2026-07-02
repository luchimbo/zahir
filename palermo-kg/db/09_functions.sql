-- ============================================================
-- 09_functions.sql
-- Funciones helper reutilizables en scrapers, API y jobs.
-- ============================================================

-- Calcula el confidence score según número de fuentes que confirman un valor.
-- Usar esta función en los scrapers al insertar/actualizar properties.
CREATE OR REPLACE FUNCTION calc_confidence(nb_sources integer)
RETURNS numeric(3,2) AS $$
BEGIN
    RETURN CASE
        WHEN nb_sources >= 3 THEN 1.00
        WHEN nb_sources = 2  THEN 0.75
        ELSE                      0.50
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;


-- Recalcula el importance score de una entidad basado en nb_incoming_edges.
-- Se llama desde el job nocturno de mantenimiento.
-- importance = MIN(100, nb_incoming_edges * 2)  (ajustar factor según datos reales)
CREATE OR REPLACE FUNCTION recalc_importance(entity_id uuid)
RETURNS void AS $$
BEGIN
    UPDATE entities
    SET importance = LEAST(100, nb_incoming_edges * 2)
    WHERE id = entity_id;
END;
$$ LANGUAGE plpgsql;


-- Recalcula importance para todas las entidades activas.
-- Ejecutar como job nocturno.
CREATE OR REPLACE FUNCTION recalc_all_importance()
RETURNS void AS $$
BEGIN
    UPDATE entities
    SET importance = LEAST(100, nb_incoming_edges * 2)
    WHERE is_active = true AND canonical_id IS NULL;
END;
$$ LANGUAGE plpgsql;


-- Busca entidades por nombre con soporte fuzzy (pg_trgm).
-- Devuelve entidades canónicas activas ordenadas por similitud.
CREATE OR REPLACE FUNCTION search_entities(query text, max_results integer DEFAULT 10)
RETURNS TABLE(id uuid, name text, entity_type text, subtype text, similarity real) AS $$
BEGIN
    RETURN QUERY
    SELECT e.id, e.name, e.entity_type, e.subtype,
           similarity(e.name, query) AS similarity
    FROM entities e
    WHERE e.is_active = true
      AND e.canonical_id IS NULL
      AND (e.name % query OR e.name ILIKE '%' || query || '%')
    ORDER BY similarity DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;


-- Cierra una propiedad activa (setea valid_until = hoy).
-- Usar en scrapers cuando el valor de una propiedad cambió.
CREATE OR REPLACE FUNCTION close_property(prop_id uuid)
RETURNS void AS $$
BEGIN
    UPDATE properties
    SET valid_until = CURRENT_DATE
    WHERE id = prop_id AND valid_until IS NULL;
END;
$$ LANGUAGE plpgsql;
