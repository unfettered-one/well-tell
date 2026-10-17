import asyncio
import json
import sqlite3

import httpx
import pytest
from pydantic import ValidationError

from backend.api import create_app
from backend.visuals import Visual
from eval import check_case


@pytest.mark.parametrize("kind", ["status_card", "table", "line", "bar", "map", "heatmap"])
def test_all_visuals_accept_explicit_mappings_and_missing_values(kind):
    spec = {"type": kind, "data": [{"asset": "WELL-0001", "date": "2026-10-15", "value": None, "lat": 32.1, "lon": -102.1}],
            "columns": [{"field": "asset", "label": "Well"}]}
    if kind in ("line", "bar"):
        spec.update(x={"field": "date", "format": "date"}, y=[{"field": "value", "unit": "°C"}])
    elif kind == "map":
        spec.update(latitude="lat", longitude="lon", well_id="asset")
    elif kind == "heatmap":
        spec.update(row={"field": "asset"}, column={"field": "date"}, value={"field": "value"})
    assert Visual.model_validate(spec).data[0]["value"] is None
    spec["data"] = []
    assert Visual.model_validate(spec).data == []


def test_visuals_preserve_legacy_contract_and_validate_new_metadata():
    assert Visual.model_validate({"type": "bar", "data": [{"well": "A", "days": 3}]}).x is None
    assert Visual.model_validate({"type": "bar", "x": "well", "y": "days", "data": [{"well": "A", "days": 3}]}).y[0].field == "days"
    for field in ({"field": "invented"}, {"field": "days", "format": "execute"}, {"field": "days", "decimals": -1}):
        with pytest.raises(ValidationError):
            Visual.model_validate({"type": "bar", "x": {"field": "well"}, "y": [field], "data": [{"well": "A", "days": 3}]})


def test_health_metadata_is_sourced_from_each_dataset(db_copy):
    async def scenario():
        with sqlite3.connect(db_copy) as conn:
            expected = conn.execute("SELECT user_id,name,role FROM users WHERE dataset_id='sample' ORDER BY name,user_id").fetchall()
            as_of = conn.execute("SELECT value FROM meta WHERE key='as_of_sample'").fetchone()[0]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_copy)), base_url="http://test") as client:
            response = await client.get("/health")
            dataset = next(d for d in response.json()["datasets"] if d["dataset_id"] == "sample")
            assert dataset["as_of"] == as_of
            assert [(u["user_id"], u["name"], u["role"]) for u in dataset["users"]] == expected
    asyncio.run(scenario())


def test_heatmap_eval_supports_both_mapping_contracts():
    from pathlib import Path
    capture = Path("data/eval-final-results.json")
    if not capture.exists():
        pytest.skip("Historical evaluation capture not present")
    response = next(r["response"] for r in json.loads(capture.read_text()) if r["case"] == "Q8")
    assert check_case("Q8", response, [], "heatmap") == []
    spec = response["visual"]
    spec.update(row={"field": spec.pop("y")}, column={"field": spec.pop("x")}, value={"field": spec["value"]})
    assert check_case("Q8", response, [], "heatmap") == []
