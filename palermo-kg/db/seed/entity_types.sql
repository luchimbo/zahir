-- ============================================================
-- seed/entity_types.sql
-- Tipos de entidad iniciales del sistema.
-- Para agregar uno nuevo: INSERT aquí + documentar en RULES.md
-- ============================================================

INSERT INTO entity_types (name, description) VALUES
    ('Location',        'Barrios, zonas, subzonas geográficas de Palermo'),
    ('Facility',        'Parques, museos, plazas, espacios públicos'),
    ('Organization',    'Comercios, restaurantes, bares, servicios, empresas'),
    ('Property',        'Inmuebles en alquiler o venta'),
    ('Event',           'Eventos, ferias, recitales, exposiciones'),
    ('Transport',       'Líneas de subte, colectivos, paradas, estaciones'),
    ('LegalEntity',     'Sociedades registradas en IGJ (SA, SRL, SAS)'),
    ('Trademark',       'Marcas registradas en INPI'),
    ('LegalCase',       'Expedientes judiciales del Poder Judicial CABA'),
    ('Parcel',          'Parcelas catastrales de ARBA/AGIP'),
    ('HistoricalRecord','Registros históricos del IHCBA y Archivo General de la Nación'),
    ('MarketIndex',     'Índices bursátiles (MERVAL, S&P BYMA, etc.)'),
    ('Security',        'Especies negociables listadas (acciones, ADRs)'),
    ('EconomicSeries',  'Series estadísticas oficiales (BCRA, INDEC)'),
    ('Regulation',      'Normativa y comunicaciones de organismos nacionales (BCRA, etc.)')
ON CONFLICT (name) DO NOTHING;
