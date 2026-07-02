-- ============================================================
-- init.sql
-- Script de inicialización completo del Knowledge Graph Palermo.
-- Ejecutar este archivo UNA SOLA VEZ al crear la base de datos en Neon.
--
-- Cómo usarlo:
--   1. En la consola SQL de Neon: copiar y pegar todo este contenido
--   2. O via psql: psql "<connection-string>" -f init.sql
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- 00 EXTENSIONS
-- ────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";


-- ────────────────────────────────────────────────────────────
-- 01 ENTITY TYPES
-- REGLA: name siempre PascalCase. Nunca eliminar si tiene entidades.
-- ────────────────────────────────────────────────────────────

CREATE TABLE entity_types (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text UNIQUE NOT NULL,
    description text,
    created_at  timestamp DEFAULT now()
);


-- ────────────────────────────────────────────────────────────
-- 02 SOURCES
-- REGLA: source_name siempre snake_case.
-- REGLA: tier 1=API oficial | 2=scraping | 3=PDF+LLM | 4=manual
-- ────────────────────────────────────────────────────────────

CREATE TABLE sources (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name text UNIQUE NOT NULL,
    source_url  text,
    tier        smallint NOT NULL CHECK (tier BETWEEN 1 AND 4),
    is_reliable boolean DEFAULT true,
    scraped_at  timestamp,
    created_at  timestamp DEFAULT now()
);


-- ────────────────────────────────────────────────────────────
-- 03 ENTITIES
-- REGLA: canonical_id NULL = canónica (usar en queries).
-- REGLA: canonical_id != NULL = duplicado (ignorar en queries normales).
-- REGLA: nunca eliminar; usar is_active = false.
-- REGLA: lat y lng siempre ambos o ninguno.
-- ────────────────────────────────────────────────────────────

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


-- ────────────────────────────────────────────────────────────
-- 04 PROPERTIES (EAV)
-- REGLA: key siempre snake_case.
-- REGLA: nunca eliminar; cerrar con valid_until cuando el valor cambia.
-- REGLA: confidence = calc_confidence(nb_fuentes).
-- ────────────────────────────────────────────────────────────

CREATE TABLE properties (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id    uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    key          text NOT NULL,
    value        text NOT NULL,
    value_type   text NOT NULL CHECK (value_type IN ('string','number','boolean','date','url','json')),
    valid_from   date,
    valid_until  date,
    confidence   numeric(3,2) DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    origins      text[] DEFAULT '{}',
    last_seen_at timestamp DEFAULT now(),
    source_id    uuid REFERENCES sources(id),
    created_at   timestamp DEFAULT now(),

    CONSTRAINT valid_dates CHECK (
        valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until
    )
);

CREATE VIEW active_properties AS
SELECT * FROM properties
WHERE valid_until IS NULL OR valid_until > CURRENT_DATE;


-- ────────────────────────────────────────────────────────────
-- 05 RELATIONSHIPS
-- REGLA: no self-relationships.
-- REGLA: para agregar tipo nuevo: ALTER TABLE + documentar en RULES.md.
-- ────────────────────────────────────────────────────────────

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


-- ────────────────────────────────────────────────────────────
-- 06 TAGS
-- REGLA: siempre lowercase, sin espacios, usar guión: "pet-friendly"
-- ────────────────────────────────────────────────────────────

CREATE TABLE tags (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id uuid NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    tag       text NOT NULL,

    CONSTRAINT tag_format CHECK (tag = lower(tag) AND tag NOT LIKE '% %'),
    UNIQUE (entity_id, tag)
);


-- ────────────────────────────────────────────────────────────
-- 07 INDEXES
-- ────────────────────────────────────────────────────────────

CREATE INDEX ON entities(entity_type);
CREATE INDEX ON entities(subtype);
CREATE INDEX ON entities(is_active);
CREATE INDEX ON entities(canonical_id);
CREATE INDEX ON entities USING GIN(all_names);
CREATE INDEX ON entities USING GIN(types);
CREATE INDEX ON entities USING GIN(name gin_trgm_ops);
CREATE INDEX ON entities(lat, lng) WHERE lat IS NOT NULL;

CREATE INDEX ON properties(entity_id, key);
CREATE INDEX ON properties(entity_id, valid_until);
CREATE INDEX ON properties(source_id);

CREATE INDEX ON tags(entity_id);
CREATE INDEX ON tags(tag);

CREATE INDEX ON relationships(from_entity_id);
CREATE INDEX ON relationships(to_entity_id);
CREATE INDEX ON relationships(relationship_type);


-- ────────────────────────────────────────────────────────────
-- 09 FUNCTIONS
-- ────────────────────────────────────────────────────────────

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


CREATE OR REPLACE FUNCTION recalc_all_importance()
RETURNS void AS $$
BEGIN
    UPDATE entities
    SET importance = LEAST(100, nb_incoming_edges * 2)
    WHERE is_active = true AND canonical_id IS NULL;
END;
$$ LANGUAGE plpgsql;


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


CREATE OR REPLACE FUNCTION close_property(prop_id uuid)
RETURNS void AS $$
BEGIN
    UPDATE properties
    SET valid_until = CURRENT_DATE
    WHERE id = prop_id AND valid_until IS NULL;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────
-- 10 TRIGGERS
-- ────────────────────────────────────────────────────────────

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


CREATE OR REPLACE FUNCTION update_nb_incoming_edges()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE entities SET nb_incoming_edges = nb_incoming_edges + 1
        WHERE id = NEW.to_entity_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE entities SET nb_incoming_edges = GREATEST(nb_incoming_edges - 1, 0)
        WHERE id = OLD.to_entity_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER relationships_edge_count
AFTER INSERT OR DELETE ON relationships
FOR EACH ROW EXECUTE FUNCTION update_nb_incoming_edges();


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


-- ────────────────────────────────────────────────────────────
-- SEED: entity_types
-- ────────────────────────────────────────────────────────────

INSERT INTO entity_types (name, description) VALUES
    ('Location',         'Barrios, zonas, subzonas geográficas de Palermo'),
    ('Facility',         'Parques, museos, plazas, espacios públicos'),
    ('Organization',     'Comercios, restaurantes, bares, servicios, empresas'),
    ('Property',         'Inmuebles en alquiler o venta'),
    ('Event',            'Eventos, ferias, recitales, exposiciones'),
    ('Transport',        'Líneas de subte, colectivos, paradas, estaciones'),
    ('LegalEntity',      'Sociedades registradas en IGJ (SA, SRL, SAS)'),
    ('Trademark',        'Marcas registradas en INPI'),
    ('LegalCase',        'Expedientes judiciales del Poder Judicial CABA'),
    ('Parcel',           'Parcelas catastrales de ARBA/AGIP'),
    ('HistoricalRecord', 'Registros históricos del IHCBA y Archivo General de la Nación')
ON CONFLICT (name) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- SEED: sources
-- ────────────────────────────────────────────────────────────

INSERT INTO sources (source_name, source_url, tier) VALUES
    ('ba_data',         'https://data.buenosaires.gob.ar',            1),
    ('gcba_wfs',        'https://epok.buenosaires.gob.ar/etl/wfs/',   1),
    ('zonaprop',        'https://www.zonaprop.com.ar',                2),
    ('argenprop',       'https://www.argenprop.com',                   2),
    ('google_places',   'https://maps.googleapis.com/maps/api/place',  2),
    ('agenda_gcba',     'https://turismo.buenosaires.gob.ar/agenda',   2),
    ('igj',             'https://www.igj.gob.ar',                     2),
    ('inpi',            'https://www.inpi.gob.ar',                    2),
    ('arba',            'https://www.arba.gob.ar',                    2),
    ('agip',            'https://www.agip.gob.ar',                    2),
    ('boletin_oficial', 'https://boletinoficial.buenosaires.gob.ar',   3),
    ('poder_judicial',  'https://www.jusbaires.gob.ar',               3),
    ('ihcba',           'https://www.buenosaires.gob.ar/ihcba',       3),
    ('agn',             'https://www.argentina.gob.ar/interior/agn',  4),
    ('mapoteca_gcba',   'https://www.buenosaires.gob.ar/mapoteca',    4)
ON CONFLICT (source_name) DO NOTHING;


-- ────────────────────────────────────────────────────────────
-- VERIFICACIÓN FINAL
-- Debería mostrar las tablas creadas y los seeds insertados.
-- ────────────────────────────────────────────────────────────

SELECT 'entity_types' AS tabla, COUNT(*) AS registros FROM entity_types
UNION ALL
SELECT 'sources',    COUNT(*) FROM sources
UNION ALL
SELECT 'entities',   COUNT(*) FROM entities
UNION ALL
SELECT 'properties', COUNT(*) FROM properties
UNION ALL
SELECT 'relationships', COUNT(*) FROM relationships
UNION ALL
SELECT 'tags',       COUNT(*) FROM tags;
