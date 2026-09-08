from app.inventory import inventory_metrics, optimized_quantity


def test_inventory_metrics_bounds_risk_and_reorder_point():
    result = inventory_metrics(100, 10, 20, 10, 8, 5)
    assert result["available_inventory"] == 110
    assert result["reorder_point"] > 0
    assert 0 <= result["stockout_probability"] <= 1


def test_optimized_quantity_respects_case_pack_and_moq():
    assert optimized_quantity(100, 1000, 40, 50, 240, 40) == 920.0
