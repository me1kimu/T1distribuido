from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    # Payload de consultas Q1-Q5 con parametros de zona y confianza.
    query_type: Literal["Q1", "Q2", "Q3", "Q4", "Q5"]
    zone_id: Optional[str] = None
    zone_id_a: Optional[str] = None
    zone_id_b: Optional[str] = None
    confidence_min: float = Field(default=0.0, ge=0.0, le=1.0)
    bins: int = Field(default=5, ge=1, le=100000)


class MetricEvent(BaseModel):
    # Eventos de cache para hit/miss y eviccion.
    event_type: Literal["hit", "miss", "eviction"]
    query_type: str
    latency_ms: float = Field(ge=0.0)
