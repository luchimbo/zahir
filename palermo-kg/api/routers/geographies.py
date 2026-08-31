from fastapi import APIRouter

from geography_catalog import geography_rows

router = APIRouter(tags=["geography"])


@router.get("/geographies")
async def list_geographies():
    """División territorial oficial disponible para filtros y clientes."""
    rows = geography_rows()
    return {
        "city": rows[0],
        "communes": [row for row in rows if row["level"] == "commune"],
        "neighborhoods": [row for row in rows if row["level"] == "neighborhood"],
    }
