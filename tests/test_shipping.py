# tests/test_shipping.py
# Tests for CR-017: create_shipment() must reuse calculate_shipping_cost()

import inspect
from unittest.mock import patch

import pytest

import src.shipping as shipping


@pytest.fixture(autouse=True)
def mock_carriers():
    """Carrier API calls are mocked: they only print and return a stub."""
    with patch.object(shipping, "_call_np_api", return_value={"success": True}) as np_api, \
         patch.object(shipping, "_call_courier_api", return_value={"success": True}) as courier_api, \
         patch.object(shipping, "_call_ukrposhta_api", return_value={"success": True}) as up_api:
        yield {"np": np_api, "courier": courier_api, "up": up_api}


@pytest.mark.parametrize("method,weight,distance,fragile", [
    (1, 2, 150, False),
    (1, 10, 350, False),
    (2, 5, 550, False),
    (2, 0.3, 100, True),
    (3, 1, 40, False),
    (4, 5, 0, False),
    (4, 1, 0, True),
])
def test_cost_matches_calculate_shipping_cost(method, weight, distance, fragile):
    expected = shipping.calculate_shipping_cost(weight, distance, method, fragile)
    result = shipping.create_shipment(1, method, "addr", weight,
                                      is_fragile=fragile, distance=distance)
    assert result["cost"] == expected


@pytest.mark.parametrize("distance,expected_days", [(50, 1), (200, 2), (350, 3), (700, 4)])
def test_distance_is_passed_to_delivery_time(distance, expected_days):
    result = shipping.create_shipment(1, 1, "addr", 2, distance=distance)
    assert result["estimated_days"] == shipping.get_delivery_time(1, distance)
    assert result["estimated_days"] == expected_days


def test_distance_is_required():
    with pytest.raises(TypeError):
        shipping.create_shipment(1, 1, "addr", 2)


def test_unknown_method_cost_is_zero_and_carrier_fails():
    result = shipping.create_shipment(1, 9, "addr", 1, distance=100)
    assert result["cost"] == 0
    assert result["carrier_response"]["success"] is False


@pytest.mark.parametrize("method,carrier", [(1, "np"), (2, "np"), (3, "courier"), (4, "up")])
def test_carrier_dispatch_unchanged(mock_carriers, method, carrier):
    shipping.create_shipment(1, method, "addr", 2, distance=100)
    assert mock_carriers[carrier].call_count == 1


def test_no_inline_cost_logic_in_create_shipment():
    source = inspect.getsource(shipping.create_shipment)
    assert "calculate_shipping_cost(" in source
    assert "if weight <=" not in source
    assert "elif weight <=" not in source
