from __future__ import annotations

from dataclasses import dataclass

from geo_agent.config import Settings
from geo_agent.services.result_store import FileSystemResultStore, ResultStore
from geo_agent.services.wfs_client import WFSClient


@dataclass
class Services:
    settings: Settings
    wfs: WFSClient
    store: ResultStore


_services: Services | None = None


def init_services(settings: Settings) -> Services:
    global _services
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    _services = Services(
        settings=settings,
        wfs=WFSClient(
            base_url=settings.WFS_BASE_URL,
            cache_dir=settings.DATA_DIR,
            http_timeout_seconds=settings.WFS_HTTP_TIMEOUT_SECONDS,
        ),
        store=FileSystemResultStore(data_dir=settings.DATA_DIR),
    )
    return _services


def get_services() -> Services:
    if _services is None:
        raise RuntimeError("Services not initialized. Call init_services() first.")
    return _services
