"""Catálogo operativo: una única fuente de verdad para conectores del KG."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    name: str
    module: str
    url: str
    tier: int
    mode: str  # public | credential | approval
    description: str
    env_key: str | None = None
    args: tuple[str, ...] = ()
    data_class: str = "current"  # current | historical | aggregate | contextual
    refresh_schedule: str = "monthly"
    cost_policy: str = "free"  # free | paid | approval
    license_url: str | None = None


SOURCES = (
    SourceSpec("ba_data", "scrapers.gcba_ba_data", "https://data.buenosaires.gob.ar", 1, "public", "Barrios, espacios verdes y subte", refresh_schedule="daily"),
    SourceSpec("ba_data_extended", "scrapers.gcba_extended", "https://data.buenosaires.gob.ar", 1, "public", "Salud, bibliotecas y equipamiento"),
    SourceSpec("osm", "scrapers.osm_palermo", "https://www.openstreetmap.org", 1, "public", "POIs georreferenciados"),
    SourceSpec("wikidata", "scrapers.wikidata_ba", "https://www.wikidata.org", 1, "public", "Instituciones y patrimonio estructurado"),
    SourceSpec("sinca", "scrapers.sinca_culture", "https://datos.gob.ar", 1, "public", "Espacios culturales", args=("--write",), data_class="historical", refresh_schedule="annual"),
    SourceSpec("national_monuments", "scrapers.national_monuments", "https://www.argentina.gob.ar/cultura/monumentos", 1, "public", "Monumentos nacionales"),
    SourceSpec("national_education", "scrapers.national_education", "https://datos.gob.ar", 1, "public", "Padrón educativo"),
    SourceSpec("transporte_rmba", "scrapers.transporte_rmba", "https://datos.gob.ar", 1, "public", "Red de transporte", args=("--write",)),
    SourceSpec("indec_censo", "scrapers.indec_census", "https://www.indec.gob.ar", 1, "public", "Contexto censal", data_class="aggregate", refresh_schedule="census"),
    SourceSpec("refes_historical", "scrapers.refes_historical", "https://datos.gob.ar", 4, "public", "Establecimientos de salud REFES", args=("--write",), data_class="historical", refresh_schedule="annual"),
    SourceSpec("bcra", "scrapers.bcra_sucursales", "https://www.bcra.gob.ar", 1, "public", "Cajeros y redes bancarias"),
    SourceSpec("google_places", "scrapers.google_places", "https://maps.googleapis.com/maps/api/place", 2, "credential", "Ratings, horarios y contacto", "GOOGLE_PLACES_API_KEY", (), "current", "weekly", "paid"),
    SourceSpec("igj", "scrapers.igj", "https://www.igj.gob.ar", 2, "public", "Sociedades y estado legal", data_class="current", refresh_schedule="weekly"),
    SourceSpec("boletin_oficial", "scrapers.boletin_oficial", "https://www.boletinoficial.gob.ar", 3, "credential", "Resoluciones y avisos oficiales", "OPENROUTER_API_KEY", ("--dias", "1"), "current", "daily", "paid"),
    SourceSpec("zonaprop", "scrapers.zonaprop", "https://www.zonaprop.com.ar", 2, "approval", "Inmuebles", data_class="current", refresh_schedule="daily", cost_policy="paid"),
    SourceSpec("argenprop", "scrapers.argenprop", "https://www.argenprop.com", 2, "approval", "Inmuebles", data_class="current", refresh_schedule="daily", cost_policy="paid"),
    SourceSpec("gcba_habilitaciones", "scrapers.gcba_commercial_signals", "https://data.buenosaires.gob.ar/dataset/habilitaciones-aprobadas", 1, "public", "Habilitaciones AGC", refresh_schedule="quarterly"),
    SourceSpec("gcba_obras", "scrapers.gcba_obras", "https://data.buenosaires.gob.ar", 1, "public", "Obras y permisos", refresh_schedule="monthly"),
    SourceSpec("gcba_urbanism", "scrapers.gcba_urban_planning", "https://data.buenosaires.gob.ar", 1, "public", "Código y planeamiento urbano", refresh_schedule="monthly"),
    SourceSpec("gcba_environment", "scrapers.gcba_environment", "https://data.buenosaires.gob.ar", 1, "public", "Arbolado y ambiente", refresh_schedule="annual"),
    SourceSpec("gcba_culture", "scrapers.gcba_culture_public_space", "https://data.buenosaires.gob.ar", 1, "public", "Cultura y espacio público", refresh_schedule="weekly"),
    SourceSpec("gcba_mobility", "scrapers.gcba_mobility", "https://data.buenosaires.gob.ar", 1, "public", "Movilidad y accesibilidad", refresh_schedule="monthly"),
    SourceSpec("gcba_bocba", "scrapers.gcba_bocba", "https://boletinoficial.buenosaires.gob.ar", 3, "credential", "Boletín Oficial CABA", "OPENROUTER_API_KEY", (), "current", "daily", "paid"),
    SourceSpec("gcba_ramps", "scrapers.gcba_accessibility_ramps", "https://data.buenosaires.gob.ar", 1, "public", "Rampas de accesibilidad", refresh_schedule="monthly"),
    SourceSpec("gcba_clubs", "scrapers.gcba_clubs", "https://data.buenosaires.gob.ar", 1, "public", "Clubes de barrio", refresh_schedule="monthly"),
    SourceSpec("gcba_libraries", "scrapers.gcba_libraries", "https://data.buenosaires.gob.ar", 1, "public", "Bibliotecas", refresh_schedule="monthly"),
    SourceSpec("gcba_health_education", "scrapers.gcba_health_education", "https://data.buenosaires.gob.ar", 1, "public", "Salud y educación", refresh_schedule="monthly"),
    SourceSpec("gcba_police", "scrapers.gcba_police_stations", "https://data.buenosaires.gob.ar", 1, "public", "Comisarías", refresh_schedule="monthly"),
    SourceSpec("gcba_community", "scrapers.gcba_community_institutions", "https://data.buenosaires.gob.ar", 1, "public", "Instituciones comunitarias", refresh_schedule="monthly"),
    SourceSpec("gcba_worship", "scrapers.gcba_places_of_worship", "https://data.buenosaires.gob.ar", 1, "public", "Lugares de culto", refresh_schedule="monthly"),
    SourceSpec("gcba_healthy_stations", "scrapers.gcba_healthy_stations", "https://data.buenosaires.gob.ar", 1, "public", "Estaciones saludables", refresh_schedule="monthly"),
    SourceSpec("gcba_labor", "scrapers.gcba_labor_integration", "https://data.buenosaires.gob.ar", 1, "public", "Integración laboral", refresh_schedule="monthly"),
    SourceSpec("gcba_inspections", "scrapers.gcba_inspections", "https://data.buenosaires.gob.ar", 1, "public", "Inspecciones AGC", refresh_schedule="monthly"),
    SourceSpec("gcba_patrimonio", "scrapers.gcba_patrimonio", "https://data.buenosaires.gob.ar", 1, "public", "Patrimonio", data_class="historical", refresh_schedule="annual"),
    SourceSpec("gcba_cultural_archive", "scrapers.gcba_cultural_archive", "https://data.buenosaires.gob.ar", 1, "public", "Archivo cultural", data_class="historical", refresh_schedule="annual"),
    SourceSpec("gcba_nightlife_events", "scrapers.gcba_nightlife_events", "https://data.buenosaires.gob.ar", 1, "public", "Eventos y vida nocturna", refresh_schedule="weekly"),
    SourceSpec("gcba_delitos", "scrapers.gcba_delitos", "https://data.buenosaires.gob.ar", 1, "public", "Delitos agregados", data_class="aggregate", refresh_schedule="monthly"),
    SourceSpec("gcba_wifi", "scrapers.gcba_wifi", "https://data.buenosaires.gob.ar", 1, "public", "Wi-Fi público", refresh_schedule="monthly"),
    SourceSpec("gcba_civil_registry", "scrapers.gcba_civil_registry", "https://data.buenosaires.gob.ar", 1, "public", "Registro civil", refresh_schedule="monthly"),
    SourceSpec("inpi", "scrapers.inpi", "https://www.inpi.gob.ar", 2, "approval", "Marcas públicas", data_class="current", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("arca", "scrapers.arca", "https://www.arca.gob.ar", 2, "approval", "Padrón fiscal autorizado", data_class="current", refresh_schedule="on_demand", cost_policy="approval"),
    SourceSpec("gcba_sports", "scrapers.gcba_sports", "https://data.buenosaires.gob.ar", 1, "public", "Polideportivos y programas deportivos", args=("--write",), refresh_schedule="monthly"),
    SourceSpec("gcba_parcels", "scrapers.gcba_parcels", "https://data.buenosaires.gob.ar", 1, "public", "Parcelas catastrales Palermo", args=("--write",), refresh_schedule="monthly"),
    SourceSpec("gcba_urban_documents", "scrapers.gcba_urban_documents", "https://data.buenosaires.gob.ar", 1, "public", "Certificados, línea oficial y banda mínima", args=("--write",), refresh_schedule="monthly"),
    SourceSpec("gcba_productoras", "scrapers.gcba_productoras", "https://data.buenosaires.gob.ar", 1, "public", "Productoras de eventos masivos", args=("--write",), refresh_schedule="monthly"),
    SourceSpec("gcba_parcel_links", "scrapers.link_parcel_references", "https://data.buenosaires.gob.ar", 1, "public", "Vínculo obras-parcelas por SMP", args=("--write",), refresh_schedule="monthly"),
    SourceSpec("gcba_music_agenda", "scrapers.gcba_music_agenda", "https://data.buenosaires.gob.ar", 1, "public", "Agenda oficial de música vigente", args=("--write",), refresh_schedule="weekly"),
    # Fuentes curatoriales y sectoriales: registradas, pero no automatizadas hasta validar licencia y muestra.
    SourceSpec("up_disenio_comunicacion", "scrapers.manual_web_sources", "https://www.palermo.edu/dyc/publicaciones/", 2, "approval", "Publicaciones académicas de Diseño y Comunicación", data_class="historical", refresh_schedule="annual", cost_policy="approval"),
    SourceSpec("up_mapa_espacios_disenio", "scrapers.manual_web_sources", "https://www.palermo.edu/dyc/mejor-diseno/img/mejor-diseno.pdf", 2, "approval", "Mapa documental de espacios de diseño", data_class="historical", refresh_schedule="annual", cost_policy="approval"),
    SourceSpec("michelin_guide_buenos_aires", "scrapers.manual_web_sources", "https://guide.michelin.com/ar/es/buenos-aires-region/buenos-aires/restaurants", 2, "approval", "Selección curatorial de restaurantes", refresh_schedule="weekly", cost_policy="approval"),
    SourceSpec("hipodromo_gastronomia", "scrapers.manual_web_sources", "https://old.palermo.com.ar/es/gastronomia/c/restaurantes", 2, "approval", "Restaurantes y cafeterías del Hipódromo", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("observatorio_leyendas_palermo", "scrapers.manual_web_sources", "https://buenosaires.gob.ar/sites/default/files/media/document/2018/11/28/063f58061324137ee3f969cc845bc1c127cf7daf.pdf", 1, "approval", "Leyendas e historias curiosas de Palermo", data_class="historical", refresh_schedule="annual", cost_policy="approval"),
    SourceSpec("palermonline_historia", "scrapers.manual_web_sources", "https://palermonline.com.ar/wordpress/", 3, "approval", "Crónicas e historia barrial", data_class="historical", refresh_schedule="quarterly", cost_policy="approval"),
    SourceSpec("trama_ropa_autor", "scrapers.manual_web_sources", "https://www.tramaropadeautor.com/", 2, "approval", "Marcas de indumentaria de autor", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("godoy_mix_group", "scrapers.manual_web_sources", "https://godoymixgroup.com.ar/", 2, "approval", "Streetwear, objetos y ediciones cortas", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("palermo_design", "scrapers.manual_web_sources", "https://palermodesign.com.ar/", 2, "approval", "Muebles de diseño a medida", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("modo_casa", "scrapers.manual_web_sources", "https://modocasa.com.ar/quienes-somos/", 2, "approval", "Interiorismo y muebles personalizados", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("madera_muebles", "scrapers.manual_web_sources", "https://www.maderamuebles.com.ar/showroom/", 2, "approval", "Showroom y estudio de muebles", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("feliza_queer", "scrapers.manual_web_sources", "https://felizarcoiris.com/", 2, "approval", "Bar, club y programación queer", refresh_schedule="weekly", cost_policy="approval"),
    SourceSpec("agenda_queer", "scrapers.manual_web_sources", "https://www.instagram.com/agenda.queer/", 3, "approval", "Agenda de fiestas y eventos LGBTQ+", refresh_schedule="weekly", cost_policy="approval"),
    SourceSpec("cc_nueva_uriarte", "scrapers.manual_web_sources", "https://ccnuevauriarte.com.ar/", 2, "approval", "Centro cultural, música y talleres", refresh_schedule="weekly", cost_policy="approval"),
    SourceSpec("c3_ciencia", "scrapers.manual_web_sources", "https://www.argentina.gob.ar/centro-cultural-de-la-ciencia", 1, "approval", "Centro Cultural de la Ciencia", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("malba", "scrapers.manual_web_sources", "https://malba.org.ar/museo/", 1, "approval", "Museo de arte latinoamericano", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("museo_arte_decorativo", "scrapers.manual_web_sources", "https://museoartedecorativo.cultura.gob.ar/", 1, "approval", "Museo Nacional de Arte Decorativo", refresh_schedule="monthly", cost_policy="approval"),
    SourceSpec("museo_evita", "scrapers.manual_web_sources", "https://museoevita.org/", 1, "approval", "Museo Evita", refresh_schedule="monthly", cost_policy="approval"),
)


def by_name(name: str) -> SourceSpec:
    for source in SOURCES:
        if source.name == name:
            return source
    raise KeyError(name)
