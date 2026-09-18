"""
Cold-Chain Telemetry API

Responsibilities:

1. Receive telemetry from simulator / ESP32-S3.
2. Validate telemetry using Pydantic.
3. Store telemetry in SQLite.
4. Run rule-based fault detection.
5. Manage fault lifecycle.
6. Update current system state.
7. Run self-healing decision engine.
8. Generate control commands when recovery is required.
9. Run Tier-3 rerouting evaluation for critical failures.
10. Provide telemetry history APIs.

IMPORTANT:
Rerouting warehouse information is currently SIMULATED.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from backend.database.db import (
    get_latest_telemetry,
    get_telemetry_history,
    save_telemetry,
)

from backend.models.telemetry import TelemetryData

from backend.services.fault_manager import (
    process_fault_lifecycle,
)

from backend.services.self_healing import (
    evaluate_self_healing,
)

from backend.services.rerouting import (
    evaluate_rerouting,
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/v1",
    tags=["Telemetry"]
)


# ============================================================
# RECEIVE TELEMETRY
# ============================================================

@router.post("/telemetry")
def receive_telemetry(data: TelemetryData):
    """
    Receive one validated telemetry packet.

    Newly inserted packets are processed through:

        Telemetry
            ↓
        Fault Lifecycle
            ↓
        Self-Healing
            ↓
        Tier-3 Rerouting

    Duplicate packets are stored only once and do not trigger
    duplicate fault, command or rerouting activity.
    """

    received_at = datetime.now(
        timezone.utc
    ).isoformat()

    # --------------------------------------------------------
    # STORE TELEMETRY
    # --------------------------------------------------------

    inserted = save_telemetry(
        data=data,
        received_at=received_at
    )

    # --------------------------------------------------------
    # INITIALIZE PROCESSING RESULTS
    # --------------------------------------------------------

    fault_result = None
    self_healing_result = None
    rerouting_result = None

    # --------------------------------------------------------
    # PROCESS NEW TELEMETRY ONLY
    # --------------------------------------------------------

    if inserted:

        # ----------------------------------------------------
        # FAULT LIFECYCLE
        # ----------------------------------------------------

        fault_result = process_fault_lifecycle(
            data
        )

        # ----------------------------------------------------
        # SELF-HEALING DECISION
        # ----------------------------------------------------

        self_healing_result = evaluate_self_healing(
            data=data,
            fault_result=fault_result
        )

        # ----------------------------------------------------
        # TIER-3 REROUTING
        # ----------------------------------------------------

        rerouting_result = evaluate_rerouting(
            data=data,
            fault_result=fault_result
        )

    # ========================================================
    # CONSOLE LOG
    # ========================================================

    print("\n" + "=" * 70)
    print("TELEMETRY RECEIVED")
    print("=" * 70)

    print(
        f"Device           : "
        f"{data.device_id}"
    )

    print(
        f"Session          : "
        f"{data.session_id}"
    )

    print(
        f"Sequence         : "
        f"{data.sequence}"
    )

    print(
        f"Source           : "
        f"{data.telemetry_source}"
    )

    print(
        f"Simulation       : "
        f"{data.simulation_mode}"
    )

    print(
        f"Chamber Temp     : "
        f"{data.chamber_temp_c} C"
    )

    print(
        f"Heatsink Temp    : "
        f"{data.heatsink_temp_c} C"
    )

    print(
        f"Humidity         : "
        f"{data.humidity_pct} %"
    )

    print(
        f"Current          : "
        f"{data.current_a} A"
    )

    print(
        f"Door Open        : "
        f"{data.door_open}"
    )

    print(
        f"Primary Cooling  : "
        f"{data.primary_cooling}"
    )

    print(
        f"Backup Cooling   : "
        f"{data.backup_cooling}"
    )

    print(
        f"GPS Valid        : "
        f"{data.gps.valid}"
    )

    print(
        f"GPS Source       : "
        f"{data.gps.source}"
    )

    print(
        f"Latitude         : "
        f"{data.gps.latitude}"
    )

    print(
        f"Longitude        : "
        f"{data.gps.longitude}"
    )

    print(
        f"Scenario Label   : "
        f"{data.scenario}"
    )

    print(
        f"Database Insert  : "
        f"{inserted}"
    )

    # ========================================================
    # FAULT LOG
    # ========================================================

    if fault_result is not None:

        print("-" * 70)

        print(
            f"Fault Detected   : "
            f"{fault_result['fault_detected']}"
        )

        print(
            f"Fault Type       : "
            f"{fault_result['fault_type']}"
        )

        print(
            f"Severity         : "
            f"{fault_result['severity']}"
        )

        print(
            f"System State     : "
            f"{fault_result['system_state']}"
        )

        print(
            f"New Fault Event  : "
            f"{fault_result['new_fault_created']}"
        )

        print(
            f"Fault ID         : "
            f"{fault_result['fault_id']}"
        )

        print(
            f"Resolved Faults  : "
            f"{fault_result['resolved_fault_ids']}"
        )

    else:

        print("-" * 70)

        print(
            "Fault Processing : "
            "SKIPPED (duplicate telemetry)"
        )

    # ========================================================
    # SELF-HEALING LOG
    # ========================================================

    if self_healing_result is not None:

        print("-" * 70)

        print(
            f"Action Required  : "
            f"{self_healing_result['action_required']}"
        )

        print(
            f"Command Created  : "
            f"{self_healing_result['command_created']}"
        )

        print(
            f"Command ID       : "
            f"{self_healing_result['command_id']}"
        )

        print(
            f"Command Type     : "
            f"{self_healing_result['command_type']}"
        )

        print(
            f"Target Primary   : "
            f"{self_healing_result['primary_cooling']}"
        )

        print(
            f"Target Backup    : "
            f"{self_healing_result['backup_cooling']}"
        )

        print(
            f"Command Status   : "
            f"{self_healing_result['status']}"
        )

        print(
            f"Action Reason    : "
            f"{self_healing_result['reason']}"
        )

    else:

        print("-" * 70)

        print(
            "Self-Healing     : "
            "SKIPPED (duplicate telemetry)"
        )

    # ========================================================
    # TIER-3 REROUTING LOG
    # ========================================================

    if rerouting_result is not None:

        print("-" * 70)

        print(
            f"Reroute Required : "
            f"{rerouting_result['rerouting_required']}"
        )

        print(
            f"Reroute Created  : "
            f"{rerouting_result['rerouting_created']}"
        )

        print(
            f"Rerouting ID     : "
            f"{rerouting_result['rerouting_id']}"
        )

        destination = rerouting_result.get(
            "destination"
        )

        if destination is not None:

            print(
                f"Destination      : "
                f"{destination.get('name')}"
            )

            print(
                f"Destination ID   : "
                f"{destination.get('warehouse_id')}"
            )

            print(
                f"Distance         : "
                f"{destination.get('distance_km')} km"
            )

            print(
                f"Destination Data : "
                f"{destination.get('data_source')}"
            )

        print(
            f"Reroute Reason   : "
            f"{rerouting_result['reason']}"
        )

    else:

        print("-" * 70)

        print(
            "Tier-3 Rerouting : "
            "SKIPPED (duplicate telemetry)"
        )

    print("=" * 70)

    # ========================================================
    # RESPONSE
    # ========================================================

    response = {

        "accepted": True,

        "stored": inserted,

        "duplicate": not inserted,

        "device_id":
            data.device_id,

        "session_id":
            data.session_id,

        "sequence":
            data.sequence,

        "message": (
            "Telemetry stored and processed successfully"
            if inserted
            else
            "Duplicate telemetry already stored"
        ),

        "server_timestamp":
            received_at
    }

    # ========================================================
    # ADD FAULT RESULT
    # ========================================================

    if fault_result is not None:

        response["fault"] = {

            "detected":
                fault_result[
                    "fault_detected"
                ],

            "type":
                fault_result[
                    "fault_type"
                ],

            "severity":
                fault_result[
                    "severity"
                ],

            "system_state":
                fault_result[
                    "system_state"
                ],

            "description":
                fault_result[
                    "description"
                ],

            "new_event":
                fault_result[
                    "new_fault_created"
                ],

            "fault_id":
                fault_result[
                    "fault_id"
                ],

            "resolved_fault_ids":
                fault_result[
                    "resolved_fault_ids"
                ]
        }

    else:

        response["fault"] = {
            "processed": False,
            "reason": "duplicate_telemetry"
        }

    # ========================================================
    # ADD SELF-HEALING RESULT
    # ========================================================

    if self_healing_result is not None:

        response["self_healing"] = {

            "action_required":
                self_healing_result[
                    "action_required"
                ],

            "command_created":
                self_healing_result[
                    "command_created"
                ],

            "command_id":
                self_healing_result[
                    "command_id"
                ],

            "command_type":
                self_healing_result[
                    "command_type"
                ],

            "primary_cooling":
                self_healing_result[
                    "primary_cooling"
                ],

            "backup_cooling":
                self_healing_result[
                    "backup_cooling"
                ],

            "status":
                self_healing_result[
                    "status"
                ],

            "reason":
                self_healing_result[
                    "reason"
                ]
        }

    else:

        response["self_healing"] = {
            "processed": False,
            "reason": "duplicate_telemetry"
        }

    # ========================================================
    # ADD TIER-3 REROUTING RESULT
    # ========================================================

    if rerouting_result is not None:

        response["rerouting"] = {
            "rerouting_required":
                rerouting_result[
                    "rerouting_required"
                ],

            "rerouting_created":
                rerouting_result[
                    "rerouting_created"
                ],

            "rerouting_id":
                rerouting_result[
                    "rerouting_id"
                ],

            "destination":
                rerouting_result[
                    "destination"
                ],

            "reason":
                rerouting_result[
                    "reason"
                ]
        }

    else:

        response["rerouting"] = {
            "processed": False,
            "reason": "duplicate_telemetry"
        }

    return response


# ============================================================
# LATEST TELEMETRY
# ============================================================

@router.get("/telemetry/{device_id}/latest")
def latest_telemetry(device_id: str):

    row = get_latest_telemetry(
        device_id
    )

    if row is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "No telemetry found "
                "for this device"
            )
        )

    return row


# ============================================================
# TELEMETRY HISTORY
# ============================================================

@router.get("/telemetry/{device_id}/history")
def telemetry_history(
    device_id: str,
    limit: int = Query(
        default=100,
        ge=1,
        le=1000
    )
):

    rows = get_telemetry_history(
        device_id=device_id,
        limit=limit
    )

    return {

        "device_id":
            device_id,

        "count":
            len(rows),

        "telemetry":
            rows
    }