from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from geo_agent.agent.registry import get_services

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
def list_all() -> list[dict]:
    return [m.model_dump(mode="json") for m in get_services().store.list()]


@router.get("/{dataset_id}/meta")
def get_meta(dataset_id: str) -> dict:
    try:
        return get_services().store.get_meta(dataset_id).model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")


@router.get("/{dataset_id}/geojson")
def get_geojson(dataset_id: str) -> dict:
    try:
        return get_services().store.get_geojson(dataset_id)
    except FileNotFoundError:
        raise HTTPException(404, f"dataset {dataset_id} not found")


class DrawingPayload(BaseModel):
    polygon: dict


@router.post("/drawing")
def create_drawing(payload: DrawingPayload) -> dict:
    services = get_services()
    if payload.polygon.get("type") != "Polygon":
        raise HTTPException(400, "polygon must be a GeoJSON Polygon")

    existing_drawings = sum(
        1 for m in services.store.list() if m.lineage.operation == "user_drawing"
    )
    alias = f"zone_{existing_drawings + 1}"

    rid = services.store.put(
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "geometry": payload.polygon, "properties": {}}],
        },
        {
            "alias": alias,
            "source": {"type": "user_drawing", "filter_summary": "user-drawn polygon"},
            "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}},
        },
    )
    meta = services.store.get_meta(rid)
    return {
        "id": rid,
        "alias": meta.alias,
        "feature_count": meta.feature_count,
        "bbox": list(meta.bbox),
        "layer": None,
        "operation": "user_drawing",
    }
