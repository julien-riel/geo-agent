import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from geo_agent.models import DatasetMeta, LineageInfo, SourceInfo


def _infer_attribute_schema(geojson: dict) -> dict[str, str]:
    schema: dict[str, str] = {}
    for feat in geojson.get("features", []):
        for k, v in (feat.get("properties") or {}).items():
            if k in schema:
                continue
            if isinstance(v, bool):
                schema[k] = "boolean"
            elif isinstance(v, (int, float)):
                schema[k] = "number"
            elif v is None:
                continue
            else:
                schema[k] = "string"
    return schema


def _compute_bbox(geojson: dict) -> tuple[float, float, float, float]:
    minx = miny = float("inf")
    maxx = maxy = float("-inf")

    def walk(coords: Any) -> None:
        nonlocal minx, miny, maxx, maxy
        if isinstance(coords, (int, float)):
            return
        if (
            isinstance(coords, list)
            and len(coords) >= 2
            and all(isinstance(c, (int, float)) for c in coords[:2])
        ):
            x, y = coords[0], coords[1]
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
            return
        if isinstance(coords, list):
            for c in coords:
                walk(c)

    for feat in geojson.get("features", []):
        geom = feat.get("geometry") or {}
        walk(geom.get("coordinates"))

    if minx == float("inf"):
        return (0.0, 0.0, 0.0, 0.0)
    return (minx, miny, maxx, maxy)


class ResultStore(Protocol):
    def put(self, geojson: dict, meta_partial: dict) -> str: ...
    def get_geojson(self, id: str) -> dict: ...
    def get_meta(self, id: str) -> DatasetMeta: ...
    def list(self) -> list[DatasetMeta]: ...
    def delete(self, id: str) -> None: ...
    def update_alias(self, id: str, alias: str) -> None: ...


class FileSystemResultStore:
    def __init__(self, data_dir: Path) -> None:
        self._results_dir = data_dir / "results"
        self._sessions_dir = data_dir / "sessions"
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._counter_file = self._sessions_dir / "counter"

    def _next_id(self) -> str:
        existing = sorted(p.stem for p in self._results_dir.glob("result_*.geojson"))
        last = 0
        if existing:
            last = max(int(p.split("_")[1]) for p in existing)
        if self._counter_file.exists():
            last = max(last, int(self._counter_file.read_text().strip() or "0"))
        next_id = last + 1
        self._counter_file.write_text(str(next_id))
        return f"result_{next_id:03d}"

    def put(self, geojson: dict, meta_partial: dict) -> str:
        rid = self._next_id()
        gj_path = self._results_dir / f"{rid}.geojson"
        meta_path = self._results_dir / f"{rid}.json"

        gj_bytes = json.dumps(geojson).encode("utf-8")
        gj_path.write_bytes(gj_bytes)

        meta = DatasetMeta(
            id=rid,
            alias=meta_partial.get("alias"),
            source=SourceInfo(**meta_partial["source"]),
            feature_count=len(geojson.get("features", [])),
            bbox=_compute_bbox(geojson),
            attribute_schema=_infer_attribute_schema(geojson),
            lineage=LineageInfo(**meta_partial["lineage"]),
            created_at=datetime.now(timezone.utc),
            size_bytes=len(gj_bytes),
        )
        meta_path.write_text(meta.model_dump_json())
        return rid

    def _resolve_id(self, id_or_alias: str) -> str:
        """Return the canonical dataset id, accepting either the id or an alias."""
        direct = self._results_dir / f"{id_or_alias}.json"
        if direct.exists():
            return id_or_alias
        for p in self._results_dir.glob("result_*.json"):
            meta = DatasetMeta.model_validate_json(p.read_text())
            if meta.alias == id_or_alias:
                return meta.id
        raise FileNotFoundError(f"dataset {id_or_alias!r} not found (no id or alias match)")

    def get_geojson(self, id: str) -> dict:
        rid = self._resolve_id(id)
        return json.loads((self._results_dir / f"{rid}.geojson").read_text())

    def get_meta(self, id: str) -> DatasetMeta:
        rid = self._resolve_id(id)
        return DatasetMeta.model_validate_json(
            (self._results_dir / f"{rid}.json").read_text()
        )

    def list(self) -> list[DatasetMeta]:
        return [
            DatasetMeta.model_validate_json(p.read_text())
            for p in sorted(self._results_dir.glob("result_*.json"))
        ]

    def delete(self, id: str) -> None:
        (self._results_dir / f"{id}.geojson").unlink(missing_ok=True)
        (self._results_dir / f"{id}.json").unlink(missing_ok=True)

    def update_alias(self, id: str, alias: str) -> None:
        meta = self.get_meta(id)
        meta = meta.model_copy(update={"alias": alias})
        (self._results_dir / f"{id}.json").write_text(meta.model_dump_json())
