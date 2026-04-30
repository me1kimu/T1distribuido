from __future__ import annotations

import asyncio
import json
import os
import time
from functools import partial

import httpx
import redis
from anyio import to_thread
from fastapi import FastAPI, HTTPException

from src.engine import build_cache_key
from src.schemas import MetricEvent, QueryRequest

app = FastAPI(title="Cache Service")
redis_client: redis.Redis | None = None
response_client: httpx.AsyncClient | None = None
metrics_client: httpx.AsyncClient | None = None
response_service_url = os.getenv("RESPONSE_SERVICE_URL", "http://localhost:8002")
metrics_service_url = os.getenv("METRICS_SERVICE_URL", "http://localhost:8001")
# TTL de cache en segundos para respuestas precargadas.
cache_ttl_seconds = int(os.getenv("CACHE_TTL", "120"))
_last_evicted_keys = 0
_eviction_lock = asyncio.Lock()


@app.on_event("startup")
async def startup() -> None:
    global redis_client, response_client, metrics_client, _last_evicted_keys
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, decode_responses=True)
    redis_client = client
    response_client = httpx.AsyncClient(timeout=60.0)
    metrics_client = httpx.AsyncClient(timeout=60.0)
    try:
        info = await to_thread.run_sync(client.info, "stats")
        _last_evicted_keys = int(info.get("evicted_keys", 0))
    except Exception:
        _last_evicted_keys = 0


@app.on_event("shutdown")
async def shutdown() -> None:
    if response_client is not None:
        await response_client.aclose()
    if metrics_client is not None:
        await metrics_client.aclose()


async def _push_metric(event: MetricEvent) -> None:
    if metrics_client is None:
        return
    try:
        await metrics_client.post(f"{metrics_service_url}/events", json=event.model_dump())
    except httpx.HTTPError:
        pass


async def _register_evictions_if_any() -> int:
    global _last_evicted_keys

    async with _eviction_lock:
        client = redis_client
        if client is None:
            return 0
        try:
            info = await to_thread.run_sync(client.info, "stats")
            current = int(info.get("evicted_keys", 0))
        except Exception:
            return 0

        delta = max(current - _last_evicted_keys, 0)
        _last_evicted_keys = current
        return delta


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "cache-service"}


@app.post("/query")
async def query(payload: QueryRequest) -> dict:
    redis_ref = redis_client
    response_ref = response_client
    if redis_ref is None or response_ref is None:
        raise HTTPException(status_code=503, detail="cache-service no inicializado")

    key = build_cache_key(payload)
    start = time.perf_counter()

    try:
        cached = await to_thread.run_sync(redis_ref.get, key)
    except Exception:
        cached = None

    if cached is not None:
        # Cache hit: responde desde Redis y registra latencia.
        latency_ms = (time.perf_counter() - start) * 1000
        await _push_metric(MetricEvent(event_type="hit", query_type=payload.query_type, latency_ms=latency_ms))
        return {"cache_key": key, "source": "cache", "result": json.loads(cached)}

    try:
        # Cache miss: delega el calculo al servicio de respuestas.
        response = await response_ref.post(f"{response_service_url}/compute", json=payload.model_dump())
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="response-service no disponible") from exc

    computed = response.json()
    try:
        await to_thread.run_sync(partial(redis_ref.set, key, json.dumps(computed["result"]), ex=cache_ttl_seconds))
    except Exception:
        pass

    latency_ms = (time.perf_counter() - start) * 1000
    await _push_metric(MetricEvent(event_type="miss", query_type=payload.query_type, latency_ms=latency_ms))

    evictions = await _register_evictions_if_any()
    # Reporta evicciones acumuladas como eventos de metricas.
    for _ in range(evictions):
        await _push_metric(MetricEvent(event_type="eviction", query_type=payload.query_type, latency_ms=0.0))

    return {"cache_key": key, "source": "response-service", "result": computed["result"]}
