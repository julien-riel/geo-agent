from pathlib import Path

import pytest

from geo_agent.services.result_store import FileSystemResultStore


@pytest.fixture
def store(data_dir: Path) -> FileSystemResultStore:
    return FileSystemResultStore(data_dir=data_dir)


def _sample_geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-73.6, 45.5]},
                "properties": {"name": "A", "value": 1},
            }
        ],
    }


def test_put_returns_sequential_ids(store: FileSystemResultStore) -> None:
    id1 = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    id2 = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    assert id1 == "result_001"
    assert id2 == "result_002"


def test_put_writes_geojson_and_sidecar(store: FileSystemResultStore, data_dir: Path) -> None:
    rid = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "parcs", "filter_summary": "Within"}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}})
    assert (data_dir / "results" / f"{rid}.geojson").exists()
    assert (data_dir / "results" / f"{rid}.json").exists()


def test_get_geojson_round_trip(store: FileSystemResultStore) -> None:
    gj = _sample_geojson()
    rid = store.put(gj, {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    assert store.get_geojson(rid) == gj


def test_get_meta_includes_computed_fields(store: FileSystemResultStore) -> None:
    rid = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "parcs", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "select", "params": {}}})
    meta = store.get_meta(rid)
    assert meta.feature_count == 1
    assert meta.bbox == (-73.6, 45.5, -73.6, 45.5)
    assert meta.attribute_schema == {"name": "string", "value": "number"}
    assert meta.size_bytes > 0


def test_list_returns_all_datasets(store: FileSystemResultStore) -> None:
    rid1 = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "a", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    rid2 = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "b", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    items = store.list()
    assert {m.id for m in items} == {rid1, rid2}


def test_update_alias(store: FileSystemResultStore) -> None:
    rid = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    store.update_alias(rid, "my_alias")
    assert store.get_meta(rid).alias == "my_alias"


def test_delete_removes_files(store: FileSystemResultStore, data_dir: Path) -> None:
    rid = store.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    store.delete(rid)
    assert not (data_dir / "results" / f"{rid}.geojson").exists()
    assert not (data_dir / "results" / f"{rid}.json").exists()


def test_counter_persists_across_instances(data_dir: Path) -> None:
    s1 = FileSystemResultStore(data_dir=data_dir)
    s1.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    s2 = FileSystemResultStore(data_dir=data_dir)
    rid = s2.put(_sample_geojson(), {"source": {"type": "wfs", "layer": "x", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "test", "params": {}}})
    assert rid == "result_002"


def test_get_meta_resolves_alias_to_id(data_dir: Path) -> None:
    from geo_agent.services.result_store import FileSystemResultStore

    store = FileSystemResultStore(data_dir=data_dir)
    rid = store.put(
        {"type": "FeatureCollection", "features": []},
        {"alias": "zone_42", "source": {"type": "user_drawing", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}}},
    )
    by_id = store.get_meta(rid)
    by_alias = store.get_meta("zone_42")
    assert by_id == by_alias


def test_get_geojson_resolves_alias_to_id(data_dir: Path) -> None:
    from geo_agent.services.result_store import FileSystemResultStore

    store = FileSystemResultStore(data_dir=data_dir)
    gj = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}]}
    store.put(
        gj,
        {"alias": "zone_99", "source": {"type": "user_drawing", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}}},
    )
    loaded = store.get_geojson("zone_99")
    assert loaded["features"][0]["geometry"]["coordinates"] == [0, 0]


def test_get_meta_unknown_raises_filenotfounderror(data_dir: Path) -> None:
    import pytest

    from geo_agent.services.result_store import FileSystemResultStore

    store = FileSystemResultStore(data_dir=data_dir)
    with pytest.raises(FileNotFoundError):
        store.get_meta("nonexistent_id_or_alias")


def test_delete_resolves_alias_to_id(data_dir: Path) -> None:
    from geo_agent.services.result_store import FileSystemResultStore

    store = FileSystemResultStore(data_dir=data_dir)
    rid = store.put(
        {"type": "FeatureCollection", "features": []},
        {"alias": "zone_to_delete", "source": {"type": "user_drawing", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}}},
    )

    store.delete("zone_to_delete")

    with pytest.raises(FileNotFoundError):
        store.get_meta(rid)


def test_update_alias_resolves_alias_to_id(data_dir: Path) -> None:
    from geo_agent.services.result_store import FileSystemResultStore

    store = FileSystemResultStore(data_dir=data_dir)
    rid = store.put(
        {"type": "FeatureCollection", "features": []},
        {"alias": "old_alias", "source": {"type": "user_drawing", "filter_summary": ""}, "lineage": {"parent_ids": [], "operation": "user_drawing", "params": {}}},
    )

    store.update_alias("old_alias", "new_alias")

    meta = store.get_meta(rid)
    assert meta.alias == "new_alias"
    # No sidecar file should have been created at <alias>.json
    assert not (data_dir / "results" / "old_alias.json").exists()
    assert not (data_dir / "results" / "new_alias.json").exists()
