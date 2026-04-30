from __future__ import annotations

from fastapi import FastAPI, HTTPException

from src.data import load_dataset
from src.engine import QueryValidationError, ResponseEngine
from src.schemas import QueryRequest

app = FastAPI(title="Response Service")
engine: ResponseEngine | None = None


@app.on_event("startup")
def startup() -> None:
    global engine
    # Descarga el dataset de Google (o reanuda el archivo parcial en el volumen) y lo carga en memoria.
    engine = ResponseEngine(load_dataset())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "response-service"}


@app.post("/compute")
def compute(query: QueryRequest) -> dict:
    # Ejecuta Q1-Q5 en memoria y retorna el resultado al cache.
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Response engine is not initialized",
        )
    try:
        return engine.compute(query)
    except QueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
