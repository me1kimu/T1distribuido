from io import BytesIO
import gzip
import time
import urllib.request

import pytest

from src import data as data_module
from src.config import ZONES


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._buffer = BytesIO(payload)
        self.headers = {}
        self.status = 206

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


class SequencedUrlopen:
    def __init__(self, first_payload: bytes, second_payload: bytes) -> None:
        self.first_payload = first_payload
        self.second_payload = second_payload
        self.calls = 0

    def __call__(self, request, timeout=None):
        self.calls += 1
        if self.calls == 1:
            assert request.headers.get("Range") is None
            return FakeResponse(self.first_payload)

        assert request.headers.get("Range") == f"bytes={len(self.first_payload)}-"
        return FakeResponse(self.second_payload)


def _gzip_csv_bytes() -> bytes:
    csv_text = (
        "latitude,longitude,area_in_meters,confidence\n"
        "-33.43,-70.62,100.0,0.9\n"
    )
    return gzip.compress(csv_text.encode("utf-8"))


def test_load_dataset_resumes_partial_download_after_low_speed_failure(monkeypatch, tmp_path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_file = dataset_dir / "967_buildings.csv"
    gz_file = dataset_dir / "967_buildings.csv.gz"
    part_file = dataset_dir / "967_buildings.csv.gz.part"

    monkeypatch.setattr(data_module, "DATASET_DIR", dataset_dir)
    monkeypatch.setattr(data_module, "DATASET_FILE", dataset_file)
    monkeypatch.setattr(data_module, "DATASET_GZ_FILE", gz_file)
    monkeypatch.setattr(data_module, "DATASET_GZ_PART_FILE", part_file)

    gz_bytes = _gzip_csv_bytes()
    first_payload = gz_bytes[: len(gz_bytes) // 2]
    second_payload = gz_bytes[len(gz_bytes) // 2 :]
    monkeypatch.setattr(urllib.request, "urlopen", SequencedUrlopen(first_payload, second_payload))

    real_perf_counter = time.perf_counter
    slow_times = iter([0.0, 60.0])
    monkeypatch.setattr(data_module.time, "perf_counter", lambda: next(slow_times))

    with pytest.raises(data_module.DatasetDownloadTooSlowError):
        data_module.load_dataset()

    assert gz_file.exists()
    assert not dataset_file.exists()

    monkeypatch.setattr(data_module.time, "perf_counter", real_perf_counter)

    data = data_module.load_dataset()

    assert set(data) == set(ZONES)
    assert len(data["Z1"]) == 1
    assert data["Z1"][0].area_in_meters == 100.0
    assert gz_file.exists()
    assert not part_file.exists()
    assert dataset_file.exists()