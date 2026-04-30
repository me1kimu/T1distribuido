#!/usr/bin/env pwsh
# benchmark.ps1 — Ejecuta todas las campañas experimentales y guarda métricas en results/

$ErrorActionPreference = "Continue"
$ResultsDir = "$PSScriptRoot\results"
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null

function Run-Scenario {
    param(
        [string]$Name,
        [string]$MaxMemory,
        [string]$Policy,
        [int]$Requests,
        [string]$Distribution,
        [int]$SleepMs,
        [int]$CacheTTL
    )

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  Scenario: $Name" -ForegroundColor Cyan
    Write-Host "  MaxMemory=$MaxMemory Policy=$Policy Dist=$Distribution Requests=$Requests SleepMs=$SleepMs TTL=$CacheTTL" -ForegroundColor Cyan
    Write-Host "========================================`n" -ForegroundColor Cyan

    # Detener contenedores en ejecución
    docker compose down --volumes 2>$null

    # Escribir archivo de override temporal
    $override = @"
services:
  redis:
    command: ["redis-server", "--maxmemory", "$MaxMemory", "--maxmemory-policy", "$Policy"]
  cache-service:
    environment:
      - PYTHONPATH=/app
      - REDIS_URL=redis://redis:6379/0
      - RESPONSE_SERVICE_URL=http://response-service:8002
      - METRICS_SERVICE_URL=http://metrics-service:8001
      - CACHE_TTL=$CacheTTL
  traffic-generator:
    command: ["python", "-m", "src.traffic_generator", "--base-url", "http://cache-service:8000", "--metrics-url", "http://metrics-service:8001/summary", "--requests", "$Requests", "--distribution", "$Distribution", "--sleep-ms", "$SleepMs", "--seed", "7"]
"@
    $override | Out-File -Encoding utf8 -FilePath "$PSScriptRoot\docker-compose.override.yml"

    # Iniciar servicios (sin traffic generator, dejar que el dataset se descargue)
    docker compose up -d redis metrics-service response-service cache-service

    # Esperar a que cache-service esté saludable
    Write-Host "Esperando a que los servicios estén listos..."
    $maxWait = 300
    $waited = 0
    while ($waited -lt $maxWait) {
        $health = docker inspect --format='{{.State.Health.Status}}' t1distribuido-cache-service-1 2>$null
        if ($health -eq "healthy") { break }
        Start-Sleep -Seconds 5
        $waited += 5
        Write-Host "  ...esperando ($waited s, cache-service: $health)"
    }
    if ($waited -ge $maxWait) {
        Write-Host "ERROR: Los servicios no se iniciaron a tiempo" -ForegroundColor Red
        docker compose logs
        docker compose down
        return
    }
    Write-Host "Todos los servicios listos!" -ForegroundColor Green

    # Ejecutar generador de tráfico
    Write-Host "Ejecutando generador de tráfico..."
    docker compose run --rm traffic-generator

    # Capturar métricas
    Write-Host "Capturando métricas..."
    $metrics = Invoke-RestMethod -Uri "http://localhost:8001/summary" -Method Get
    $metricsJson = $metrics | ConvertTo-Json -Depth 5
    $metricsJson | Out-File -Encoding utf8 -FilePath "$ResultsDir\$Name.json"
    Write-Host "Métricas guardadas en results\$Name.json" -ForegroundColor Green
    Write-Host $metricsJson

    # Detener contenedores (mantener volumen dataset)
    docker compose down
}

# ============================================================
# Campaña A: Comparación de distribución (LRU, 200MB, TTL=300)
# ============================================================
Run-Scenario -Name "dist_uniform_lru_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "uniform" -SleepMs 0 -CacheTTL 300
Run-Scenario -Name "dist_zipf_lru_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300

# ============================================================
# Campaña A: Comparación de política de remoción (Zipf, 200MB, TTL=300)
# ============================================================
Run-Scenario -Name "policy_lru_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300
Run-Scenario -Name "policy_lfu_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-lfu" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300
Run-Scenario -Name "policy_random_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-random" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300

# ============================================================
# Campaña A: Comparación de tamaño de caché (LRU, Zipf, TTL=300)
# ============================================================
Run-Scenario -Name "size_50mb_lru_zipf" -MaxMemory "50mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300
Run-Scenario -Name "size_200mb_lru_zipf" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300
Run-Scenario -Name "size_500mb_lru_zipf" -MaxMemory "500mb" -Policy "allkeys-lru" -Requests 4000 -Distribution "zipf" -SleepMs 0 -CacheTTL 300

# ============================================================
# Campaña B: Sensibilidad de TTL (Zipf, 200MB, LRU, 50ms delay)
# ============================================================
Run-Scenario -Name "ttl_5s_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 1200 -Distribution "zipf" -SleepMs 50 -CacheTTL 5
Run-Scenario -Name "ttl_20s_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 1200 -Distribution "zipf" -SleepMs 50 -CacheTTL 20
Run-Scenario -Name "ttl_120s_zipf_200mb" -MaxMemory "200mb" -Policy "allkeys-lru" -Requests 1200 -Distribution "zipf" -SleepMs 50 -CacheTTL 120

# Limpiar archivo de override
Remove-Item -Path "$PSScriptRoot\docker-compose.override.yml" -ErrorAction SilentlyContinue

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Todos los escenarios completados!" -ForegroundColor Green
Write-Host "  Resultados en: $ResultsDir" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
