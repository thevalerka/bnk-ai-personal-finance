from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Adaptive Markets Terminal API")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
