-- Esquema TiDB/MySQL 8 idempotente para Palermo Knowledge Graph.
CREATE TABLE IF NOT EXISTS entity_types (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sources (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), source_name VARCHAR(120) NOT NULL UNIQUE,
  source_url TEXT, tier TINYINT NOT NULL, is_reliable BOOLEAN NOT NULL DEFAULT TRUE,
  scraped_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT sources_tier CHECK (tier BETWEEN 1 AND 4)
);
CREATE TABLE IF NOT EXISTS entities (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), name VARCHAR(500) NOT NULL,
  all_names JSON NULL, entity_type VARCHAR(100) NOT NULL, types JSON NULL,
  subtype VARCHAR(150) NULL, description TEXT NULL, lat DECIMAL(10,7) NULL,
  lng DECIMAL(10,7) NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
  importance SMALLINT NOT NULL DEFAULT 0, nb_incoming_edges INT NOT NULL DEFAULT 0,
  canonical_id CHAR(36) NULL, classifier_model VARCHAR(200) NULL,
  classifier_confidence DECIMAL(3,2) NULL, origin_url TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT entities_type_fk FOREIGN KEY (entity_type) REFERENCES entity_types(name),
  CONSTRAINT entities_canonical_fk FOREIGN KEY (canonical_id) REFERENCES entities(id),
  CONSTRAINT entities_importance CHECK (importance BETWEEN 0 AND 100),
  CONSTRAINT entities_coordinates CHECK ((lat IS NULL AND lng IS NULL) OR (lat IS NOT NULL AND lng IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS properties (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), entity_id CHAR(36) NOT NULL,
  `key` VARCHAR(150) NOT NULL, value TEXT NOT NULL, value_type VARCHAR(20) NOT NULL,
  valid_from DATE NULL, valid_until DATE NULL, confidence DECIMAL(3,2) NOT NULL DEFAULT 0.50,
  origins JSON NULL, last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source_id CHAR(36) NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT properties_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id),
  CONSTRAINT properties_source_fk FOREIGN KEY (source_id) REFERENCES sources(id),
  CONSTRAINT properties_value_type CHECK (value_type IN ('string','number','boolean','date','url','json')),
  CONSTRAINT properties_dates CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until)
);
CREATE TABLE IF NOT EXISTS relationships (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), from_entity_id CHAR(36) NOT NULL,
  relationship_type VARCHAR(50) NOT NULL, to_entity_id CHAR(36) NOT NULL,
  weight DECIMAL(10,4) NOT NULL DEFAULT 1.0, confidence DECIMAL(3,2) NOT NULL DEFAULT 0.50,
  origins JSON NULL, direction VARCHAR(20) NOT NULL DEFAULT 'directed',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT relationships_from_fk FOREIGN KEY (from_entity_id) REFERENCES entities(id),
  CONSTRAINT relationships_to_fk FOREIGN KEY (to_entity_id) REFERENCES entities(id),
  CONSTRAINT relationships_no_self CHECK (from_entity_id <> to_entity_id),
  CONSTRAINT relationships_direction CHECK (direction IN ('directed','bidirectional'))
);
CREATE TABLE IF NOT EXISTS tags (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), entity_id CHAR(36) NOT NULL, tag VARCHAR(100) NOT NULL,
  CONSTRAINT tags_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id), UNIQUE KEY tags_entity_tag (entity_id, tag)
);
CREATE TABLE IF NOT EXISTS query_log (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), query_text TEXT NULL,
  query_mode VARCHAR(30) NOT NULL, entity_type VARCHAR(100) NULL, subtype VARCHAR(150) NULL,
  tag VARCHAR(100) NULL, result_count INT NOT NULL DEFAULT 0, entity_types_returned JSON NULL,
  is_gap BOOLEAN AS (result_count = 0) STORED, source VARCHAR(100) NOT NULL DEFAULT 'api',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_sync_runs (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), source_id CHAR(36) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'running', started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL, records_seen INT NOT NULL DEFAULT 0, records_written INT NOT NULL DEFAULT 0,
  error_message TEXT NULL,
  CONSTRAINT sync_runs_source_fk FOREIGN KEY (source_id) REFERENCES sources(id),
  CONSTRAINT sync_runs_status CHECK (status IN ('running','completed','partial','failed'))
);
CREATE TABLE IF NOT EXISTS external_ids (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()), entity_id CHAR(36) NOT NULL, source_id CHAR(36) NOT NULL,
  external_id VARCHAR(500) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT external_ids_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id),
  CONSTRAINT external_ids_source_fk FOREIGN KEY (source_id) REFERENCES sources(id),
  UNIQUE KEY external_ids_source_value (source_id, external_id)
);
CREATE TABLE IF NOT EXISTS source_policies (
  source_id CHAR(36) PRIMARY KEY, data_class VARCHAR(30) NOT NULL DEFAULT 'current',
  refresh_schedule VARCHAR(40) NOT NULL DEFAULT 'manual', access_mode VARCHAR(30) NOT NULL DEFAULT 'public',
  cost_policy VARCHAR(20) NOT NULL DEFAULT 'free', enabled BOOLEAN NOT NULL DEFAULT TRUE,
  license_url TEXT NULL, terms_url TEXT NULL, permitted_fields JSON NULL, retention_days INT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT policies_source_fk FOREIGN KEY (source_id) REFERENCES sources(id)
);
CREATE TABLE IF NOT EXISTS source_checkpoints (
  source_id CHAR(36) PRIMARY KEY, cursor_value TEXT NULL, content_hash CHAR(64) NULL,
  last_heartbeat_at TIMESTAMP NULL, next_attempt_at TIMESTAMP NULL, retry_count INT NOT NULL DEFAULT 0,
  last_error_code VARCHAR(100) NULL, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT checkpoints_source_fk FOREIGN KEY (source_id) REFERENCES sources(id)
);
CREATE TABLE IF NOT EXISTS source_run_metrics (
  run_id CHAR(36) PRIMARY KEY, coverage JSON NULL, extractor_version VARCHAR(80) NULL,
  error_code VARCHAR(100) NULL, checkpoint_after TEXT NULL, content_hash CHAR(64) NULL,
  CONSTRAINT metrics_run_fk FOREIGN KEY (run_id) REFERENCES source_sync_runs(id)
);
CREATE INDEX IF NOT EXISTS entities_filters_idx ON entities(entity_type, subtype, is_active, canonical_id);
CREATE INDEX IF NOT EXISTS entities_coordinates_idx ON entities(lat, lng);
CREATE INDEX IF NOT EXISTS entities_name_idx ON entities(name);
CREATE INDEX IF NOT EXISTS properties_entity_key_idx ON properties(entity_id, `key`, valid_until);
CREATE INDEX IF NOT EXISTS properties_source_idx ON properties(source_id);
CREATE INDEX IF NOT EXISTS tags_tag_idx ON tags(tag);
CREATE INDEX IF NOT EXISTS relationships_from_idx ON relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS relationships_to_idx ON relationships(to_entity_id);
CREATE UNIQUE INDEX IF NOT EXISTS relationships_identity_idx ON relationships(from_entity_id, relationship_type, to_entity_id);
CREATE INDEX IF NOT EXISTS query_log_created_idx ON query_log(created_at);
CREATE INDEX IF NOT EXISTS source_sync_runs_source_idx ON source_sync_runs(source_id, started_at);
CREATE INDEX IF NOT EXISTS external_ids_entity_idx ON external_ids(entity_id);
CREATE INDEX IF NOT EXISTS checkpoints_retry_idx ON source_checkpoints(next_attempt_at, retry_count);
CREATE OR REPLACE VIEW active_properties AS
SELECT * FROM properties WHERE valid_until IS NULL OR valid_until > CURRENT_DATE();
INSERT IGNORE INTO entity_types (name, description) VALUES
('Location','Barrios y zonas'),('Facility','Espacios y equipamientos'),('Organization','Comercios y organizaciones'),
('Property','Inmuebles'),('Event','Eventos'),('Transport','Transporte'),('LegalEntity','Sociedades'),
('Trademark','Marcas'),('LegalCase','Causas judiciales'),('Parcel','Parcelas'),('HistoricalRecord','Registros históricos');
INSERT IGNORE INTO sources (source_name, source_url, tier) VALUES
('ba_data','https://data.buenosaires.gob.ar',1),('gcba_wfs','https://epok.buenosaires.gob.ar/etl/wfs/',1),
('google_places','https://maps.googleapis.com/maps/api/place',2),('agenda_gcba','https://turismo.buenosaires.gob.ar/agenda',2),
('igj','https://www.igj.gob.ar',2),('inpi','https://www.inpi.gob.ar',2),
('boletin_oficial','https://boletinoficial.buenosaires.gob.ar',3),('osm','https://www.openstreetmap.org',1),
('wikidata','https://www.wikidata.org',1);
