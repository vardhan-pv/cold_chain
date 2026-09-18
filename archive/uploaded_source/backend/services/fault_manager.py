"""
Cold-Chain Fault Lifecycle Manager

Responsibilities:

1. Run rule-based detection.
2. Create database events only for actual faults.
3. Avoid duplicate active fault records.
4. Resolve faults when operating condition changes.
5. Maintain latest system state.
6. Support operational states such as BACKUP_ACTIVE.
7. Preserve fault IDs for self-healing traceability.
"""

from datetime import datetime, timezone

from backend.database.db import (
    create_fault_event,
    get_active_faults,
    get_active_fault_by_type,
    resolve_fault,
    update_system_state,
)

from backend.services.fault_detector import (
    detect_fault,
    STATE_NORMAL,
    STATE_BACKUP_ACTIVE,
)


def utc_now_iso():
    """
    Return current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def process_fault_lifecycle(data):
    """
    Analyze one telemetry packet and synchronize fault_events
    and system_state.

    BACKUP_ACTIVE is an operational state rather than a new
    fault event.
    """

    detected_at = utc_now_iso()

    result = detect_fault(data)

    new_fault_created = False
    active_fault_id = None
    resolved_fault_ids = []

    # ========================================================
    # ACTUAL FAULT
    # ========================================================

    if result.fault_detected:

        active_faults = get_active_faults(
            data.device_id
        )

        # Current detector returns one dominant fault.
        # Resolve other active fault types.

        for active_fault in active_faults:

            if (
                active_fault["fault_type"]
                != result.fault_type
            ):

                resolved = resolve_fault(
                    active_fault["id"],
                    detected_at
                )

                if resolved:

                    resolved_fault_ids.append(
                        active_fault["id"]
                    )

        existing_fault = (
            get_active_fault_by_type(
                data.device_id,
                result.fault_type
            )
        )

        if existing_fault is None:

            active_fault_id = (
                create_fault_event(
                    device_id=data.device_id,
                    session_id=data.session_id,
                    fault_type=result.fault_type,
                    severity=result.severity,
                    system_state=result.system_state,
                    description=result.description,
                    chamber_temp_c=(
                        data.chamber_temp_c
                    ),
                    heatsink_temp_c=(
                        data.heatsink_temp_c
                    ),
                    humidity_pct=(
                        data.humidity_pct
                    ),
                    current_a=data.current_a,
                    detected_at=detected_at
                )
            )

            new_fault_created = True

        else:

            active_fault_id = (
                existing_fault["id"]
            )

        update_system_state(
            device_id=data.device_id,
            session_id=data.session_id,
            current_state=result.system_state,
            primary_cooling=data.primary_cooling,
            backup_cooling=data.backup_cooling,
            active_fault=result.fault_type,
            updated_at=detected_at
        )

    # ========================================================
    # BACKUP ACTIVE — OPERATIONAL RECOVERY STATE
    # ========================================================

    elif result.system_state == STATE_BACKUP_ACTIVE:

        # ----------------------------------------------------
        # Resolve active fault events because the current
        # telemetry confirms that the backup actuator has
        # successfully taken control.
        #
        # The historical fault rows remain in fault_events,
        # including their resolved timestamps.
        #
        # No BACKUP_COOLING_ACTIVE fault is created.
        # ----------------------------------------------------

        active_faults = get_active_faults(
            data.device_id
        )

        for active_fault in active_faults:

            resolved = resolve_fault(
                active_fault["id"],
                detected_at
            )

            if resolved:

                resolved_fault_ids.append(
                    active_fault["id"]
                )

        update_system_state(
            device_id=data.device_id,
            session_id=data.session_id,
            current_state=STATE_BACKUP_ACTIVE,
            primary_cooling=data.primary_cooling,
            backup_cooling=data.backup_cooling,
            active_fault=None,
            updated_at=detected_at
        )

    # ========================================================
    # NORMAL / RECOVERED
    # ========================================================

    else:

        active_faults = get_active_faults(
            data.device_id
        )

        for active_fault in active_faults:

            resolved = resolve_fault(
                active_fault["id"],
                detected_at
            )

            if resolved:

                resolved_fault_ids.append(
                    active_fault["id"]
                )

        update_system_state(
            device_id=data.device_id,
            session_id=data.session_id,
            current_state=STATE_NORMAL,
            primary_cooling=data.primary_cooling,
            backup_cooling=data.backup_cooling,
            active_fault=None,
            updated_at=detected_at
        )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "fault_detected":
            result.fault_detected,

        "fault_type":
            result.fault_type,

        "severity":
            result.severity,

        "system_state":
            result.system_state,

        "description":
            result.description,

        "new_fault_created":
            new_fault_created,

        "fault_id":
            active_fault_id,

        "resolved_fault_ids":
            resolved_fault_ids
    }