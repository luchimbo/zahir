import asyncio
from scrapers.candidate_sources import main_for
SUPPORTS_SOURCE_CONTRACT = True
async def main(): return await main_for("sube_open")
if __name__ == "__main__": print(asyncio.run(main()).as_dict())
