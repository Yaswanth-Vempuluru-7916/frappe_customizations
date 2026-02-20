import frappe
from frappe.utils import getdate, add_days, get_last_day


# =============================================================================
# INTERNAL CORE LOGIC
# =============================================================================

def _get_period_start_day(target_date, company=None):
    """
    Fetch custom_period_start_day from Payroll Period covering target_date.
    Fallback → 1 (calendar month)
    """
    filters = {
        "start_date": ["<=", target_date],
        "end_date": [">=", target_date],
        "docstatus": ["!=", 2],
    }
    if company:
        filters["company"] = company

    payroll_period = frappe.db.get_value(
        "Payroll Period",
        filters,
        ["custom_period_start_day"],
        as_dict=True,
    )

    if payroll_period:
        day = payroll_period.get("custom_period_start_day")
        if day is not None and day != "":
            day = int(day)
            if 1 <= day <= 31:
                return day
    return 1


def _clamp_day_to_month(year, month, day):
    """
    Clamp configured day to actual month length
    Handles leap year automatically
    """

    first = getdate(f"{year}-{str(month).zfill(2)}-01")
    last_day = get_last_day(first).day
    return min(day, last_day)


def _build_period_date(year, month, configured_day):
    safe_day = _clamp_day_to_month(year, month, configured_day)
    return getdate(f"{year}-{str(month).zfill(2)}-{str(safe_day).zfill(2)}")


def _get_period_boundaries(target_date, company=None):
    """
    CORE payroll period computation logic
    Returns period_start, period_end
    """
    configured_day = _get_period_start_day(target_date, company=company)

    year = target_date.year
    month = target_date.month
    day = target_date.day

    effective_this_month = _clamp_day_to_month(year, month, configured_day)

    # Case 1 → current month period
    if day >= effective_this_month:

        period_start = _build_period_date(year, month, configured_day)

        if month == 12:
            next_year, next_month = year + 1, 1
        else:
            next_year, next_month = year, month + 1

    # Case 2 → previous month period
    else:

        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        period_start = _build_period_date(prev_year, prev_month, configured_day)
        next_year, next_month = year, month

    next_period_start = _build_period_date(next_year, next_month, configured_day)
    period_end = add_days(next_period_start, -1)

    return period_start, period_end


# =============================================================================
# PUBLIC SERVER SCRIPT API
# =============================================================================

@frappe.whitelist()
def get_period_boundaries(date, company=None):
    """
    Server Script safe API.
    Optional company: if not provided, uses default company from session so
    the Payroll Period (and its custom_period_start_day) is found correctly.
    """
    target_date = getdate(date)
    if not company:
        company = frappe.defaults.get_default("company")

    cache_key = f"payroll_period::{target_date}::{company or ''}"

    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    start, end = _get_period_boundaries(target_date, company=company)

    result = {
        "start": str(start),
        "end": str(end),
    }

    frappe.cache().set_value(cache_key, result, expires_in_sec=3600)

    return result