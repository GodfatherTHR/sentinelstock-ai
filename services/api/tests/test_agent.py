from __future__ import annotations

from app.agent import TOOLS, _status_from_query, execute_tool


class FakeRow:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_dump(self, mode: str = "python"):
        return dict(self.__dict__)


class FakeRepository:
    def __init__(self) -> None:
        self._inventory = [
            FakeRow(id="1", warehouse_id="w1", warehouse_name="Sylhet East", product_id="p1", sku="OIL-1L-SUN", product_name="Sunflower Oil 1L", category="Cooking Oil", quantity=1600, reserved=250, incoming=400, available_inventory=1750, average_daily_demand=420, days_of_inventory=3.8, safety_stock=1680, reorder_point=5040, stockout_probability=0.91, excess_inventory=0, inventory_risk="CRITICAL", unit_value=38, updated_at="2026-09-19T00:00:00Z"),
            FakeRow(id="2", warehouse_id="w2", warehouse_name="Rajshahi North", product_id="p2", sku="DAL-1KG-RED", product_name="Red Lentils 1kg", category="Staples", quantity=9600, reserved=430, incoming=1300, available_inventory=10470, average_daily_demand=310, days_of_inventory=33.2, safety_stock=1240, reorder_point=3720, stockout_probability=0.09, excess_inventory=0, inventory_risk="LOW", unit_value=22, updated_at="2026-09-19T00:00:00Z"),
        ]
        self._recommendations = [
            FakeRow(id="rec-1", approval_status="pending", expected_cost=100.0, recommended_quantity=10, product_name="Sunflower Oil 1L", warehouse_name="Sylhet East", sku="OIL-1L-SUN", urgency="HIGH", risk_score=0.9, confidence=0.9, forecast_demand=2940, current_inventory=1750, days_of_inventory=3.8, expected_stockout_probability=0.91, drivers=[], requires_human_approval=True, supplier_id="s1", supplier_name="PRAN-RFL Group", decision_type="RESTOCK", warehouse_id="w1", product_id="p1", created_at="2026-09-19T00:00:00Z", explanation={"what": "", "how_much": "", "when": "", "from_where": "", "why": "", "risk": "", "confidence": ""}),
            FakeRow(id="rec-2", approval_status="approved", expected_cost=200.0, recommended_quantity=20, product_name="UHT Milk 1L", warehouse_name="Dhaka Central", sku="MILK-1L-UHT", urgency="HIGH", risk_score=0.8, confidence=0.9, forecast_demand=3150, current_inventory=3120, days_of_inventory=6.9, expected_stockout_probability=0.8, drivers=[], requires_human_approval=True, supplier_id="s1", supplier_name="PRAN-RFL Group", decision_type="RESTOCK", warehouse_id="w2", product_id="p2", created_at="2026-09-19T00:00:00Z", explanation={"what": "", "how_much": "", "when": "", "from_where": "", "why": "", "risk": "", "confidence": ""}),
        ]

    def inventory(self):
        return self._inventory

    def recommendations(self):
        return self._recommendations

    def forecasts(self):
        return [FakeRow(warehouse_id="w1", product_id="p1", product_name="Sunflower Oil 1L", horizon="7d", predicted_demand=2940, lower_bound=2587, upper_bound=3293, confidence=0.9, model_name="baseline_demand_v1", model_version="phase1.1", generated_at="2026-09-19T00:00:00Z")]

    def vessels(self):
        return [FakeRow(mmsi=1, name="TEST", destination="NLRTM", speed_knots=7.3, nav_status_label="under way using engine", observed_at="2026-09-19T00:00:00Z", latitude=1.0, longitude=2.0, call_sign=None, imo=None, ship_type_label="cargo", draught=7.9, course_degrees=90.0)]

    def crop_indices(self):
        return [FakeRow(scene_id="S1", aoi_name="Punjab Wheat Belt", crop="wheat", observation_date="2026-08-30", ndvi_mean=0.64, ndvi_p10=0.4, ndvi_p90=0.8, health_score=0.68, cloud_pixel_percentage=1.0, valid_pixel_percentage=95.0)]


def test_tool_catalogue_stays_within_the_direct_render_limit():
    # Needle renders five tools directly; more would switch to retrieval.
    assert len(TOOLS) <= 5
    assert {tool["name"] for tool in TOOLS} == {
        "inventory_risk",
        "recommendation_queue",
        "demand_forecast",
        "maritime_watch",
        "crop_health",
    }


def test_status_filter_is_read_from_the_question_not_the_model():
    assert _status_from_query("What is still waiting for approval?") == "pending"
    assert _status_from_query("Which recommendations still need a decision?") == "pending"
    assert _status_from_query("What did we approve already?") == "approved"
    assert _status_from_query("Which recommendations were rejected?") == "rejected"
    assert _status_from_query("show me everything") is None


def test_inventory_tool_filters_and_summarises():
    repository = FakeRepository()
    result = execute_tool("inventory_risk", {"min_probability": 0.5}, repository)
    assert len(result["rows"]) == 1
    assert "91% stockout" in result["summary"] or "91%" in result["summary"]

    filtered = execute_tool("inventory_risk", {"warehouse": "rajshahi"}, repository)
    assert len(filtered["rows"]) == 1
    assert filtered["rows"][0]["warehouse_name"] == "Rajshahi North"


def test_recommendation_tool_honours_pending_wording():
    repository = FakeRepository()
    pending = execute_tool("recommendation_queue", {"status": "approved"}, repository, "What is still waiting for approval?")
    assert len(pending["rows"]) == 1
    assert pending["rows"][0]["approval_status"] == "pending"
    assert "filter: pending" in pending["summary"]

    approved = execute_tool("recommendation_queue", {}, repository, "What did we approve already?")
    assert len(approved["rows"]) == 1
    assert approved["rows"][0]["approval_status"] == "approved"


def test_maritime_tool_ignores_generic_destination_words():
    repository = FakeRepository()
    result = execute_tool("maritime_watch", {"destination": "port"}, repository)
    assert len(result["rows"]) == 1
    assert "1 vessels match" in result["summary"]

    specific = execute_tool("maritime_watch", {"destination": "rotterdam"}, repository)
    assert specific["rows"] == []


def test_crop_tool_reports_the_weakest_area():
    repository = FakeRepository()
    result = execute_tool("crop_health", {"crop": "wheat"}, repository)
    assert len(result["rows"]) == 1
    assert "Punjab Wheat Belt" in result["summary"]
