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
)


def by_name(name: str) -> SourceSpec:
    for source in SOURCES:
        if source.name == name:
            return source
    raise KeyError(name)
