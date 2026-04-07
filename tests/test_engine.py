from src.data import BuildingRecord
from src.engine import ResponseEngine, build_cache_key
from src.schemas import QueryRequest


def _engine() -> ResponseEngine:
    data = {
        "Z1": [
            BuildingRecord(-33.43, -70.62, 100.0, 0.9),
            BuildingRecord(-33.431, -70.621, 200.0, 0.5),
            BuildingRecord(-33.432, -70.622, 300.0, 0.2),
        ],
        "Z2": [
            BuildingRecord(-33.40, -70.58, 80.0, 0.7),
            BuildingRecord(-33.41, -70.57, 160.0, 0.8),
        ],
        "Z3": [BuildingRecord(-33.5, -70.75, 120.0, 0.6)],
        "Z4": [BuildingRecord(-33.44, -70.64, 90.0, 0.9)],
        "Z5": [BuildingRecord(-33.45, -70.78, 110.0, 0.4)],
    }
    return ResponseEngine(data)


def test_q1_count_filters_by_confidence() -> None:
    engine = _engine()
    assert engine.q1_count("Z1", confidence_min=0.5) == 2


def test_q2_area_returns_average_total_and_n() -> None:
    engine = _engine()
    result = engine.q2_area("Z1", confidence_min=0.5)
    assert result["n"] == 2
    assert result["total_area"] == 300.0
    assert result["avg_area"] == 150.0


def test_q5_distribution_bucket_count_matches_records() -> None:
    engine = _engine()
    result = engine.q5_confidence_dist("Z2", bins=4)
    assert sum(bucket["count"] for bucket in result) == 2


def test_compute_q4_works() -> None:
    engine = _engine()
    query = QueryRequest(query_type="Q4", zone_id_a="Z1", zone_id_b="Z2", confidence_min=0.0)
    response = engine.compute(query)
    assert response["query_type"] == "Q4"
    assert "winner" in response["result"]


def test_build_cache_key() -> None:
    q1 = QueryRequest(query_type="Q1", zone_id="Z1", confidence_min=0.4)
    q5 = QueryRequest(query_type="Q5", zone_id="Z2", bins=10)
    assert build_cache_key(q1) == "count:Z1:conf=0.40"
    assert build_cache_key(q5) == "confidence_dist:Z2:bins=10"
