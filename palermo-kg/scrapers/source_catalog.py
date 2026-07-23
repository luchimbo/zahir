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


SOURCES = (
    SourceSpec("ba_data", "scrapers.gcba_ba_data", "https://data.buenosaires.gob.ar", 1, "public", "Barrios, espacios verdes y subte"),
    SourceSpec("ba_data_extended", "scrapers.gcba_extended", "https://data.buenosaires.gob.ar", 1, "public", "Salud, bibliotecas y equipamiento"),
    SourceSpec("osm", "scrapers.osm_palermo", "https://www.openstreetmap.org", 1, "public", "POIs georreferenciados"),
    SourceSpec("wikidata", "scrapers.wikidata_ba", "https://www.wikidata.org", 1, "public", "Instituciones y patrimonio estructurado"),
    SourceSpec("sinca", "scrapers.sinca_culture", "https://datos.gob.ar", 1, "public", "Espacios culturales", args=("--write",)),
    SourceSpec("national_monuments", "scrapers.national_monuments", "https://www.argentina.gob.ar/cultura/monumentos", 1, "public", "Monumentos nacionales"),
    SourceSpec("national_education", "scrapers.national_education", "https://datos.gob.ar", 1, "public", "Padrón educativo"),
    SourceSpec("transporte_rmba", "scrapers.transporte_rmba", "https://datos.gob.ar", 1, "public", "Red de transporte", args=("--write",)),
    SourceSpec("indec_censo", "scrapers.indec_census", "https://www.indec.gob.ar", 1, "public", "Contexto censal"),
    SourceSpec("refes_historical", "scrapers.refes_historical", "https://datos.gob.ar", 4, "public", "Establecimientos de salud REFES", args=("--write",)),
    SourceSpec("bcra", "scrapers.bcra_sucursales", "https://www.bcra.gob.ar", 1, "public", "Cajeros y redes bancarias"),
    SourceSpec("google_places", "scrapers.google_places", "https://maps.googleapis.com/maps/api/place", 2, "credential", "Ratings, horarios y contacto", "GOOGLE_PLACES_API_KEY"),
    SourceSpec("igj", "scrapers.igj", "https://www.igj.gob.ar", 2, "approval", "Sociedades y estado legal"),
    SourceSpec("boletin_oficial", "scrapers.boletin_oficial", "https://www.boletinoficial.gob.ar", 3, "credential", "Resoluciones y avisos oficiales", "OPENROUTER_API_KEY", ("--dias", "1")),
    SourceSpec("zonaprop", "scrapers.zonaprop", "https://www.zonaprop.com.ar", 2, "approval", "Inmuebles"),
    SourceSpec("argenprop", "scrapers.argenprop", "https://www.argenprop.com", 2, "approval", "Inmuebles"),
)


def by_name(name: str) -> SourceSpec:
    for source in SOURCES:
        if source.name == name:
            return source
    raise KeyError(name)
