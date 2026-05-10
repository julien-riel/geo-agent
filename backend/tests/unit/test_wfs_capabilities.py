from pathlib import Path

from geo_agent.services.wfs_client import parse_capabilities


def test_parse_capabilities_extracts_layers() -> None:
    xml = (Path(__file__).parent.parent / "fixtures" / "wfs_capabilities_2.0.0.xml").read_bytes()
    layers = parse_capabilities(xml)

    assert len(layers) >= 2
    names = {l.name for l in layers}
    assert "montreal:chaussees" in names

    chaussees = next(l for l in layers if l.name == "montreal:chaussees")
    assert chaussees.title
    assert chaussees.default_crs.endswith("4326")
    assert chaussees.bbox is not None
    minx, miny, maxx, maxy = chaussees.bbox
    assert -75 < minx < -73 and 45 < miny < 46
