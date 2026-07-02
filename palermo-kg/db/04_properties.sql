-- ============================================================
-- 04_properties.sql
-- Propiedades dinámicas de las entidades (patrón EAV).
-- Permite agregar cualquier atributo sin modificar el schema.
--
-- REGLAS:
--   - key siempre snake_case (ej: price_usd, hours_open, rating)
--   - value siempre texto; usar value_type para interpretar correctamente
--   - nunca eliminar propiedades; cerrar con valid_until = hoy cuando cambian
--   - valid_from <= valid_until cuando ambos presentes (constraint lo garantiza)
--   - confidence: cuántas fuentes confirman este valor
--       0.5 = 1 fuente
--       0.75 = 2 fuentes
--       1.0 = 3 o más fuentes
--   - origins: array de URLs que confirman este valor
--   - last_seen_at: actualizar cada vez que el scraper re-confirma el valor
--
-- UPSERT recomendado en scrapers:
--   Si existe (entity_id, key) con valid_until NULL y misma source_id:
--     → actualizar value, last_seen_at, origins
--   Si el valor cambió:
--     → cerrar el anterior con valid_until = hoy
--     → insertar nuevo registro
-- ============================================================

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

-- Vista: propiedades activas (sin fecha de vencimiento, o aún vigentes)
CREATE VIEW active_properties AS
SELECT * FROM properties
WHERE valid_until IS NULL OR valid_until > CURRENT_DATE;
