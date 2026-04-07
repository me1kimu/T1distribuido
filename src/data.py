from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from src.config import ZONES


@dataclass(frozen=True)
class BuildingRecord:
    latitude: float
    longitude: float
    area_in_meters: float
    confidence: float


def _generate_synthetic_records(seed: int = 42, records_per_zone: int = 1000) -> Dict[str, List[BuildingRecord]]:
    rng = random.Random(seed)
    data: Dict[str, List[BuildingRecord]] = {}
    for zone_id, zone in ZONES.items():
        rows: List[BuildingRecord] = []
        for _ in range(records_per_zone):
            rows.append(
                BuildingRecord(
                    latitude=rng.uniform(zone["lat_min"], zone["lat_max"]),
                    longitude=rng.uniform(zone["lon_min"], zone["lon_max"]),
                    area_in_meters=rng.uniform(30.0, 600.0),
                    confidence=rng.uniform(0.2, 1.0),
                )
            )
        data[zone_id] = rows
    return data


def load_dataset(dataset_path: str | None = None) -> Dict[str, List[BuildingRecord]]:
    if not dataset_path:
        return _generate_synthetic_records()

    path = Path(dataset_path)
    if not path.exists():
        return _generate_synthetic_records()

    data: Dict[str, List[BuildingRecord]] = {zone_id: [] for zone_id in ZONES}
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            zone_id = row.get("zone_id", "")
            if zone_id not in data:
                continue
            data[zone_id].append(
                BuildingRecord(
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    area_in_meters=float(row["area_in_meters"]),
                    confidence=float(row["confidence"]),
                )
            )

    if any(len(rows) == 0 for rows in data.values()):
        return _generate_synthetic_records()

    return data
