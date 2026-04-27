from __future__ import annotations

import math
from typing import Dict, TypedDict


class Zone(TypedDict):
    id: str
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


# Bounding boxes de las cinco zonas predefinidas de Santiago.
ZONES: Dict[str, Zone] = {
    "Z1": {"id": "Z1", "name": "Providencia", "lat_min": -33.445, "lat_max": -33.420, "lon_min": -70.640, "lon_max": -70.600},
    "Z2": {"id": "Z2", "name": "Las Condes", "lat_min": -33.420, "lat_max": -33.390, "lon_min": -70.600, "lon_max": -70.550},
    "Z3": {"id": "Z3", "name": "Maipú", "lat_min": -33.530, "lat_max": -33.490, "lon_min": -70.790, "lon_max": -70.740},
    "Z4": {"id": "Z4", "name": "Santiago Centro", "lat_min": -33.460, "lat_max": -33.430, "lon_min": -70.670, "lon_max": -70.630},
    "Z5": {"id": "Z5", "name": "Pudahuel", "lat_min": -33.470, "lat_max": -33.430, "lon_min": -70.810, "lon_max": -70.760},
}


def zone_area_km2(zone_id: str) -> float:
    # Area aproximada para normalizar densidad en Q3.
    zone = ZONES[zone_id]
    delta_lat = abs(zone["lat_max"] - zone["lat_min"])
    delta_lon = abs(zone["lon_max"] - zone["lon_min"])
    mid_lat = (zone["lat_min"] + zone["lat_max"]) / 2
    lat_km = 111.32 * delta_lat
    lon_km = 111.32 * math.cos(math.radians(mid_lat)) * delta_lon
    return max(lat_km * lon_km, 1e-6)


# Areas precalculadas para consultas de densidad.
ZONE_AREAS_KM2 = {zone_id: zone_area_km2(zone_id) for zone_id in ZONES}
