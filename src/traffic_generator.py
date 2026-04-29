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
            "confidence_min": rng.choice([0.0, 0.3, 0.5]),
            "bins": 5,
        }

    return {
        "query_type": query_type,
        "zone_id": _pick_zone(distribution, rng),
        "confidence_min": rng.choice([0.0, 0.3, 0.5]),
        "bins": rng.choice([5, 10]),
    }


def _default_metrics_url(base_url: str) -> str:
    parsed = urlparse(base_url.rstrip("/"))
    host = parsed.hostname or parsed.netloc.split("@")[-1].split(":")[0]

    if host == "cache-service":
        host = "metrics-service"
    return urlunparse((parsed.scheme or "http", f"{host}:8001", "/summary", "", "", ""))


def _wait_for_dataset(health_url: str, timeout: int) -> None:
    """Espera hasta que el response-service reporte dataset_loaded=true."""
    print(f"Esperando que el dataset esté listo ({health_url}, timeout={timeout}s)...")
    start = time.monotonic()
    interval = 10  # segundos entre polls

    while True:
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            print(f"TIMEOUT: el dataset no estuvo listo en {timeout}s. Continuando de todas formas.")
            return

        try:
            resp = requests.get(health_url, timeout=5)
            if resp.ok:
                data = resp.json()
                loaded = data.get("dataset_loaded", False)
                status = data.get("dataset_status", "unknown")
                detail = data.get("dataset_detail", "")

                if loaded:
                    print(f"Dataset listo! (status={status}, detail={detail})")
                    return

                print(f"  [{elapsed:.0f}s] dataset_status={status} detail={detail}")

                if status == "error":
                    error = data.get("dataset_error", "desconocido")
                    print(f"ERROR: el dataset falló al cargar: {error}")
                    return
        except requests.RequestException as exc:
            print(f"  [{elapsed:.0f}s] health check falló: {exc}")

        time.sleep(interval)


def run(base_url: str, metrics_url: str | None, requests_n: int, distribution: str, sleep_ms: int, seed: int) -> None:
    # Envia trafico controlado y reporta metricas agregadas.
    rng = random.Random(seed)
    session = requests.Session()
    endpoint = f"{base_url.rstrip('/')}/query"

    ok = 0
    errors = 0
    by_type = Counter()
    started = time.perf_counter()

    for _ in range(requests_n):
        payload = _generate_query(distribution, rng)
        by_type[payload["query_type"]] += 1
        try:
            res = session.post(endpoint, json=payload, timeout=30)
            if res.ok:
                ok += 1
            else:
                errors += 1
        except requests.RequestException:
            errors += 1
        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000)

    elapsed = max(time.perf_counter() - started, 1e-6)
    print(f"Solicitudes enviadas: {requests_n}")
    print(f"Exitosas: {ok}")
    print(f"Errores: {errors}")
    print(f"Throughput observado: {ok / elapsed:.2f} req/s")
    print(f"Distribución por consulta: {dict(by_type)}")

    try:
        metrics_endpoint = metrics_url or _default_metrics_url(base_url)
        metrics = session.get(metrics_endpoint, timeout=5)
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
    parser.add_argument(
        "--wait-ready-url",
        default=None,
        help="URL del health endpoint del response-service. Si se provee, espera hasta que dataset_loaded=true.",
    )
    parser.add_argument(
        "--wait-ready-timeout",
        type=int,
        default=900,
        help="Timeout en segundos para esperar al dataset (default: 900 = 15 min).",
    )
    args = parser.parse_args()

    if args.wait_ready_url:
        _wait_for_dataset(args.wait_ready_url, args.wait_ready_timeout)

    run(args.base_url, args.metrics_url, args.requests, args.distribution, args.sleep_ms, args.seed)


if __name__ == "__main__":
    main()
