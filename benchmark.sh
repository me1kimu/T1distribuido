#!/usr/bin/env bash
# benchmark.sh — Ejecuta todas las campañas experimentales y guarda métricas en results/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
RESULTS_DIR="$PROJECT_DIR/results"
mkdir -p "$RESULTS_DIR"
cd "$PROJECT_DIR"

run_scenario() {
    local name="$1"
    local max_memory="$2"
    local policy="$3"
    local requests="$4"
    local distribution="$5"
    local sleep_ms="$6"
    local cache_ttl="$7"

    echo ""
    echo "========================================"
    echo "  Escenario: $name"
    echo "  MaxMemory=$max_memory Policy=$policy Dist=$distribution Requests=$requests SleepMs=$sleep_ms TTL=$cache_ttl"
    echo "========================================"
    echo ""

    # Detener contenedores en ejecución
    docker.exe compose down --volumes 2>/dev/null || true

    # Escribir archivo de override temporal (via /tmp para evitar CRLF de NTFS)
    local override_file="$PROJECT_DIR/docker-compose.override.yml"
    printf 'services:\n  redis:\n    command: ["redis-server", "--maxmemory", "%s", "--maxmemory-policy", "%s"]\n  cache-service:\n    environment:\n      - PYTHONPATH=/app\n      - REDIS_URL=redis://redis:6379/0\n      - RESPONSE_SERVICE_URL=http://response-service:8002\n      - METRICS_SERVICE_URL=http://metrics-service:8001\n      - CACHE_TTL=%s\n  traffic-generator:\n    command: ["python", "-m", "src.traffic_generator", "--base-url", "http://cache-service:8000", "--metrics-url", "http://metrics-service:8001/summary", "--requests", "%s", "--distribution", "%s", "--sleep-ms", "%s", "--seed", "7"]\n' "$max_memory" "$policy" "$cache_ttl" "$requests" "$distribution" "$sleep_ms" > /tmp/docker-compose.override.yml
    cp /tmp/docker-compose.override.yml "$override_file"

    # Iniciar servicios (sin traffic generator, dejar que el dataset se descargue)
    docker.exe compose up -d redis metrics-service response-service cache-service

    # Esperar a que cache-service esté saludable
    echo "Esperando a que los servicios estén listos..."
    local max_wait=300
    local waited=0
    while [ $waited -lt $max_wait ]; do
        health=$(docker.exe inspect --format='{{.State.Health.Status}}' t1distribuido-cache-service-1 2>/dev/null || echo "starting")
        if [ "$health" = "healthy" ]; then
            break
        fi
        sleep 5
        waited=$((waited + 5))
        echo "  ...esperando (${waited}s, cache-service: $health)"
    done

    if [ $waited -ge $max_wait ]; then
        echo "ERROR: Los servicios no se iniciaron a tiempo"
        docker.exe compose logs
        docker.exe compose down
        return
    fi
    echo "Todos los servicios listos!"

    # Ejecutar generador de tráfico
    echo "Ejecutando generador de tráfico..."
    docker.exe compose run --rm traffic-generator

    # Capturar métricas
    echo "Capturando métricas..."
    curl -s http://localhost:8001/summary | tee "$RESULTS_DIR/$name.json"
    echo ""
    echo "Métricas guardadas en results/$name.json"

    # Detener contenedores (mantener volumen dataset)
    docker.exe compose down
}

# ============================================================
# Campaña A: Comparación de distribución (LRU, 200MB, TTL=300)
# ============================================================
run_scenario "dist_uniform_lru_200mb" "200mb" "allkeys-lru" 4000 "uniform" 0 300
run_scenario "dist_zipf_lru_200mb" "200mb" "allkeys-lru" 4000 "zipf" 0 300

# ============================================================
# Campaña A: Comparación de política de remoción (Zipf, 200MB, TTL=300)
# ============================================================
run_scenario "policy_lru_zipf_200mb" "200mb" "allkeys-lru" 4000 "zipf" 0 300
run_scenario "policy_lfu_zipf_200mb" "200mb" "allkeys-lfu" 4000 "zipf" 0 300
run_scenario "policy_random_zipf_200mb" "200mb" "allkeys-random" 4000 "zipf" 0 300

# ============================================================
# Campaña A: Comparación de tamaño de caché (LRU, Zipf, TTL=300)
# ============================================================
run_scenario "size_50mb_lru_zipf" "50mb" "allkeys-lru" 4000 "zipf" 0 300
run_scenario "size_200mb_lru_zipf" "200mb" "allkeys-lru" 4000 "zipf" 0 300
run_scenario "size_500mb_lru_zipf" "500mb" "allkeys-lru" 4000 "zipf" 0 300

# ============================================================
# Campaña B: Sensibilidad de TTL (Zipf, 200MB, LRU, 50ms delay)
# ============================================================
run_scenario "ttl_5s_zipf_200mb" "200mb" "allkeys-lru" 1200 "zipf" 50 5
run_scenario "ttl_20s_zipf_200mb" "200mb" "allkeys-lru" 1200 "zipf" 50 20
run_scenario "ttl_120s_zipf_200mb" "200mb" "allkeys-lru" 1200 "zipf" 50 120

# Limpiar archivo de override
rm -f "$PROJECT_DIR/docker-compose.override.yml"

echo ""
echo "========================================"
echo "  Todos los escenarios completados!"
echo "  Resultados en: $RESULTS_DIR"
echo "========================================"
