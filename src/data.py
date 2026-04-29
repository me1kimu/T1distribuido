from __future__ import annotations

import csv
import gzip
import logging
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from src.config import ZONES

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATASET_URL = "https://storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_4_gzip/967_buildings.csv.gz"
DATASET_DIR = Path("/app/dataset")
DATASET_FILE = DATASET_DIR / "967_buildings.csv"
DATASET_GZ_FILE = DATASET_DIR / "967_buildings.csv.gz"
DATASET_GZ_PART_FILE = DATASET_DIR / "967_buildings.csv.gz.part"
DOWNLOAD_SOCKET_TIMEOUT_SECONDS = 50
DOWNLOAD_MIN_OBSERVATION_SECONDS = 50.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MIN_AVERAGE_DOWNLOAD_BITS_PER_SECOND = 1_000_000


class DatasetDownloadError(RuntimeError):
    pass


class DatasetDownloadTooSlowError(DatasetDownloadError):
    pass


@dataclass(frozen=True)
class BuildingRecord:
    latitude: float
    longitude: float
    area_in_meters: float
    confidence: float


def _assign_zone(lat: float, lon: float) -> str | None:
    """Devuelve el zone_id cuyo bounding box contiene (lat, lon), o None."""
    for zone_id, zone in ZONES.items():
        if (
            zone["lat_min"] <= lat <= zone["lat_max"]
            and zone["lon_min"] <= lon <= zone["lon_max"]
        ):
            return zone_id
    return None


def _download_dataset() -> None:
    """Descarga y extrae el .csv.gz en DATASET_DIR si aún no existe."""
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    if DATASET_FILE.exists():
        logger.info("Dataset ya presente en %s, omitiendo descarga.", DATASET_FILE)
        return

    if DATASET_GZ_FILE.exists() and not DATASET_GZ_PART_FILE.exists():
        DATASET_GZ_FILE.replace(DATASET_GZ_PART_FILE)

    download_path = DATASET_GZ_PART_FILE if DATASET_GZ_PART_FILE.exists() else DATASET_GZ_FILE
    if not download_path.exists():
        logger.info("Descargando dataset desde %s …", DATASET_URL)
    else:
        logger.info("Reanudando descarga del dataset desde %s bytes …", download_path.stat().st_size)

    starting_bytes = download_path.stat().st_size if download_path.exists() else 0
    request = urllib.request.Request(DATASET_URL)
    if starting_bytes:
        request.add_header("Range", f"bytes={starting_bytes}-")

    started_at = time.perf_counter()
    downloaded_this_attempt = 0
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_SOCKET_TIMEOUT_SECONDS) as response:
            with download_path.open("ab" if starting_bytes else "wb") as out_file:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break

                    out_file.write(chunk)
                    downloaded_this_attempt += len(chunk)
                    elapsed_seconds = time.perf_counter() - started_at
                    if elapsed_seconds >= DOWNLOAD_MIN_OBSERVATION_SECONDS:
                        average_bits_per_second = (downloaded_this_attempt * 8) / elapsed_seconds
                        if average_bits_per_second < MIN_AVERAGE_DOWNLOAD_BITS_PER_SECOND:
                            raise DatasetDownloadTooSlowError(
                                "La velocidad media de descarga del dataset es menor a 1 Mbps"
                            )
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and download_path.exists():
            logger.info("La descarga reanudable ya no tiene más bytes pendientes; verificando archivo local.")
        else:
            raise DatasetDownloadError(f"No se pudo descargar el dataset: {exc}") from exc

    try:
        _extract_gz(download_path, DATASET_FILE)
    except Exception as exc:
        raise DatasetDownloadError("No se pudo extraer el dataset descargado") from exc

    if download_path != DATASET_GZ_FILE:
        download_path.replace(DATASET_GZ_FILE)
    logger.info("Dataset disponible en %s.", DATASET_FILE)


def _extract_gz(gz_path: Path, csv_path: Path) -> None:
    with gzip.open(gz_path, "rb") as f_in, csv_path.open("wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def _load_csv(path: Path) -> Dict[str, List[BuildingRecord]]:
    """Lee el CSV de Open Buildings y agrupa los registros por zona."""
    data: Dict[str, List[BuildingRecord]] = {zone_id: [] for zone_id in ZONES}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
                area = float(row["area_in_meters"])
                conf = float(row["confidence"])
            except (KeyError, ValueError):
                continue
            zone_id = _assign_zone(lat, lon)
            if zone_id is None:
                continue
            data[zone_id].append(BuildingRecord(lat, lon, area, conf))
    return data


def load_dataset() -> Dict[str, List[BuildingRecord]]:
    """Descarga (si es necesario) y carga el dataset de Open Buildings."""
    _download_dataset()
    if not DATASET_FILE.exists():
        raise DatasetDownloadError("El dataset no quedó disponible después de la descarga")

    data = _load_csv(DATASET_FILE)
    total = sum(len(v) for v in data.values())
    if total == 0:
        raise DatasetDownloadError("El CSV de Open Buildings no contiene registros en las zonas configuradas")

    logger.info("Dataset cargado: %d registros distribuidos en %d zonas.", total, len(data))
    return data
