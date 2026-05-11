from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from geo_agent.agent.registry import Services, _services
from geo_agent.agent.tools.list_wfs_layers import list_wfs_layers
from geo_agent.config import Settings
from geo_agent.models import WFSLayer
from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def services_with_mock_wfs(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Services:
    settings = Settings(DATA_DIR=data_dir)
    wfs_mock = AsyncMock()
    wfs_mock.get_layers.return_value = [
        WFSLayer(name="montreal:parcs", title="Parcs", default_crs="EPSG:4326"),
        WFSLayer(name="montreal:chaussees", title="Chaussées", abstract="Routes", default_crs="EPSG:4326"),
    ]
    services = Services(settings=settings, wfs=wfs_mock, store=FileSystemResultStore(data_dir=data_dir))
    monkeypatch.setattr("geo_agent.agent.tools.list_wfs_layers.get_services", lambda: services)
    return services


async def test_list_wfs_layers_returns_summary(services_with_mock_wfs: Services) -> None:
    result = await list_wfs_layers.ainvoke({})

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "montreal:parcs"
    assert "title" in result[0]
    assert "abstract" in result[1]


async def test_list_wfs_layers_includes_abstract(monkeypatch: pytest.MonkeyPatch) -> None:
    from geo_agent.agent.registry import Services
    from geo_agent.agent.tools import list_wfs_layers as mod
    from geo_agent.config import Settings
    from geo_agent.models import WFSLayer
    from unittest.mock import AsyncMock

    wfs_mock = AsyncMock()
    wfs_mock.get_layers.return_value = [
        WFSLayer(
            name="montreal:parcs",
            title="Parcs",
            abstract="Parcs et espaces verts de la Ville",
            default_crs="EPSG:4326",
        ),
    ]
    services = Services(settings=Settings(), wfs=wfs_mock, store=None)  # type: ignore[arg-type]
    monkeypatch.setattr("geo_agent.agent.tools.list_wfs_layers.get_services", lambda: services)

    out = await mod.list_wfs_layers.coroutine()

    assert out == [{"name": "montreal:parcs", "title": "Parcs", "abstract": "Parcs et espaces verts de la Ville"}]
