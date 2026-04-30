from __future__ import annotations

import argparse
import random
import time
from collections import Counter
from urllib.parse import urlparse, urlunparse

import requests

from src.config import ZONES


def _pick_zone(distribution: str, rng: random.Random) -> str:
    # Seleccion de zona con distribucion uniforme o Zipf.
    zone_ids = list(ZONES.keys())
    if distribution == "uniform":
        return rng.choice(zone_ids)

    s = 1.2
    ranks = list(range(1, len(zone_ids) + 1))
    weights = [1 / (r**s) for r in ranks]
    total = sum(weights)
    probs = [w / total for w in weights]
    return rng.choices(zone_ids, weights=probs, k=1)[0]


def _generate_query(distribution: str, rng: random.Random) -> dict:
    # Genera consultas sinteticas Q1-Q5 con parametros validos.
    query_type = rng.choice(["Q1", "Q2", "Q3", "Q4", "Q5"])

    if query_type == "Q4":
        zone_a, zone_b = rng.sample(list(ZONES.keys()), 2)
        return {
            "query_type": "Q4",
            "zone_id_a": zone_a,
            "zone_id_b": zone_b,
            "confidence_min": round(rng.uniform(0.0, 0.99), 2),
            "bins": rng.randint(5000, 15000),
        }

    return {
        "query_type": query_type,
        "zone_id": _pick_zone(distribution, rng),
        "confidence_min": round(rng.uniform(0.0, 0.99), 2),
        "bins": rng.randint(5000, 15000),
    }


def _default_metrics_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    host = parsed.hostname or parsed.netloc.split("@")[-1].split(":")[0]

    if host == "cache-service":
        host = "metrics-service"
    return urlunparse((parsed.scheme or "http", f"{host}:8001", "/summary", "", "", ""))


import concurrent.futures

def run(base_url: str, metrics_url: str | None, requests_n: int, distribution: str, sleep_ms: int, seed: int) -> None:
    # Envia trafico controlado y reporta metricas agregadas concurrentemente.
    rng = random.Random(seed)
    endpoint = f"{base_url.rstrip('/')}/query"

    ok = 0
    errors = 0
    by_type = Counter()
    started = time.perf_counter()

    queries = [_generate_query(distribution, random.Random(seed + i)) for i in range(requests_n)]
    for q in queries:
        by_type[q["query_type"]] += 1

    def send_query(payload):
        nonlocal ok, errors
        try:
            res = requests.post(endpoint, json=payload, timeout=60)
            if res.ok:
                ok += 1
            else:
                errors += 1
        except requests.RequestException:
            errors += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        executor.map(send_query, queries)

    elapsed = max(time.perf_counter() - started, 1e-6)
    print(f"Solicitudes enviadas: {requests_n}")
    print(f"Exitosas: {ok}")
    print(f"Errores: {errors}")
    print(f"Throughput observado: {ok / elapsed:.2f} req/s")
    print(f"Distribución por consulta: {dict(by_type)}")

    try:
        metrics_endpoint = metrics_url or _default_metrics_url(base_url)
        metrics = requests.get(metrics_endpoint, timeout=60)
        if metrics.ok:
            print("Resumen métricas:", metrics.json())
    except requests.RequestException:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Generador de tráfico para el sistema de caché")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--distribution", choices=["uniform", "zipf"], default="uniform")
    parser.add_argument("--metrics-url", default=None)
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    run(args.base_url, args.metrics_url, args.requests, args.distribution, args.sleep_ms, args.seed)


if __name__ == "__main__":
    main()
