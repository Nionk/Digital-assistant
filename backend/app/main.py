from fastapi import FastAPI
from app.core.database import engine
from app.models import models

app = FastAPI(title="AI-ассистент СКАРТ")

@app.get("/health")
async def health_check():
    return {"status": "ok"}