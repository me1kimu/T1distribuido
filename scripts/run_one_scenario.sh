#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 7 ]]; then
  echo "Uso: $0 <name> <max_memory> <policy> <requests> <distribution> <sleep_ms> <cache_ttl>" >&2
  exit 1
fi

name="$1"
max_memory="$2"
policy="$3"
requests="$4"
distribution="$5"
sleep_ms="$6"
cache_ttl="$7"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p results

cat > docker-compose.override.yml <<EOF
services:
  redis:
    command: ["redis-server", "--maxmemory", "${max_memory}", "--maxmemory-policy", "${policy}"]
  cache-service:
    environment:
      - PYTHONPATH=/app
      - REDIS_URL=redis://redis:6379/0
      - RESPONSE_SERVICE_URL=http://response-service:8002
      - METRICS_SERVICE_URL=http://metrics-service:8001
      - CACHE_TTL=${cache_ttl}
  traffic-generator:
    command: ["python", "-m", "src.traffic_generator", "--base-url", "http://cache-service:8000", "--metrics-url", "http://metrics-service:8001/summary", "--requests", "${requests}", "--distribution", "${distribution}", "--sleep-ms", "${sleep_ms}", "--seed", "7"]
EOF

echo "=== Scenario ${name} ==="
docker compose down >/dev/null 2>&1 || true
docker compose up --build -d redis metrics-service response-service cache-service >/dev/null

for _ in $(seq 1 240); do
  status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' t1distribuido-cache-service-1 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 5
done

status="$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' t1distribuido-cache-service-1 2>/dev/null || echo missing)"
if [[ "$status" != "healthy" ]]; then
  echo "cache-service no saludable, estado=$status" >&2
  docker compose ps >&2
  exit 1
fi

docker compose run --build --rm traffic-generator >"/tmp/${name}_traffic.log"
curl -s http://localhost:8001/summary >"results/${name}.json"
cat "results/${name}.json"
