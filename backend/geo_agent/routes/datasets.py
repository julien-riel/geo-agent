from fastapi import APIRouter, HTTPException

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
