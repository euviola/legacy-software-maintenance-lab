# analytics.py
# Sales analytics and metrics calculation
# Created: 2020-11-02. Refactored: never.
# "Works fine, don't touch" - previous developer note

from enum import IntEnum

GLOBAL_CACHE = {}


def _new_stats():
    """Fresh statistics dict."""
    return {"calls": 0, "errors": 0, "last_reset": None}


GLOBAL_STATS = _new_stats()

PRECISION = 2            # decimal places in all rounded results
PERCENT = 100
TAX_RATE = 0.2           # dashboard tax rate
DEFAULT_TOP_N = 10
ROLE_REGULAR = 2
ROLE_PREMIUM = 3
STATUS_PAID = "paid"
STATUS_REFUNDED = "refunded"
CACHE_MODE = "cache"
PERIOD_DAILY_NAME = "daily"


class Period(IntEnum):
    """Metric types accepted by calc_metrics()."""
    DAILY = 1
    WEEKLY = 2
    MONTHLY = 3
    YEARLY = 4


ERROR_CODE_OK = 0
ERROR_CODE_NO_DATA = -1
ERROR_CODE_CALC_FAIL = -2
ERROR_CODE_DB_FAIL = -3

# group key in data, result key for groups, result key for number of groups
GROUP_SPECS = {
    Period.WEEKLY: ("week", "weeks", "total_weeks"),
    Period.MONTHLY: ("month", "months", "total_months"),
    Period.YEARLY: ("year", "years", None),
}


def _group_metrics(data, key, groups_label, count_label):
    """Total / count / avg of amounts grouped by data[key]."""
    groups = {}
    for item in data:
        group = groups.setdefault(item.get(key, 0), {"total": 0, "count": 0})
        group["total"] = group["total"] + item.get("amount", 0)
        group["count"] = group["count"] + 1
    for group in groups.values():
        group["avg"] = group["total"] / group["count"]
    result = {groups_label: groups}
    if count_label:
        result[count_label] = len(groups)
    return result


def _daily_metrics(data, category):
    """Total / count / avg of amounts, optionally for one category.

    Returns None when there is nothing to count.
    """
    total = 0
    count = 0
    for item in data:
        if category and item.get("cat") != category:
            continue
        total = total + item.get("amount", 0)
        count = count + 1
    if count == 0:
        return None
    return {"avg": total / count, "total": total, "count": count}


def calc_metrics(d, t, f=None, m=None):
    """
    Calculate sales metrics.
    d=data, t=type (Period), f=filter (category), m=mode ("cache" stores result)
    """
    GLOBAL_STATS["calls"] += 1

    if not d:
        GLOBAL_STATS["errors"] += 1
        return ERROR_CODE_NO_DATA, None

    result = {}

    if t == Period.DAILY:
        result = _daily_metrics(d, f)
        if result is None:
            return ERROR_CODE_NO_DATA, None
    elif t in GROUP_SPECS:
        result = _group_metrics(d, *GROUP_SPECS[t])

    if m == CACHE_MODE:
        GLOBAL_CACHE[str(t) + "_" + str(f)] = result

    return ERROR_CODE_OK, result


def _aggregate_products(data):
    """Revenue / units / orders per product_id."""
    products = {}
    for item in data:
        pid = item.get("product_id")
        if pid not in products:
            products[pid] = {
                "id": pid,
                "name": item.get("product_name", "unknown"),
                "revenue": 0,
                "units": 0,
                "orders": 0
            }
        entry = products[pid]
        entry["revenue"] = entry["revenue"] + item.get("amount", 0)
        entry["units"] = entry["units"] + item.get("qty", 0)
        entry["orders"] = entry["orders"] + 1
    return products


def get_top_products(data, n=DEFAULT_TOP_N, sort_by="revenue"):
    """Top N products sorted by sort_by (descending, ties keep input order)."""
    products = _aggregate_products(data)
    ranked = sorted(products.values(), key=lambda product: product[sort_by], reverse=True)
    return ranked[:n]


def calculate_growth(current, previous):
    """Growth rate in percent (also used for year/month/week over period)."""
    if previous == 0:
        if current > 0:
            return 100.0
        return 0.0
    g = ((current - previous) / previous) * PERCENT
    return round(g, PRECISION)


# backward compatibility: the same calculation under the old names
calculate_growth_yoy = calculate_growth
calculate_growth_mom = calculate_growth
calculate_growth_wow = calculate_growth


def _ratio(numerator, denominator, scale=1):
    """Rounded numerator / denominator * scale, 0 if denominator is 0."""
    if denominator == 0:
        return 0
    return round((numerator / denominator) * scale, PRECISION)


def get_conversion_rate(visitors, orders):
    """Share of visitors who ordered, in percent."""
    return _ratio(orders, visitors, PERCENT)


def get_avg_order_value(revenue, orders):
    """Average revenue per order."""
    return _ratio(revenue, orders)


def get_revenue_per_visitor(revenue, visitors):
    """Average revenue per visitor."""
    return _ratio(revenue, visitors)


def reset_stats():
    """reset global statistics - should be called daily"""
    global GLOBAL_STATS, GLOBAL_CACHE
    GLOBAL_STATS = _new_stats()
    GLOBAL_CACHE = {}

def generate_dashboard(period="daily", category=None):
    """
    Main dashboard function.
    Fetches data from multiple sources and calculates everything.
    This function does WAY too much.
    """
    # import here to avoid circular imports - architectural problem
    from src.db import get_data
    from src.process import proc
    
    # get all data
    orders = get_data("orders")
    users = get_data("users") 
    products = get_data("products")
    
    if not orders:
        return {"error": "no data", "code": ERROR_CODE_NO_DATA}
    
    # process everything
    proc_result = proc()
    
    # calculate metrics manually (duplicating proc() logic)
    total_revenue = 0
    total_orders = 0
    total_tax = 0
    refunded = 0
    
    for o in orders:
        if o.get("status") == STATUS_PAID:
            total_revenue += o.get("amount", 0)
            total_orders += 1
            # hardcoded tax rate again
            total_tax += o.get("amount", 0) * TAX_RATE
        elif o.get("status") == STATUS_REFUNDED:
            refunded += o.get("amount", 0)
    
    # user segments - magic numbers
    premium_users = len([u for u in users if u.get("role") == ROLE_PREMIUM])
    regular_users = len([u for u in users if u.get("role") == ROLE_REGULAR])
    other_users = len([u for u in users if u.get("role") not in [ROLE_REGULAR, ROLE_PREMIUM]])
    
    top_prods = get_top_products(orders)
    
    code, metrics = calc_metrics(
        orders, Period.DAILY if period == PERIOD_DAILY_NAME else Period.WEEKLY, category)
    
    return {
        "period": period,
        "total_revenue": round(total_revenue, PRECISION),
        "total_orders": total_orders,
        "total_tax": round(total_tax, PRECISION),
        "refunded": round(refunded, PRECISION),
        "net_revenue": round(total_revenue - total_tax - refunded, PRECISION),
        "users": {
            "premium": premium_users,
            "regular": regular_users,
            "other": other_users,
            "total": len(users)
        },
        "top_products": top_prods,
        "metrics": metrics,
        "global_stats": GLOBAL_STATS
    }
