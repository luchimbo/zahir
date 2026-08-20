"""Relaciona obras de Palermo con su parcela por SMP, sin crear ni borrar entidades."""
import argparse, asyncio, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scrapers.shared.db_helpers import get_conn

async def main():
 p=argparse.ArgumentParser();p.add_argument("--write",action="store_true");args=p.parse_args();conn=await get_conn()
 try:
  count=await conn.fetchval("""SELECT COUNT(*) FROM active_properties w JOIN active_properties q ON q.`key`='smp' AND UPPER(q.value)=UPPER(w.value)
   JOIN entities we ON we.id=w.entity_id JOIN entities pe ON pe.id=q.entity_id
   WHERE w.`key`='smp' AND we.entity_type='Facility' AND pe.entity_type='Parcel' AND we.canonical_id IS NULL AND pe.canonical_id IS NULL""")
  print(f"Obras con parcela SMP resoluble: {count}")
  if not args.write:return
  await conn.execute("""INSERT INTO relationships (id,from_entity_id,relationship_type,to_entity_id,confidence,origins)
   SELECT UUID(),w.entity_id,'RELATED_TO',q.entity_id,.95,JSON_ARRAY('https://data.buenosaires.gob.ar')
   FROM active_properties w JOIN active_properties q ON q.`key`='smp' AND UPPER(q.value)=UPPER(w.value)
   JOIN entities we ON we.id=w.entity_id JOIN entities pe ON pe.id=q.entity_id
   WHERE w.`key`='smp' AND we.entity_type='Facility' AND pe.entity_type='Parcel' AND we.canonical_id IS NULL AND pe.canonical_id IS NULL
   AND NOT EXISTS (SELECT 1 FROM relationships r WHERE r.from_entity_id=w.entity_id AND r.to_entity_id=q.entity_id AND r.relationship_type='RELATED_TO')""")
 finally:await conn.close()
if __name__=="__main__":asyncio.run(main())
