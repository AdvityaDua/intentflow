from config import get_settings
from agents.knowledge_agent import retrieve_and_plan
import asyncio
from database import init_db

async def main():
    init_db()
    s = get_settings()
    plan = await retrieve_and_plan("billing_dispute", {}, "Medium", "My premium tier billing is showing incorrect charges for the last 3 months", "")
    print("PLAN:", plan.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())
