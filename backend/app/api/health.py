"""Health check and ping endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "Backend is running"}


@router.get("/api/ping")
async def ping():
    return {"message": "Hello from FastAPI backend"}
