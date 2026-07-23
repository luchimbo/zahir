-- Hechos repetibles de IGJ: no reemplazan propiedades vigentes de la entidad.
CREATE TABLE IF NOT EXISTS legal_entity_records (
  id CHAR(36) PRIMARY KEY,
  entity_id CHAR(36) NOT NULL,
  source_id CHAR(36) NOT NULL,
  record_type VARCHAR(30) NOT NULL,
  record_key CHAR(64) NOT NULL,
  observed_period VARCHAR(20) NOT NULL,
  event_date DATE NULL,
  payload JSON NOT NULL,
  origins JSON NULL,
  first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT legal_records_entity_fk FOREIGN KEY (entity_id) REFERENCES entities(id),
  CONSTRAINT legal_records_source_fk FOREIGN KEY (source_id) REFERENCES sources(id),
  CONSTRAINT legal_records_type CHECK (record_type IN ('domicile','authority','assembly','balance')),
  UNIQUE KEY legal_records_source_key (source_id, record_key)
);
CREATE INDEX legal_records_entity_type_idx ON legal_entity_records(entity_id, record_type, observed_period);
CREATE INDEX legal_records_type_period_idx ON legal_entity_records(record_type, observed_period);
