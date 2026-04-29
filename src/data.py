from __future__ import annotations

import csv
import gzip
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from src.config import ZONES

DATASET_URL = "https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_4_gzip/967_buildings.csv.gz"
DEFAULT_DATASET_FILENAME = "967_buildings.csv"
PROGRESS_LOG_SECONDS = 30.0
_CHUNK_SIZE = 256 * 1024  # 256 KB chunks for download progress

_logger = logging.getLogger("uvicorn.error")

# Estado compartido para que /health pueda informar la fase del loader.
loader_status: Dict[str, object] = {
    "phase": "idle",       # idle | downloading | parsing | ready | error
    "detail": None,        # mensaje legible
    "error": None,         # str del error si falló
}


@dataclass(frozen=True)
class BuildingRecord:
    latitude: float
    longitude: float
    area_in_meters: float
    confidence: float


def _default_dataset_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "data" / DEFAULT_DATASET_FILENAME


def _download_and_extract(url: str, dest_path: Path) -> None:
    """Descarga el .csv.gz y lo extrae a CSV plano con logging de progreso."""
    from urllib.request import urlopen, Request

    loader_status["phase"] = "downloading"
    loader_status["detail"] = "Iniciando descarga"

    _logger.info("Descargando dataset desde %s", url)
    req = Request(url)
    response = urlopen(req)

    total_size = int(response.headers.get("Content-Length", 0))
    total_mb_str = f"/ {total_size / 1e6:.1f} MB" if total_size else ""

    downloaded = 0
    decompressed = 0
    start = time.monotonic()
    last_log = start

    # Leemos comprimido en chunks, descomprimimos, y escribimos el CSV plano.
    decompressor = gzip.GzipFile(fileobj=response)
    with dest_path.open("wb") as out:
        while True:
            chunk = decompressor.read(_CHUNK_SIZE)
            if not chunk:
                break
            out.write(chunk)
            decompressed += len(chunk)
            # Estimamos downloaded basándonos en ratio de compresión (~4:1 aprox)
            # pero lo relevante es el decompressed que es lo que tenemos exacto.

            now = time.monotonic()
            if now - last_log >= PROGRESS_LOG_SECONDS:
                elapsed = now - start
                speed = decompressed / elapsed / 1e6 if elapsed > 0 else 0
                detail = f"Descomprimido: {decompressed / 1e6:.1f} MB, velocidad: {speed:.1f} MB/s, elapsed: {elapsed:.0f}s"
                loader_status["detail"] = detail
                _logger.info("Descarga en progreso: %s", detail)
                last_log = now

    elapsed = time.monotonic() - start
    _logger.info(
        "Descarga completada: %.1f MB descomprimidos en %.1fs -> %s",
        decompressed / 1e6,
        elapsed,
        dest_path,
    )


def _ensure_dataset(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        _logger.info("Dataset encontrado en %s (%d bytes), saltando descarga", path, path.stat().st_size)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _download_and_extract(DATASET_URL, path)
    except Exception as exc:
        if path.exists():
            path.unlink()
        raise RuntimeError(f"Error descargando dataset desde {DATASET_URL}") from exc


def _zone_for_point(latitude: float, longitude: float) -> str | None:
    for zone_id, zone in ZONES.items():
        if zone["lat_min"] <= latitude <= zone["lat_max"] and zone["lon_min"] <= longitude <= zone["lon_max"]:
            return zone_id
    return None


def load_dataset(dataset_path: str | None = None) -> Dict[str, List[BuildingRecord]]:
    """Carga el CSV real; si no existe, lo descarga desde Open Buildings."""
    try:
        path = Path(dataset_path) if dataset_path else _default_dataset_path()
        _ensure_dataset(path)

        loader_status["phase"] = "parsing"
        loader_status["detail"] = "Iniciando parseo"

        data: Dict[str, List[BuildingRecord]] = {zone_id: [] for zone_id in ZONES}
        file_size = path.stat().st_size
        start = time.monotonic()
        last_log = start
        last_rows = 0
        rows = 0
        matched = 0
        _logger.info("Cargando dataset desde %s (%d bytes)", path, file_size)
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows += 1
                try:
                    latitude = float(row["latitude"])
                    longitude = float(row["longitude"])
                    area_in_meters = float(row["area_in_meters"])
                    confidence = float(row["confidence"])
                except (KeyError, ValueError) as exc:
                    raise RuntimeError("CSV no contiene columnas esperadas") from exc

                zone_id = row.get("zone_id")
                if zone_id not in data:
                    zone_id = _zone_for_point(latitude, longitude)
                if zone_id is None:
                    continue

                matched += 1
                data[zone_id].append(
                    BuildingRecord(
                        latitude=latitude,
                        longitude=longitude,
                        area_in_meters=area_in_meters,
                        confidence=confidence,
                    )
                )

                now = time.monotonic()
                if now - last_log >= PROGRESS_LOG_SECONDS:
                    delta_rows = rows - last_rows
                    delta_time = max(now - last_log, 1e-6)
                    detail = f"rows={rows} matched={matched} rows_per_sec={delta_rows / delta_time:.0f} elapsed={now - start:.0f}s"
                    loader_status["detail"] = detail
                    _logger.info("Dataset load progress: %s", detail)
                    last_log = now
                    last_rows = rows

        elapsed = time.monotonic() - start
        _logger.info(
            "Dataset cargado: rows=%d matched=%d elapsed=%.1fs",
            rows,
            matched,
            elapsed,
        )
        for zid, records in data.items():
            _logger.info("  Zona %s: %d edificios", zid, len(records))

        loader_status["phase"] = "ready"
        loader_status["detail"] = f"Listo: {matched} edificios en {elapsed:.0f}s"
        loader_status["error"] = None
        return data

    except Exception as exc:
        loader_status["phase"] = "error"
        loader_status["error"] = str(exc)
        loader_status["detail"] = str(exc)
        raise
