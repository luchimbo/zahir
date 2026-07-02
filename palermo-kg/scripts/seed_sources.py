"""Inserta las fuentes nuevas en la DB."""
import asyncio, os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

NEW_SOURCES = [
    ("osm",                 "https://www.openstreetmap.org",              1),
    ("wikidata",            "https://www.wikidata.org",                   1),
    ("bcra",                "https://www.bcra.gob.ar",                    1),
    ("enacom",              "https://www.enacom.gob.ar",                  1),
    ("indec",               "https://www.indec.gob.ar",                   1),
    ("anmat",               "https://www.anmat.gov.ar",                   1),
    ("afip",                "https://www.afip.gob.ar",                    1),
    ("cnv",                 "https://www.cnv.gob.ar",                     1),
    ("inside_airbnb",       "https://insideairbnb.com",                   1),
    ("smn",                 "https://www.smn.gob.ar",                     1),
    ("apra",                "https://buenosaires.gob.ar/apra",            1),
    ("acumar",              "https://www.acumar.gob.ar",                  1),
    ("mapa_delito",         "https://mapa.buenosaires.gob.ar/delito",     1),
    ("tripadvisor",         "https://www.tripadvisor.com.ar",             2),
    ("guia_oleo",           "https://www.guiaoleo.com.ar",                2),
    ("alternativa_teatral", "https://www.alternativateatral.com",         2),
    ("eventbrite",          "https://www.eventbrite.com.ar",              2),
    ("pedidosya",           "https://www.pedidosya.com.ar",               2),
    ("rappi",               "https://www.rappi.com.ar",                   2),
    ("mercadolibre",        "https://www.mercadolibre.com.ar",            2),
    ("doctoralia",          "https://www.doctoralia.com.ar",              2),
    ("timeout_ba",          "https://www.timeoutbuenosaires.com",         2),
    ("booking",             "https://www.booking.com",                    2),
    ("crunchbase",          "https://www.crunchbase.com",                 2),
    ("clutch",              "https://clutch.co",                          2),
    ("rapipago",            "https://www.rapipago.com.ar",                2),
    ("reddit",              "https://www.reddit.com/r/buenosaires",       2),
    ("youtube",             "https://www.youtube.com",                    2),
]

SQL = "INSERT INTO sources (source_name, source_url, tier) VALUES ($1,$2,$3) ON CONFLICT (source_name) DO NOTHING"

async def main():
    conn = await asyncpg.connect(dsn=os.getenv("DATABASE_URL"))
    inserted = 0
    for name, url, tier in NEW_SOURCES:
        r = await conn.execute(SQL, name, url, tier)
        if r == "INSERT 0 1":
            inserted += 1
            print(f"  + {name}")
        else:
            print(f"  = {name} (ya existia)")
    await conn.close()
    print(f"\nListo: {inserted} fuentes nuevas insertadas de {len(NEW_SOURCES)}")

asyncio.run(main())
