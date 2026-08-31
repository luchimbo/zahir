import asyncio
from scrapers.candidate_sources import main_for
SUPPORTS_SOURCE_CONTRACT = True
async def main(): return await main_for("gcba_ecocircular")
if __name__ == "__main__": print(asyncio.run(main()).as_dict())
