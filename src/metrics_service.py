from __future__ import annotations

import time
from collections import defaultdict
from statistics import median
from threading import Lock
from typing import Dict, List

from fastapi import FastAPI

from src.schemas import MetricEvent


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._started_at = time.time()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._latencies: List[float] = []
        self._latencies_hit: List[float] = []
        self._latencies_miss: List[float] = []
        self._by_query: Dict[str, int] = defaultdict(int)

    def record(self, event: MetricEvent) -> None:
        # Registra hits, misses, latencias y evicciones para el analisis.
        with self._lock:
            self._latencies.append(event.latency_ms)
            self._by_query[event.query_type] += 1
            if event.event_type == "hit":
                self._hits += 1
                self._latencies_hit.append(event.latency_ms)
            elif event.event_type == "miss":
                self._misses += 1
                self._latencies_miss.append(event.latency_ms)
            elif event.event_type == "eviction":
                self._evictions += 1

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = int((len(ordered) - 1) * pct)
        return ordered[idx]

    def summary(self) -> dict:
        # Resume hit/miss rate, throughput y percentiles p50/p95.
        with self._lock:
            total = self._hits + self._misses
            uptime = max(time.time() - self._started_at, 1e-6)
            hit_rate = self._hits / total if total else 0.0
            miss_rate = self._misses / total if total else 0.0
            throughput = total / uptime
            evictions_per_min = self._evictions / (uptime / 60)
            p50 = median(self._latencies) if self._latencies else 0.0
            p95 = self._percentile(self._latencies, 0.95)
            avg_hit = sum(self._latencies_hit) / len(self._latencies_hit) if self._latencies_hit else 0.0
            avg_miss = sum(self._latencies_miss) / len(self._latencies_miss) if self._latencies_miss else 0.0
            cache_efficiency = ((self._hits * avg_hit) - (self._misses * avg_miss)) / total if total else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": hit_rate,
                "miss_rate": miss_rate,
                "throughput_qps": throughput,
                "latency_ms_p50": p50,
                "latency_ms_p95": p95,
                "eviction_rate_per_min": evictions_per_min,
                "cache_efficiency": cache_efficiency,
                "queries_by_type": dict(self._by_query),
            }


app = FastAPI(title="Metrics Service")
registry = MetricsRegistry()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "metrics-service"}


@app.post("/events")
def events(event: MetricEvent) -> dict:
    registry.record(event)
    return {"ok": True}


@app.get("/summary")
def summary() -> dict:
    return registry.summary()
