# tests/test_analytics.py
# Characterization tests for src/analytics.py (reengineering safety net)

from unittest.mock import patch

import pytest

import src.analytics as analytics
import src.process  # noqa: F401 - import before patching src.db.get_data


@pytest.fixture(autouse=True)
def clean_state():
    analytics.reset_stats()
    yield
    analytics.reset_stats()


SALES = [
    {"amount": 100, "cat": "a", "week": 1, "month": 1, "year": 2023},
    {"amount": 200, "cat": "b", "week": 1, "month": 2, "year": 2023},
    {"amount": 300, "cat": "a", "week": 2, "month": 2, "year": 2024},
]


# ---------- calc_metrics ----------

def test_calc_metrics_empty_data_counts_error():
    assert analytics.calc_metrics([], 1) == (analytics.ERROR_CODE_NO_DATA, None)
    assert analytics.GLOBAL_STATS["calls"] == 1
    assert analytics.GLOBAL_STATS["errors"] == 1


def test_calc_metrics_daily_without_filter():
    code, result = analytics.calc_metrics(SALES, 1)
    assert code == analytics.ERROR_CODE_OK
    assert result == {"avg": 200.0, "total": 600, "count": 3}


def test_calc_metrics_daily_with_filter():
    code, result = analytics.calc_metrics(SALES, 1, "a")
    assert code == analytics.ERROR_CODE_OK
    assert result == {"avg": 200.0, "total": 400, "count": 2}


def test_calc_metrics_daily_filter_without_match_is_not_counted_as_error():
    assert analytics.calc_metrics(SALES, 1, "zzz") == (analytics.ERROR_CODE_NO_DATA, None)
    assert analytics.GLOBAL_STATS["calls"] == 1
    assert analytics.GLOBAL_STATS["errors"] == 0


def test_calc_metrics_weekly():
    code, result = analytics.calc_metrics(SALES, 2)
    assert code == analytics.ERROR_CODE_OK
    assert result == {
        "weeks": {1: {"total": 300, "count": 2, "avg": 150.0},
                  2: {"total": 300, "count": 1, "avg": 300.0}},
        "total_weeks": 2,
    }


def test_calc_metrics_monthly():
    _, result = analytics.calc_metrics(SALES, 3)
    assert result == {
        "months": {1: {"total": 100, "count": 1, "avg": 100.0},
                   2: {"total": 500, "count": 2, "avg": 250.0}},
        "total_months": 2,
    }


def test_calc_metrics_yearly_has_no_total_key():
    _, result = analytics.calc_metrics(SALES, 4)
    assert result == {
        "years": {2023: {"total": 300, "count": 2, "avg": 150.0},
                  2024: {"total": 300, "count": 1, "avg": 300.0}},
    }


def test_calc_metrics_missing_keys_default_to_zero():
    _, result = analytics.calc_metrics([{"x": 1}, {"amount": 10}], 2)
    assert result["weeks"] == {0: {"total": 10, "count": 2, "avg": 5.0}}


def test_calc_metrics_unknown_type_returns_empty_result():
    assert analytics.calc_metrics(SALES, 99) == (analytics.ERROR_CODE_OK, {})


def test_calc_metrics_cache_mode_stores_result():
    _, result = analytics.calc_metrics(SALES, 1, "a", "cache")
    assert analytics.GLOBAL_CACHE["1_a"] == result
    analytics.calc_metrics(SALES, 2, None, "cache")
    assert "2_None" in analytics.GLOBAL_CACHE


def test_calc_metrics_without_cache_mode_does_not_store():
    analytics.calc_metrics(SALES, 1, "a")
    assert analytics.GLOBAL_CACHE == {}


# ---------- get_top_products ----------

ITEMS = [
    {"product_id": 1, "product_name": "A", "amount": 100, "qty": 1},
    {"product_id": 2, "product_name": "B", "amount": 500, "qty": 2},
    {"product_id": 1, "product_name": "A", "amount": 300, "qty": 3},
    {"product_id": 3, "amount": 400, "qty": 9},
]


def test_top_products_sorted_by_revenue_desc_with_stable_ties():
    result = analytics.get_top_products(ITEMS)
    assert result == [
        {"id": 2, "name": "B", "revenue": 500, "units": 2, "orders": 1},
        {"id": 1, "name": "A", "revenue": 400, "units": 4, "orders": 2},
        {"id": 3, "name": "unknown", "revenue": 400, "units": 9, "orders": 1},
    ]


def test_top_products_limit_and_sort_by_units():
    assert len(analytics.get_top_products(ITEMS, n=2)) == 2
    by_units = analytics.get_top_products(ITEMS, sort_by="units")
    assert [p["id"] for p in by_units] == [3, 1, 2]


def test_top_products_empty():
    assert analytics.get_top_products([]) == []


# ---------- growth and ratios ----------

@pytest.mark.parametrize("current,previous,expected", [
    (120, 100, 20.0),
    (80, 100, -20.0),
    (100, 100, 0.0),
    (1, 3, -66.67),
    (0, 0, 0.0),
    (5, 0, 100.0),
])
@pytest.mark.parametrize("func_name", [
    "calculate_growth", "calculate_growth_yoy",
    "calculate_growth_mom", "calculate_growth_wow",
])
def test_growth_functions(func_name, current, previous, expected):
    assert getattr(analytics, func_name)(current, previous) == expected


def test_conversion_rate():
    assert analytics.get_conversion_rate(200, 5) == 2.5
    assert analytics.get_conversion_rate(0, 5) == 0


def test_avg_order_value():
    assert analytics.get_avg_order_value(1000, 3) == 333.33
    assert analytics.get_avg_order_value(1000, 0) == 0


def test_revenue_per_visitor():
    assert analytics.get_revenue_per_visitor(1000, 8) == 125.0
    assert analytics.get_revenue_per_visitor(1000, 0) == 0


def test_reset_stats_clears_state():
    analytics.calc_metrics(SALES, 1, None, "cache")
    analytics.reset_stats()
    assert analytics.GLOBAL_STATS == {"calls": 0, "errors": 0, "last_reset": None}
    assert analytics.GLOBAL_CACHE == {}


# ---------- generate_dashboard ----------

ORDERS = [
    {"id": 1, "status": "paid", "amount": 500.0, "product_id": 10},
    {"id": 2, "status": "paid", "amount": 1200.0, "product_id": 11},
    {"id": 3, "status": "refunded", "amount": 100.0, "product_id": 10},
    {"id": 4, "status": "pending", "amount": 80.0, "product_id": 12},
]
USERS = [{"role": 3}, {"role": 3}, {"role": 2}, {"role": 1}, {"role": 5}]


def fake_get_data(orders=ORDERS, users=USERS):
    def _get(what):
        return {"orders": orders, "users": users, "products": []}[what]
    return _get


def test_dashboard_full_result():
    with patch("src.db.get_data", side_effect=fake_get_data()), \
         patch("src.process.proc") as proc_mock:
        result = analytics.generate_dashboard()
    assert proc_mock.call_count == 1
    assert result["period"] == "daily"
    assert result["total_revenue"] == 1700.0
    assert result["total_orders"] == 2
    assert result["total_tax"] == 340.0
    assert result["refunded"] == 100.0
    assert result["net_revenue"] == 1260.0
    assert result["users"] == {"premium": 2, "regular": 1, "other": 2, "total": 5}
    assert result["metrics"] == {"avg": 470.0, "total": 1880.0, "count": 4}
    assert [p["id"] for p in result["top_products"]] == [11, 10, 12]
    assert result["global_stats"] == {"calls": 1, "errors": 0, "last_reset": None}


def test_dashboard_without_orders_returns_error_and_skips_proc():
    with patch("src.db.get_data", side_effect=fake_get_data(orders=[])), \
         patch("src.process.proc") as proc_mock:
        result = analytics.generate_dashboard()
    assert result == {"error": "no data", "code": analytics.ERROR_CODE_NO_DATA}
    assert proc_mock.call_count == 0


def test_dashboard_weekly_period_uses_weekly_metrics():
    with patch("src.db.get_data", side_effect=fake_get_data()), patch("src.process.proc"):
        result = analytics.generate_dashboard("weekly")
    assert result["period"] == "weekly"
    assert result["metrics"]["total_weeks"] == 1


def test_dashboard_unknown_period_falls_back_to_weekly_metrics():
    with patch("src.db.get_data", side_effect=fake_get_data()), patch("src.process.proc"):
        result = analytics.generate_dashboard("monthly")
    assert "weeks" in result["metrics"]


def test_dashboard_category_without_match_gives_empty_metrics():
    with patch("src.db.get_data", side_effect=fake_get_data()), patch("src.process.proc"):
        result = analytics.generate_dashboard("daily", "electronics")
    assert result["metrics"] is None


def test_dashboard_with_default_test_data():
    result = analytics.generate_dashboard()
    assert result["total_revenue"] == 1700.0
    assert result["total_orders"] == 2
    assert result["net_revenue"] == 1360.0
    assert result["users"] == {"premium": 4, "regular": 1, "other": 0, "total": 5}


# ---------- constants (iteration 2) ----------

def test_period_codes_are_backward_compatible():
    assert [p.value for p in analytics.Period] == [1, 2, 3, 4]
    for code in (1, 2, 3, 4):
        assert analytics.calc_metrics(SALES, analytics.Period(code)) == \
            analytics.calc_metrics(SALES, code)


def test_named_constants_keep_legacy_values():
    assert analytics.TAX_RATE == 0.2
    assert (analytics.ROLE_REGULAR, analytics.ROLE_PREMIUM) == (2, 3)
    assert (analytics.STATUS_PAID, analytics.STATUS_REFUNDED) == ("paid", "refunded")
    assert analytics.CACHE_MODE == "cache"
    assert analytics.DEFAULT_TOP_N == 10


# ---------- consolidated helpers (iteration 3) ----------

def test_group_metrics_helper_with_count_label():
    result = analytics._group_metrics(SALES, "week", "weeks", "total_weeks")
    assert result["total_weeks"] == 2
    assert result["weeks"][1] == {"total": 300, "count": 2, "avg": 150.0}


def test_group_metrics_helper_without_count_label():
    result = analytics._group_metrics(SALES, "year", "years", None)
    assert list(result) == ["years"]


def test_group_specs_cover_all_grouped_periods():
    assert set(analytics.GROUP_SPECS) == {
        analytics.Period.WEEKLY, analytics.Period.MONTHLY, analytics.Period.YEARLY}


def test_growth_aliases_share_one_implementation():
    assert analytics.calculate_growth_yoy is analytics.calculate_growth
    assert analytics.calculate_growth_mom is analytics.calculate_growth
    assert analytics.calculate_growth_wow is analytics.calculate_growth


def test_ratio_helper_scale_and_zero_denominator():
    assert analytics._ratio(1, 3) == 0.33
    assert analytics._ratio(1, 4, 100) == 25.0
    assert analytics._ratio(1, 0, 100) == 0


def test_new_stats_returns_independent_dicts():
    first, second = analytics._new_stats(), analytics._new_stats()
    first["calls"] = 5
    assert second["calls"] == 0


# ---------- calc_metrics / top products helpers (iteration 4) ----------

def test_daily_metrics_helper():
    assert analytics._daily_metrics(SALES, None) == {"avg": 200.0, "total": 600, "count": 3}
    assert analytics._daily_metrics(SALES, "a")["count"] == 2
    assert analytics._daily_metrics(SALES, "zzz") is None


def test_aggregate_products_helper():
    products = analytics._aggregate_products(ITEMS)
    assert list(products) == [1, 2, 3]
    assert products[1] == {"id": 1, "name": "A", "revenue": 400, "units": 4, "orders": 2}


def test_top_products_do_not_mutate_input():
    snapshot = [dict(item) for item in ITEMS]
    analytics.get_top_products(ITEMS)
    assert ITEMS == snapshot


# ---------- dashboard helpers (iteration 5) ----------

def test_summarize_orders_helper():
    summary = analytics._summarize_orders(ORDERS)
    assert summary == {"revenue": 1700.0, "orders": 2, "tax": 340.0, "refunded": 100.0}


def test_summarize_orders_empty():
    assert analytics._summarize_orders([]) == {"revenue": 0, "orders": 0, "tax": 0, "refunded": 0}


def test_count_users_by_role_helper():
    assert analytics._count_users_by_role(USERS) == {
        "premium": 2, "regular": 1, "other": 2, "total": 5}
    assert analytics._count_users_by_role([]) == {
        "premium": 0, "regular": 0, "other": 0, "total": 0}


def test_metric_type_for_period_helper():
    assert analytics._metric_type_for_period("daily") == analytics.Period.DAILY
    assert analytics._metric_type_for_period("weekly") == analytics.Period.WEEKLY
    assert analytics._metric_type_for_period("anything") == analytics.Period.WEEKLY


def test_load_dashboard_data_helper():
    with patch("src.db.get_data", side_effect=fake_get_data()):
        orders, users = analytics._load_dashboard_data()
    assert orders == ORDERS and users == USERS


def test_run_order_processing_helper_calls_proc_once():
    with patch("src.process.proc") as proc_mock:
        analytics._run_order_processing()
    assert proc_mock.call_count == 1


def test_dashboard_is_an_orchestrator_over_helpers():
    with patch.object(analytics, "_load_dashboard_data", return_value=(ORDERS, USERS)) as load, \
         patch.object(analytics, "_run_order_processing") as run_proc:
        result = analytics.generate_dashboard("weekly")
    assert load.call_count == 1 and run_proc.call_count == 1
    assert result["users"]["total"] == 5
    assert result["total_orders"] == 2
