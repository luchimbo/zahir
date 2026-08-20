"""
Entity Resolver — Palermo Knowledge Graph
Deduplica entidades canonicas del mismo tipo o tipo cercano cuando representan
la misma entidad real (ej. "Don Julio" de OSM y "Don Julio Parrilla" de Google
Places, o una institución de Wikidata y otra de espacios culturales).

Estrategia:
  1. Agrupa entidades candidatas por tipo de entidad.
  2. Dentro de cada grupo, busca pares con nombres similares (pg_trgm).
  3. Si la similitud es alta (>= 0.75) → match automatico.
  4. Si es media (0.45 - 0.75) → confirma con LLM (DeepSeek via OpenRouter).
  5. Si hay match → la entidad con menor importancia / menos propiedades apunta
     a la canonica (canonical_id) y se agrega el nombre alternativo a all_names.

Reglas:
  - Nunca se borra una entidad; se marca como duplicado via canonical_id.
  - Solo se comparan entidades activas y canonicas (canonical_id IS NULL).
  - Se prioriza unificacion intra-fuente, pero funciona cross-source.
"""

import asyncio
import argparse
import os
import re
import json
from difflib import SequenceMatcher
from openai import AsyncOpenAI
from dotenv import load_dotenv
from scrapers.shared.db_helpers import get_conn

load_dotenv()

OR_MODEL = "deepseek/deepseek-v4-flash"
SIMILARITY_AUTO = 0.75
SIMILARITY_MAYBE = 0.45
LLM_BATCH_SIZE = 20

llm = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY"),
)


_STOP = re.compile(
    r"\b(sa|srl|sas|sc|sca|scs|sau|s\.a\.|s\.r\.l\.|s\.a\.s\.|"
    r"de|del|la|las|los|el|y|e|en|a|al|por|para|con|the|and|of|in)\b",
    re.IGNORECASE
)


def normalize_name_for_match(name: str) -> str:
    cleaned = _STOP.sub(" ", name)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


async def llm_confirm_matches(pairs: list[tuple[str, str]]) -> list[bool]:
    """Confirma varios pares con una sola llamada al LLM."""
    if not llm.api_key:
        return [False] * len(pairs)

    blocks = []
    for i, (a, b) in enumerate(pairs, 1):
        blocks.append(f"{i}. \"{a}\" vs \"{b}\"")

    prompt = (
        "Sos un asistente experto en deduplicacion de entidades del barrio de Palermo, Buenos Aires.\n"
        "Para cada par, responde SOLO 'si' o 'no' si representan la misma entidad real.\n"
        "Ignora diferencias de formato, acentos, mayusculas o palabras legales.\n\n"
        + "\n".join(blocks)
        + "\n\nResponde con una lista numerada exacta (si/no)."
    )
    try:
        resp = await llm.chat.completions.create(
            model=OR_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0,
        )
        text = resp.choices[0].message.content or ""
        results = []
        for line in text.splitlines():
            line = line.strip().lower()
            if not line:
                continue
            # buscar primer si/no en la linea
            if line.startswith("si") or " si" in line or ": si" in line:
                results.append(True)
            elif line.startswith("no") or " no" in line or ": no" in line:
                results.append(False)
        # Rellenar con False si faltan
        while len(results) < len(pairs):
            results.append(False)
        return results[:len(pairs)]
    except Exception as e:
        print(f"    [LLM error] {e}")
        return [False] * len(pairs)


async def entity_importance_and_props(conn, entity_id: str) -> tuple[int, int]:
    row = await conn.fetchrow(
        """
        SELECT e.importance,
               (SELECT COUNT(*) FROM properties p WHERE p.entity_id = e.id AND p.valid_until IS NULL) AS prop_count
        FROM entities e WHERE e.id = $1
        """,
        entity_id
    )
    return row["importance"] or 0, row["prop_count"] or 0


async def merge_entities(conn, keep_id: str, duplicate_id: str, confidence: float, method: str):
    """Marca duplicate_id como duplicado de keep_id y agrega nombre alternativo."""
    dup_row = await conn.fetchrow(
        "SELECT name, all_names FROM entities WHERE id = $1", duplicate_id
    )
    if not dup_row:
        return
    dup_name = dup_row["name"]
    dup_all_names = json.loads(dup_row["all_names"]) if isinstance(dup_row["all_names"], str) else (dup_row["all_names"] or [])

    keep_row = await conn.fetchrow(
        "SELECT name, all_names FROM entities WHERE id = $1", keep_id
    )
    keep_all_names = json.loads(keep_row["all_names"]) if isinstance(keep_row["all_names"], str) else (keep_row["all_names"] or [])

    new_all_names = list(set(keep_all_names + [dup_name] + list(dup_all_names)))

    await conn.execute(
        """
        UPDATE entities
        SET canonical_id = $1, is_active = false, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        keep_id, duplicate_id
    )
    await conn.execute(
        """
        UPDATE entities
        SET all_names = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """,
        json.dumps(new_all_names), keep_id
    )
    await conn.execute(
        """
        INSERT INTO relationships (id, from_entity_id, relationship_type, to_entity_id, confidence, origins, direction)
        SELECT UUID(), $1, 'CANONICAL', $2, $3, $4, 'directed'
        WHERE NOT EXISTS (SELECT 1 FROM relationships WHERE from_entity_id=$5 AND relationship_type='CANONICAL' AND to_entity_id=$6)
        """,
        duplicate_id, keep_id, confidence,
        json.dumps([f"entity_resolver:{method}"]), duplicate_id, keep_id
    )


async def find_candidate_pairs(conn, entity_type: str, subtype: str | None) -> list[dict]:
    """Busca pares candidatos de entidades similares dentro de un tipo/subtipo."""
    if subtype:
        rows = await conn.fetch(
            """
            SELECT id, name
            FROM entities
            WHERE entity_type = $1 AND subtype = $2
              AND is_active = true AND canonical_id IS NULL
            ORDER BY name
            """,
            entity_type, subtype
        )
    else:
        rows = await conn.fetch(
            """
            SELECT id, name
            FROM entities
            WHERE entity_type = $1
              AND is_active = true AND canonical_id IS NULL
            ORDER BY name
            """,
            entity_type
        )

    # TiDB no ofrece pg_trgm: se calcula una similitud conservadora en Python.
    candidates = []
    names = {r["id"]: r["name"] for r in rows}
    for r in rows:
        org_id = r["id"]
        org_name = r["name"]
        matches = []
        norm_org = normalize_name_for_match(org_name)
        for other in rows:
            if other["id"] == org_id:
                continue
            sim = SequenceMatcher(None, norm_org, normalize_name_for_match(other["name"])).ratio()
            if sim >= SIMILARITY_MAYBE:
                matches.append((sim, other))
        for sim, m in sorted(matches, key=lambda item: item[0], reverse=True)[:3]:
            if sim < SIMILARITY_MAYBE:
                continue
            # Evitar duplicados simetricos: ordenamos IDs
            a, b = sorted([org_id, m["id"]])
            norm_a = set(normalize_name_for_match(names[a]).split())
            norm_b = set(normalize_name_for_match(names[b]).split())
            shared_tokens = norm_a & norm_b
            # Rechazar pares de una sola palabra sin similitud muy alta
            if len(norm_a) == 1 and len(norm_b) == 1 and sim < 0.90:
                continue
            # Rechazar si no comparten ningun token significativo y sim baja
            if not shared_tokens and sim < 0.70:
                continue
            # Rechazar nombres genericos como 'Museo de la Luz' con otros museos
            generic = {"museo", "restaurant", "bar", "cafe", "teatro", "centro", "cultural"}
            if len(shared_tokens) == 1 and list(shared_tokens)[0] in generic and sim < 0.82:
                continue
            # Rechazar cuando el nombre fuente es generico y muy corto
            if len(norm_a) <= 2 and len(norm_b) >= 4 and sim < 0.80:
                continue
            candidates.append({
                "a": a, "b": b,
                "name_a": names[a], "name_b": names[b],
                "sim": sim,
            })

    # Deduplicar pares
    seen = set()
    unique = []
    for c in candidates:
        key = (c["a"], c["b"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique


async def resolve_group(conn, entity_type: str, subtype: str | None, dry_run: bool = False) -> dict:
    pairs = await find_candidate_pairs(conn, entity_type, subtype)
    print(f"  {entity_type}/{subtype}: {len(pairs)} pares candidatos")

    auto_pairs = [p for p in pairs if p["sim"] >= SIMILARITY_AUTO]
    maybe_pairs = [p for p in pairs if SIMILARITY_MAYBE <= p["sim"] < SIMILARITY_AUTO]

    stats = {"auto": 0, "llm_yes": 0, "llm_no": 0}

    # Procesar matches automaticos
    for p in auto_pairs:
        print(f"    AUTO [{p['sim']:.2f}] '{p['name_a']}' -> '{p['name_b']}'")
        if not dry_run:
            await merge_pair(conn, p, "trgm_auto")
        stats["auto"] += 1

    # Procesar matches dudosos en batches con LLM
    for i in range(0, len(maybe_pairs), LLM_BATCH_SIZE):
        batch = maybe_pairs[i:i + LLM_BATCH_SIZE]
        confirmations = await llm_confirm_matches(
            [(p["name_a"], p["name_b"]) for p in batch]
        )
        for p, confirmed in zip(batch, confirmations):
            tag = "LLM_OK" if confirmed else "LLM_NO"
            print(f"    {tag} [{p['sim']:.2f}] '{p['name_a']}' -> '{p['name_b']}'")
            if confirmed:
                if not dry_run:
                    await merge_pair(conn, p, "llm_confirmed")
                stats["llm_yes"] += 1
            else:
                stats["llm_no"] += 1

    return stats


async def merge_pair(conn, pair: dict, method: str):
    """Elige canonica y mergea."""
    a_imp, a_props = await entity_importance_and_props(conn, pair["a"])
    b_imp, b_props = await entity_importance_and_props(conn, pair["b"])

    # Canonica: la de mayor importancia, o si igual, la que tenga mas propiedades
    if (a_imp, a_props) >= (b_imp, b_props):
        keep, dup = pair["a"], pair["b"]
    else:
        keep, dup = pair["b"], pair["a"]

    await merge_entities(conn, keep, dup, pair["sim"], method)


async def main():
    parser = argparse.ArgumentParser(description="Entity Resolver — Palermo KG")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra matches, no escribe en la DB")
    parser.add_argument("--entity-type", type=str,
                        help="Resolver solo este tipo de entidad")
    parser.add_argument("--subtype", type=str,
                        help="Resolver solo este subtipo")
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "PRODUCCION"
    print(f"=== Entity Resolver [{mode}] ===\n")

    conn = await get_conn()
    try:
        if args.entity_type:
            groups = [(args.entity_type, args.subtype)]
        else:
            # Grupos donde la deduplicacion cross-source tiene mas valor
            groups = [
                ("Organization", "restaurant"),
                ("Organization", "cafe"),
                ("Organization", "bar"),
                ("Organization", "fast_food"),
                ("Facility", "museo"),
                ("Facility", "teatro"),
                ("Facility", "biblioteca"),
                ("Facility", "centro_cultural"),
                ("Facility", "galeria_arte"),
                ("Facility", "cine"),
                ("Facility", "anfiteatro"),
                ("Facility", "espacio_cultural"),
            ]

        total_stats = {"auto": 0, "llm_yes": 0, "llm_no": 0}
        for entity_type, subtype in groups:
            stats = await resolve_group(conn, entity_type, subtype, dry_run=args.dry_run)
            for k in total_stats:
                total_stats[k] += stats[k]

        print("\n-- Resultados ------------------")
        print(f"  Match automatico (trgm):   {total_stats['auto']}")
        print(f"  Match confirmado (LLM):    {total_stats['llm_yes']}")
        print(f"  Rechazado (LLM):           {total_stats['llm_no']}")
        total = total_stats["auto"] + total_stats["llm_yes"]
        print(f"  Entidades unificadas:      {total}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
