from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

router = APIRouter(prefix="/api/trends", tags=["trends"])

# MONGO SETUP
def _get_col():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    return client["big_data_class"]["wiki_trends"]
# END MONGO SETUP

# GET TRENDING
@router.get("/")
def get_trending(limit: int = 5):
    try:
        col = _get_col()
        doc = col.find_one({}, {"_id": 0}, sort=[("scraped_at", -1)])
        if not doc:
            raise HTTPException(status_code=404, detail="No trend data found")

        totals: dict[str, int] = {}

        for article, entries in doc.get("data", {}).items():
            if entries:
                totals[article] = entries[-1]["views"]

        ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]

        desc_map = doc.get("descriptions", {})

        return {
            "scraped_at": doc.get("scraped_at"),
            "trending": [
                {
                    "rank": i + 1,
                    "article": name.replace("_", " "),
                    "views_90d": views,
                    "description": desc_map.get(name, ""),
                }
                for i, (name, views) in enumerate(ranked)
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# END GET TRENDING
