"""Shared query helpers for routers."""

from sqlalchemy import asc, desc
from sqlalchemy.orm import InspectionAttr


def apply_sort(query, model, sort_param: str | None):
    """Parse Base44-style sort strings like '-last_checkin' or '-timestamp'."""
    if not sort_param:
        return query
    if sort_param.startswith("-"):
        col_name = sort_param[1:]
        direction = desc
    else:
        col_name = sort_param
        direction = asc

    # Handle special sort names from Base44
    if col_name == "created_date":
        col_name = "created_at"

    col = getattr(model, col_name, None)
    if col is not None and isinstance(col, InspectionAttr):
        return query.order_by(direction(col))
    return query
