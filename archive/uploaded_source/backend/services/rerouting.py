"""
Cold-Chain Tier-3 Emergency Rerouting Engine

Responsibilities:

1. Receive a critical-failure condition.
2. Validate source GPS.
3. Load available cold-storage destinations.
4. Filter unavailable/incompatible destinations.
5. Calculate geographic distance using Haversine formula.
6. Select the nearest eligible destination.
7. Store exactly one rerouting event per critical fault.

IMPORTANT:
Warehouse data is currently SIMULATED.
"""

from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

from backend.database.db import (
    create_rerouting_event,
    get_rerouting_event_by_fault,
)

from backend.services.warehouse_registry import (
    get_all_warehouses,
)


# ============================================================
# PROTOTYPE CARGO REQUIREMENTS
# ============================================================

REQUIRED_STORAGE_TEMPERATURE_C = 5.0

REQUIRED_CAPACITY_KG = 100.0


# ============================================================
# TIME
# ============================================================

def utc_now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_distance_km(
    latitude_1,
    longitude_1,
    latitude_2,
    longitude_2
):
    """
    Calculate great-circle distance between two GPS points.

    Returns distance in kilometres.
    """

    earth_radius_km = 6371.0

    lat1 = radians(latitude_1)
    lon1 = radians(longitude_1)

    lat2 = radians(latitude_2)
    lon2 = radians(longitude_2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        sin(delta_lat / 2) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(delta_lon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return earth_radius_km * c


# ============================================================
# WAREHOUSE COMPATIBILITY
# ============================================================

def is_warehouse_compatible(
    warehouse,
    required_temperature_c,
    required_capacity_kg
):
    """
    Check whether a warehouse can accept the simulated cargo.
    """

    if not warehouse["operational"]:
        return False

    if (
        warehouse["available_capacity_kg"]
        < required_capacity_kg
    ):
        return False

    if not (
        warehouse["min_temperature_c"]
        <= required_temperature_c
        <= warehouse["max_temperature_c"]
    ):
        return False

    return True


# ============================================================
# FIND BEST DESTINATION
# ============================================================

def find_best_destination(
    source_latitude,
    source_longitude,
    required_temperature_c=REQUIRED_STORAGE_TEMPERATURE_C,
    required_capacity_kg=REQUIRED_CAPACITY_KG
):
    """
    Filter compatible warehouses and return the nearest one.
    """

    warehouses = get_all_warehouses()

    candidates = []

    for warehouse in warehouses:

        if not is_warehouse_compatible(
            warehouse,
            required_temperature_c,
            required_capacity_kg
        ):
            continue

        distance_km = haversine_distance_km(
            source_latitude,
            source_longitude,
            warehouse["latitude"],
            warehouse["longitude"]
        )

        candidate = warehouse.copy()

        candidate["distance_km"] = round(
            distance_km,
            3
        )

        candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["distance_km"]
    )

    return candidates[0]


# ============================================================
# TIER-3 REROUTING EVALUATION
# ============================================================

def evaluate_rerouting(
    data,
    fault_result
):
    """
    Evaluate whether Tier-3 emergency rerouting is required.

    Rerouting occurs only when:
      - an actual fault exists
      - system state is CRITICAL_FAILURE
      - fault_id is available
      - GPS is valid
      - an eligible destination exists

    Duplicate rerouting events are prevented by fault ID.
    """

    no_action = {
        "rerouting_required": False,
        "rerouting_created": False,
        "rerouting_id": None,
        "destination": None,
        "reason": None
    }

    # --------------------------------------------------------
    # Must be an actual detected fault
    # --------------------------------------------------------

    if not fault_result.get(
        "fault_detected",
        False
    ):
        return no_action

    # --------------------------------------------------------
    # Must be CRITICAL_FAILURE
    # --------------------------------------------------------

    if (
        fault_result.get("system_state")
        != "CRITICAL_FAILURE"
    ):
        return no_action

    fault_id = fault_result.get("fault_id")

    if fault_id is None:

        return {
            **no_action,
            "rerouting_required": True,
            "reason": (
                "Critical failure detected but no "
                "fault ID was available."
            )
        }

    # --------------------------------------------------------
    # Validate GPS
    # --------------------------------------------------------

    if not data.gps.valid:

        return {
            **no_action,
            "rerouting_required": True,
            "reason": (
                "Critical failure detected but GPS "
                "position is not valid."
            )
        }

    if (
        data.gps.latitude is None
        or data.gps.longitude is None
    ):

        return {
            **no_action,
            "rerouting_required": True,
            "reason": (
                "Critical failure detected but GPS "
                "coordinates are missing."
            )
        }

    # --------------------------------------------------------
    # Duplicate prevention
    # --------------------------------------------------------

    existing = get_rerouting_event_by_fault(
        data.device_id,
        fault_id
    )

    if existing is not None:

        return {
            "rerouting_required": True,
            "rerouting_created": False,
            "rerouting_id": existing["id"],

            "destination": {
                "warehouse_id":
                    existing["destination_id"],

                "name":
                    existing["destination_name"],

                "latitude":
                    existing[
                        "destination_latitude"
                    ],

                "longitude":
                    existing[
                        "destination_longitude"
                    ],

                "distance_km":
                    existing["distance_km"],

                "available_capacity_kg":
                    existing[
                        "available_capacity_kg"
                    ],

                "data_source":
                    existing["data_source"]
            },

            "reason": (
                "Existing rerouting recommendation "
                "reused for this critical fault."
            )
        }

    # --------------------------------------------------------
    # Select destination
    # --------------------------------------------------------

    destination = find_best_destination(
        source_latitude=data.gps.latitude,
        source_longitude=data.gps.longitude,
        required_temperature_c=(
            REQUIRED_STORAGE_TEMPERATURE_C
        ),
        required_capacity_kg=(
            REQUIRED_CAPACITY_KG
        )
    )

    if destination is None:

        return {
            **no_action,
            "rerouting_required": True,
            "reason": (
                "No operational cold-storage "
                "destination satisfies the current "
                "temperature and capacity requirements."
            )
        }

    # --------------------------------------------------------
    # Create rerouting event
    # --------------------------------------------------------

    reason = (
        "Critical cold-chain failure detected. "
        f"Nearest compatible simulated destination is "
        f"{destination['name']} at approximately "
        f"{destination['distance_km']:.3f} km."
    )

    rerouting_id = create_rerouting_event(
        device_id=data.device_id,
        session_id=data.session_id,

        triggered_by_fault=fault_id,

        source_latitude=data.gps.latitude,
        source_longitude=data.gps.longitude,

        destination_id=(
            destination["warehouse_id"]
        ),

        destination_name=(
            destination["name"]
        ),

        destination_latitude=(
            destination["latitude"]
        ),

        destination_longitude=(
            destination["longitude"]
        ),

        distance_km=(
            destination["distance_km"]
        ),

        required_temperature_c=(
            REQUIRED_STORAGE_TEMPERATURE_C
        ),

        available_capacity_kg=(
            destination[
                "available_capacity_kg"
            ]
        ),

        status="RECOMMENDED",

        data_source="SIMULATED",

        reason=reason,

        created_at=utc_now_iso()
    )

    return {
        "rerouting_required": True,

        "rerouting_created": True,

        "rerouting_id": rerouting_id,

        "destination": {
            **destination
        },

        "reason": reason
    }