from __future__ import annotations

from statistics import mean
from typing import Dict, List

import numpy as np

from src.config import ZONE_AREAS_KM2, ZONES
from src.data import BuildingRecord
from src.schemas import QueryRequest


class QueryValidationError(ValueError):
    pass


class ResponseEngine:
    def __init__(self, data: Dict[str, List[BuildingRecord]]):
        self.data = data

    def q1_count(self, zone_id: str, confidence_min: float = 0.0) -> int:
        # Q1: conteo de edificios por zona y umbral de confianza.
        records = self.data[zone_id]
        return sum(1 for r in records if r.confidence >= confidence_min)

    def q2_area(self, zone_id: str, confidence_min: float = 0.0) -> dict:
        # Q2: area promedio y area total por zona.
        areas = [r.area_in_meters for r in self.data[zone_id] if r.confidence >= confidence_min]
        if not areas:
            return {"avg_area": 0.0, "total_area": 0.0, "n": 0}
        return {"avg_area": mean(areas), "total_area": sum(areas), "n": len(areas)}

    def q3_density(self, zone_id: str, confidence_min: float = 0.0) -> float:
        # Q3: densidad por km2 normalizada por el area de la zona.
        count = self.q1_count(zone_id, confidence_min)
        return count / ZONE_AREAS_KM2[zone_id]

    def q4_compare(self, zone_id_a: str, zone_id_b: str, confidence_min: float = 0.0) -> dict:
        # Q4: comparacion de densidad entre dos zonas.
        da = self.q3_density(zone_id_a, confidence_min)
        db = self.q3_density(zone_id_b, confidence_min)
        winner = zone_id_a if da > db else zone_id_b
        return {"zone_a": zone_id_a, "density_a": da, "zone_b": zone_id_b, "density_b": db, "winner": winner}

    def q5_confidence_dist(self, zone_id: str, bins: int = 5) -> list:
        # Q5: histograma de confianza en una zona.
        scores = [r.confidence for r in self.data[zone_id]]
        counts, edges = np.histogram(scores, bins=bins, range=(0, 1))
        return [
            {
                "bucket": i,
                "min": float(edges[i]),
                "max": float(edges[i + 1]),
                "count": int(counts[i]),
            }
            for i in range(bins)
        ]

    def compute(self, query: QueryRequest) -> dict:
        self._validate_query(query)

        if query.query_type == "Q1":
            return {
                "query_type": "Q1",
                "zone_id": query.zone_id,
                "result": self.q1_count(query.zone_id, query.confidence_min),
            }
        if query.query_type == "Q2":
            return {
                "query_type": "Q2",
                "zone_id": query.zone_id,
                "result": self.q2_area(query.zone_id, query.confidence_min),
            }
        if query.query_type == "Q3":
            return {
                "query_type": "Q3",
                "zone_id": query.zone_id,
                "result": self.q3_density(query.zone_id, query.confidence_min),
            }
        if query.query_type == "Q4":
            return {
                "query_type": "Q4",
                "zone_id_a": query.zone_id_a,
                "zone_id_b": query.zone_id_b,
                "result": self.q4_compare(query.zone_id_a, query.zone_id_b, query.confidence_min),
            }
        return {
            "query_type": "Q5",
            "zone_id": query.zone_id,
            "result": self.q5_confidence_dist(query.zone_id, query.bins),
        }

    @staticmethod
    def _validate_query(query: QueryRequest) -> None:
        if query.query_type in {"Q1", "Q2", "Q3", "Q5"} and query.zone_id not in ZONES:
            raise QueryValidationError("zone_id inválido para la consulta")
        if query.query_type == "Q4":
            if query.zone_id_a not in ZONES or query.zone_id_b not in ZONES:
                raise QueryValidationError("zone_id_a o zone_id_b inválido para Q4")
            if query.zone_id_a == query.zone_id_b:
                raise QueryValidationError("zone_id_a y zone_id_b deben ser distintos")


def build_cache_key(query: QueryRequest) -> str:
    # Formato de cache key alineado con las consultas Q1-Q5 del enunciado.
    conf = f"{query.confidence_min:.2f}"
    if query.query_type == "Q1":
        return f"count:{query.zone_id}:conf={conf}"
    if query.query_type == "Q2":
        return f"area:{query.zone_id}:conf={conf}"
    if query.query_type == "Q3":
        return f"density:{query.zone_id}:conf={conf}"
    if query.query_type == "Q4":
        return f"compare:density:{query.zone_id_a}:{query.zone_id_b}:conf={conf}"
    return f"confidence_dist:{query.zone_id}:bins={query.bins}"
