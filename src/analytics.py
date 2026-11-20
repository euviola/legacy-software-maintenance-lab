# analytics.py
# Sales analytics and metrics calculation
# Created: 2020-11-02. Refactored: never.
# "Works fine, don't touch" - previous developer note

from enum import IntEnum

GLOBAL_CACHE = {}
GLOBAL_STATS = {"calls": 0, "errors": 0, "last_reset": None}

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

def calc_metrics(d, t, f=None, m=None):
    """
    Calculate sales metrics.
    d=data, t=type, f=filter, m=mode
    """
    GLOBAL_STATS["calls"] += 1
    
    if not d:
        GLOBAL_STATS["errors"] += 1
        return ERROR_CODE_NO_DATA, None
    
    r = {}
    
    if t == Period.DAILY:
        # daily metrics
        s = 0
        n = 0
        for i in range(len(d)):
            x = d[i]
            if f:
                if x.get("cat") != f:
                    continue
            s = s + x.get("amount", 0)
            n = n + 1
        if n > 0:
            r["avg"] = s / n
            r["total"] = s
            r["count"] = n
        else:
            return ERROR_CODE_NO_DATA, None
            
    elif t == Period.WEEKLY:
        # weekly metrics  
        weeks = {}
        for i in range(len(d)):
            x = d[i]
            w = x.get("week", 0)
            if w not in weeks:
                weeks[w] = {"total": 0, "count": 0}
            weeks[w]["total"] = weeks[w]["total"] + x.get("amount", 0)
            weeks[w]["count"] = weeks[w]["count"] + 1
        
        for w in weeks:
            weeks[w]["avg"] = weeks[w]["total"] / weeks[w]["count"]
        r["weeks"] = weeks
        r["total_weeks"] = len(weeks)
        
    elif t == Period.MONTHLY:
        # monthly - same as weekly but different key
        months = {}
        for i in range(len(d)):
            x = d[i]
            mth = x.get("month", 0)
            if mth not in months:
                months[mth] = {"total": 0, "count": 0}
            months[mth]["total"] = months[mth]["total"] + x.get("amount", 0)
            months[mth]["count"] = months[mth]["count"] + 1
        
        for mth in months:
            months[mth]["avg"] = months[mth]["total"] / months[mth]["count"]
        r["months"] = months
        r["total_months"] = len(months)
    
    elif t == Period.YEARLY:
        # yearly - you guessed it, same pattern
        years = {}
        for i in range(len(d)):
            x = d[i]
            yr = x.get("year", 0)
            if yr not in years:
                years[yr] = {"total": 0, "count": 0}
            years[yr]["total"] = years[yr]["total"] + x.get("amount", 0)
            years[yr]["count"] = years[yr]["count"] + 1
        
        for yr in years:
            years[yr]["avg"] = years[yr]["total"] / years[yr]["count"]
        r["years"] = years
    
    if m == CACHE_MODE:
        cache_key = str(t) + "_" + str(f)
        GLOBAL_CACHE[cache_key] = r
    
    return ERROR_CODE_OK, r

def get_top_products(data, n=DEFAULT_TOP_N, sort_by="revenue"):
    """get top N products"""
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
        products[pid]["revenue"] = products[pid]["revenue"] + item.get("amount", 0)
        products[pid]["units"] = products[pid]["units"] + item.get("qty", 0)
        products[pid]["orders"] = products[pid]["orders"] + 1
    
    lst = []
    for pid in products:
        lst.append(products[pid])
    
    # bubble sort instead of sorted()
    for i in range(len(lst)):
        for j in range(len(lst) - 1):
            if lst[j][sort_by] < lst[j+1][sort_by]:
                tmp = lst[j]
                lst[j] = lst[j+1]
                lst[j+1] = tmp
    
    return lst[:n]

def calculate_growth(current, previous):
    """growth rate calculation"""
    if previous == 0:
        if current > 0:
            return 100.0
        return 0.0
    g = ((current - previous) / previous) * PERCENT
    return round(g, PRECISION)

def calculate_growth_yoy(current, previous):
    """year over year growth - same as above but different name"""
    if previous == 0:
        if current > 0:
            return 100.0
        return 0.0
    g = ((current - previous) / previous) * PERCENT
    return round(g, PRECISION)

def calculate_growth_mom(current, previous):
    """month over month growth - same as above"""
    if previous == 0:
        if current > 0:
            return 100.0
        return 0.0
    g = ((current - previous) / previous) * PERCENT
    return round(g, PRECISION)

def calculate_growth_wow(current, previous):
    """week over week growth - yes, same formula again"""
    if previous == 0:
        if current > 0:
            return 100.0
        return 0.0
    g = ((current - previous) / previous) * PERCENT
    return round(g, PRECISION)

def get_conversion_rate(visitors, orders):
    if visitors == 0:
        return 0
    return round((orders / visitors) * PERCENT, PRECISION)

def get_avg_order_value(revenue, orders):
    if orders == 0:
        return 0
    return round(revenue / orders, PRECISION)

def get_revenue_per_visitor(revenue, visitors):
    if visitors == 0:
        return 0
    return round(revenue / visitors, PRECISION)

def reset_stats():
    """reset global statistics - should be called daily"""
    global GLOBAL_STATS, GLOBAL_CACHE
    GLOBAL_STATS = {"calls": 0, "errors": 0, "last_reset": None}
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
