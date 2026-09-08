-- Serie temporal nacional/contextual: un punto por fecha, fuente y serie.
-- No reemplaza properties (estado vigente de una entidad) ni legal_entity_records
-- (hechos repetibles de IGJ). Ver db/RULES.md seccion 11.
--
-- TiDB no aplica CHECK por defecto (tidb_enable_check_constraint suele estar OFF);
-- la validacion de series_key, frequency y unit vive en scrapers/shared/db_helpers.py.
INSERT IGNORE INTO entity_types (name, description) VALUES
('MarketIndex','Indices bursatiles'),
('Security','Especies negociables listadas'),
('EconomicSeries','Series estadisticas oficiales'),
('Regulation','Normativa y comunicaciones de organismos nacionales');

CREATE TABLE IF NOT EXISTS observations (
  id CHAR(36) PRIMARY KEY,
  entity_id CHAR(36) NOT NULL,
  source_id CHAR(36) NOT NULL,
  series_key VARCHAR(150) NOT NULL,
  observed_at DATE NOT NULL,
  observed_period VARCHAR(20) NOT NULL,
  frequency VARCHAR(20) NOT NULL DEFAULT 'daily',
  value DECIMAL(38,10) NULL,
  value_text VARCHAR(255) NULL,
  unit VARCHAR(60) NULL,
  payload JSON NULL,
  origins JSON NULL,
  record_key CHAR(64) NOT NULL,
  confidence DECIMAL(3,2) NOT NULL DEFAULT 0.90,
  first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT observations_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id),
  CONSTRAINT observations_source_fk FOREIGN KEY (source_id) REFERENCES sources(id),
  UNIQUE KEY observations_identity (source_id, record_key)
);

CREATE INDEX observations_entity_series_idx ON observations(entity_id, series_key, observed_at);

CREATE INDEX observations_series_time_idx ON observations(series_key, observed_at);

CREATE INDEX observations_source_time_idx ON observations(source_id, observed_at);

-- Idempotente: ensancha `unit` si la tabla ya existía con la versión anterior
-- (VARCHAR(40) no alcanzaba para descripciones de unidad del BCRA, ej.
-- "Pesos argentinos por dólar estadounidense" = 41 caracteres).
ALTER TABLE observations MODIFY unit VARCHAR(60) NULL;
