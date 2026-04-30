# T1 Distribuido — Entregable 1

Plataforma distribuida para consultas geoespaciales sobre Google Open Buildings (versión simplificada para la Región Metropolitana) con caché Redis y métricas de rendimiento.

## Componentes

1. **Traffic Generator** (`src/traffic_generator.py`)
2. **Cache Service** (`src/cache_service.py`)
3. **Response Service** (`src/response_service.py`)
4. **Metrics Service** (`src/metrics_service.py`)
5. **Redis** como backend de caché

## Consultas implementadas

- **Q1:** conteo de edificios en zona
- **Q2:** área promedio y total
- **Q3:** densidad por km²
- **Q4:** comparación de densidad entre zonas
- **Q5:** distribución de confianza

## Ejecución con Docker Compose

```bash
docker compose up -d --build redis metrics-service response-service cache-service --wait --wait-timeout 900
```

Servicios expuestos:
- Cache Service: `http://localhost:8000`
- Metrics Service: `http://localhost:8001`
- Response Service: `http://localhost:8002`

## Ejemplo de consulta

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query_type":"Q1","zone_id":"Z1","confidence_min":0.3}'
```

## Ejecución de pruebas

```bash
python -m pip install -r requirements.txt
pytest -q
```

## Notas

- El `Response Service` descarga automáticamente el dataset de Google Open Buildings (tile S2 `967_buildings.csv.gz`) desde GCS al iniciar. El archivo parcial y el `.csv.gz` final se guardan en el volumen Docker `dataset/` para poder reanudar descargas interrumpidas.
- Si la velocidad media de descarga cae por debajo de 1 Mbps antes de completar el archivo, el servicio falla sin generar datos alternativos y la siguiente ejecución reanuda desde lo ya descargado.
- El TTL de caché se configura con `CACHE_TTL`.
- La política de remoción configurada por defecto en `docker-compose.yml` es `allkeys-lru`.
