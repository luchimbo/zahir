-- ============================================================
-- seed/sources.sql
-- Fuentes de datos iniciales del sistema.
-- tier: 1=API oficial | 2=scraping | 3=PDF+LLM | 4=manual
-- ============================================================

INSERT INTO sources (source_name, source_url, tier) VALUES
    -- Tier 1: APIs nativas oficiales
    ('ba_data',          'https://data.buenosaires.gob.ar',           1),
    ('gcba_wfs',         'https://epok.buenosaires.gob.ar/etl/wfs/',  1),

    -- Tier 2: Scraping estructurado
    ('zonaprop',         'https://www.zonaprop.com.ar',               2),
    ('argenprop',        'https://www.argenprop.com',                  2),
    ('google_places',    'https://maps.googleapis.com/maps/api/place', 2),
    ('agenda_gcba',      'https://turismo.buenosaires.gob.ar/agenda',  2),
    ('igj',              'https://www.igj.gob.ar',                    2),
    ('inpi',             'https://www.inpi.gob.ar',                   2),
    ('arba',             'https://www.arba.gob.ar',                   2),
    ('agip',             'https://www.agip.gob.ar',                   2),

    -- Tier 3: PDFs y documentos con extracción LLM
    ('boletin_oficial',  'https://boletinoficial.buenosaires.gob.ar',  3),
    ('poder_judicial',   'https://www.jusbaires.gob.ar',              3),
    ('ihcba',            'https://www.buenosaires.gob.ar/ihcba',      3),

    -- Tier 4: Archivos históricos / carga manual
    ('agn',              'https://www.argentina.gob.ar/interior/agn', 4),
    ('mapoteca_gcba',    'https://www.buenosaires.gob.ar/mapoteca',   4)

ON CONFLICT (source_name) DO NOTHING;

INSERT INTO sources (source_name, source_url, tier) VALUES
    ('refes_historical', 'https://datos.gob.ar/dataset/salud-listado-establecimientos-salud-asentados-registro-federal-refes', 4),
    ('transporte_rmba', 'https://datos.gob.ar/dataset/transporte-recorridos-lineas-transporte-region-metropolitana-buenos-aires-rmba', 4),
    ('cep_xxi', 'https://datos.gob.ar/dataset/produccion-distribucion-geografica-establecimientos-productivos', 4),
    ('enacom_context', 'https://datos.gob.ar/dataset?organization=enacom', 4),
    ('ceamse_context', 'https://portal-andino.datos.gob.ar/dataset/residuos-solidos-urbanos', 4),
    ('national_monuments', 'https://www.argentina.gob.ar/cultura/monumentos', 4)
ON CONFLICT (source_name) DO NOTHING;

-- Fuentes nacionales y geoespaciales (ronda 3)
INSERT INTO sources (source_name, source_url, tier) VALUES
    ('georef', 'https://apis.datos.gob.ar/georef/api/v2.0', 1),
    ('padron_educativo', 'https://www.argentina.gob.ar/node/246613', 1),
    ('indec_censo', 'https://geonode.indec.gob.ar', 1),
    ('ign', 'https://www.ign.gob.ar/NuestrasActividades/InformacionGeoespacial/ServiciosOGC', 1),
    ('sinca', 'https://datos.gob.ar/dataset/cultura-mapa-cultural-espacios-culturales', 4),
    ('refes', 'https://www.argentina.gob.ar/salud', 1)
ON CONFLICT (source_name) DO NOTHING;

-- Nuevas fuentes — ronda 2
INSERT INTO sources (source_name, source_url, tier) VALUES
    -- Tier 1: APIs libres / datasets abiertos
    ('osm',                'https://www.openstreetmap.org',              1),
    ('wikidata',           'https://www.wikidata.org',                   1),
    ('bcra',               'https://www.bcra.gob.ar',                    1),
    ('enacom',             'https://www.enacom.gob.ar',                  1),
    ('indec',              'https://www.indec.gob.ar',                   1),
    ('anmat',              'https://www.anmat.gov.ar',                   1),
    ('afip',               'https://www.afip.gob.ar',                    1),
    ('cnv',                'https://www.cnv.gob.ar',                     1),
    ('inside_airbnb',      'https://insideairbnb.com',                   1),
    ('smn',                'https://www.smn.gob.ar',                     1),
    ('apra',               'https://buenosaires.gob.ar/apra',            1),
    ('acumar',             'https://www.acumar.gob.ar',                  1),
    ('mapa_delito',        'https://mapa.buenosaires.gob.ar/delito',     1),

    -- Tier 2: Scraping estructurado
    ('tripadvisor',        'https://www.tripadvisor.com.ar',             2),
    ('guia_oleo',          'https://www.guiaoleo.com.ar',                2),
    ('alternativa_teatral','https://www.alternativateatral.com',         2),
    ('eventbrite',         'https://www.eventbrite.com.ar',              2),
    ('pedidosya',          'https://www.pedidosya.com.ar',               2),
    ('rappi',              'https://www.rappi.com.ar',                   2),
    ('mercadolibre',       'https://www.mercadolibre.com.ar',            2),
    ('doctoralia',         'https://www.doctoralia.com.ar',              2),
    ('timeout_ba',         'https://www.timeoutbuenosaires.com',         2),
    ('booking',            'https://www.booking.com',                    2),
    ('crunchbase',         'https://www.crunchbase.com',                 2),
    ('clutch',             'https://clutch.co',                          2),
    ('rapipago',           'https://www.rapipago.com.ar',                2),
    ('reddit',             'https://www.reddit.com/r/buenosaires',       2),
    ('youtube',            'https://www.youtube.com',                    2)

ON CONFLICT (source_name) DO NOTHING;
