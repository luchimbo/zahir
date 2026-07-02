-- ============================================================
-- 02_sources.sql
-- Fuentes de datos del sistema. Toda propiedad y relación
-- debe tener una fuente trazable.
--
-- REGLAS:
--   - source_name siempre snake_case (ej: "ba_data", "zonaprop")
--   - tier define la confiabilidad de la fuente:
--       1 = API nativa oficial (BA Data, GCBA)
--       2 = Scraping estructurado (Zonaprop, Google Places, IGJ)
--       3 = PDF / extracción LLM (Boletín Oficial, Judicial)
--       4 = Carga manual / histórica (IHCBA, AGN)
--   - nunca eliminar una fuente (puede tener propiedades históricas)
--   - actualizar scraped_at cada vez que el scraper corre exitosamente
-- ============================================================

CREATE TABLE sources (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name text UNIQUE NOT NULL,
    source_url  text,
    tier        smallint NOT NULL CHECK (tier BETWEEN 1 AND 4),
    is_reliable boolean DEFAULT true,
    scraped_at  timestamp,
    created_at  timestamp DEFAULT now()
);
