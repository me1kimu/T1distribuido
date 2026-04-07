from __future__ import annotations

import json
import os
import time

import httpx
import redis
from fastapi import FastAPI, HTTPException

from src.engine import build_cache_key
from src.schemas import MetricEvent, QueryRequest

app = FastAPI(title="Cache Service")
redis_client: redis.Redis | None = None
response_service_url = os.getenv("RESPONSE_SERVICE_URL", "http://localhost:8002")
metrics_service_url = os.getenv("METRICS_SERVICE_URL", "http://localhost:8001")
cache_ttl_seconds = int(os.getenv("CACHE_TTL", "120"))
_last_evicted_keys = 0


@app.on_event("startup")
def startup() -> None:
    global redis_client, _last_evicted_keys
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    try:
        info = redis_client.info("stats")
        _last_evicted_keys = int(info.get("evicted_keys", 0))
    except Exception:
        _last_evicted_keys = 0


async def _push_metric(event: MetricEvent) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{metrics_service_url}/events", json=event.model_dump())
        except httpx.HTTPError:
            pass


def _register_evictions_if_any(query_type: str) -> int:
    global _last_evicted_keys
    try:
        info = redis_client.info("stats")
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
    key = build_cache_key(payload)
    start = time.perf_counter()

    try:
        cached = redis_client.get(key)
    except Exception:
        cached = None

    if cached is not None:
        latency_ms = (time.perf_counter() - start) * 1000
        await _push_metric(MetricEvent(event_type="hit", query_type=payload.query_type, latency_ms=latency_ms))
        return {"cache_key": key, "source": "cache", "result": json.loads(cached)}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{response_service_url}/compute", json=payload.model_dump())
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="response-service no disponible") from exc

    computed = response.json()
    try:
        redis_client.set(key, json.dumps(computed["result"]), ex=cache_ttl_seconds)
    except Exception:
        pass

    latency_ms = (time.perf_counter() - start) * 1000
    await _push_metric(MetricEvent(event_type="miss", query_type=payload.query_type, latency_ms=latency_ms))

    evictions = _register_evictions_if_any(payload.query_type)
    for _ in range(evictions):
        await _push_metric(MetricEvent(event_type="eviction", query_type=payload.query_type, latency_ms=0.0))

    return {"cache_key": key, "source": "response-service", "result": computed["result"]}
