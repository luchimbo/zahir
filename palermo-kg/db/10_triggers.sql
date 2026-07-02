-- ============================================================
-- 10_triggers.sql
-- Triggers para mantener consistencia automática.
-- ============================================================

-- ─── updated_at automático en entities ───────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER entities_updated_at
BEFORE UPDATE ON entities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ─── nb_incoming_edges en entities ───────────────────────────
-- Se incrementa al insertar una relación.
-- Se decrementa al eliminar una relación.
-- Nunca baja de 0 (GREATEST protege contra negativos).

CREATE OR REPLACE FUNCTION update_nb_incoming_edges()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE entities
        SET nb_incoming_edges = nb_incoming_edges + 1
        WHERE id = NEW.to_entity_id;

    ELSIF TG_OP = 'DELETE' THEN
        UPDATE entities
        SET nb_incoming_edges = GREATEST(nb_incoming_edges - 1, 0)
        WHERE id = OLD.to_entity_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER relationships_edge_count
AFTER INSERT OR DELETE ON relationships
FOR EACH ROW EXECUTE FUNCTION update_nb_incoming_edges();


-- ─── last_seen_at automático en properties ────────────────────
-- Actualiza last_seen_at cada vez que se toca una propiedad.

CREATE OR REPLACE FUNCTION set_last_seen_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_seen_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER properties_last_seen
BEFORE UPDATE ON properties
FOR EACH ROW EXECUTE FUNCTION set_last_seen_at();
