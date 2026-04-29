from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, HTTPException

from src.data import load_dataset, loader_status
from src.engine import QueryValidationError, ResponseEngine
from src.schemas import QueryRequest

app = FastAPI(title="Response Service")
engine: ResponseEngine | None = None
_engine_error: Exception | None = None
_logger = logging.getLogger("uvicorn.error")


async def _init_engine() -> None:
    global engine, _engine_error
    try:
        dataset_path = os.getenv("DATASET_PATH")
        data = await asyncio.to_thread(load_dataset, dataset_path)
        engine = ResponseEngine(data)
        _logger.info("Dataset cargado en memoria")
    except Exception as exc:
        _engine_error = exc
        _logger.exception("Error al cargar dataset")


@app.on_event("startup")
async def startup() -> None:
    # Inicializa en background para no bloquear el startup.
    asyncio.create_task(_init_engine())


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "response-service",
        "dataset_loaded": engine is not None,
        "dataset_status": loader_status["phase"],
        "dataset_detail": loader_status["detail"],
        "dataset_error": str(_engine_error) if _engine_error else loader_status.get("error"),
    }


@app.post("/compute")
def compute(query: QueryRequest) -> dict:
    # Ejecuta Q1-Q5 en memoria y retorna el resultado al cache.
    if _engine_error is not None:
        raise HTTPException(status_code=503, detail=str(_engine_error))
    if engine is None:
        raise HTTPException(status_code=503, detail="Response engine is not initialized")
    try:
        return engine.compute(query)
    except QueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
