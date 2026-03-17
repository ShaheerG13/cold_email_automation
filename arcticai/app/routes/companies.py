from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_companies() -> dict:
    # Placeholder until DB is wired.
    return {"items": []}

