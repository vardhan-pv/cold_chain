"""
Cold-Chain Tier-3 Rerouting API

Provides read access to emergency rerouting recommendations.

Current warehouse destination data is SIMULATED.
"""

from fastapi import APIRouter, Query

from backend.database.db import (
    get_latest_rerouting_event,
    get_rerouting_history,
)


router = APIRouter(
    prefix="/api/v1/rerouting",
    tags=["Rerouting"]
)


# ============================================================
# LATEST REROUTING EVENT
# ============================================================

@router.get("/{device_id}/latest")
def latest_rerouting(
    device_id: str
):

    event = get_latest_rerouting_event(
        device_id
    )

    if event is None:

        return {
            "device_id": device_id,
            "rerouting_available": False,
            "event": None
        }

    return {
        "device_id": device_id,
        "rerouting_available": True,
        "event": event
    }


# ============================================================
# REROUTING HISTORY
# ============================================================

@router.get("/{device_id}/history")
def rerouting_history(
    device_id: str,
    limit: int = Query(
        default=100,
        ge=1,
        le=500
    )
):

    events = get_rerouting_history(
        device_id=device_id,
        limit=limit
    )

    return {
        "device_id": device_id,
        "count": len(events),
        "events": events
    }