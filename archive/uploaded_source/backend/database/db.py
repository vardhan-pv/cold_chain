import sqlite3
from pathlib import Path


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATABASE_DIR = PROJECT_ROOT / "database"

DATABASE_PATH = DATABASE_DIR / "cold_chain.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():
    """
    Create and return a SQLite database connection.
    """

    DATABASE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def initialize_database():
    """
    Create all required Cold-Chain database tables.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        # ====================================================
        # TELEMETRY TABLE
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id TEXT NOT NULL,

                session_id TEXT NOT NULL,

                sequence INTEGER NOT NULL,

                timestamp TEXT NOT NULL,

                telemetry_source TEXT NOT NULL,

                simulation_mode INTEGER NOT NULL,

                chamber_temp_c REAL NOT NULL,

                heatsink_temp_c REAL NOT NULL,

                humidity_pct REAL NOT NULL,

                current_a REAL NOT NULL,

                door_open INTEGER NOT NULL,

                primary_cooling INTEGER NOT NULL,

                backup_cooling INTEGER NOT NULL,

                latitude REAL,

                longitude REAL,

                gps_valid INTEGER NOT NULL,

                gps_source TEXT NOT NULL,

                scenario TEXT NOT NULL,

                received_at TEXT NOT NULL,

                UNIQUE(
                    device_id,
                    session_id,
                    sequence
                )
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_telemetry_device_timestamp
            ON telemetry(
                device_id,
                timestamp
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_telemetry_session
            ON telemetry(
                device_id,
                session_id
            )
            """
        )


        # ====================================================
        # FAULT EVENTS TABLE
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fault_events (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id TEXT NOT NULL,

                session_id TEXT,

                fault_type TEXT NOT NULL,

                severity TEXT NOT NULL,

                system_state TEXT NOT NULL,

                description TEXT NOT NULL,

                chamber_temp_c REAL,

                heatsink_temp_c REAL,

                humidity_pct REAL,

                current_a REAL,

                detected_at TEXT NOT NULL,

                resolved INTEGER NOT NULL DEFAULT 0,

                resolved_at TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_fault_events_device_time
            ON fault_events(
                device_id,
                detected_at
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_fault_events_active
            ON fault_events(
                device_id,
                resolved
            )
            """
        )


        # ====================================================
        # SYSTEM STATE TABLE
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS system_state (

                device_id TEXT PRIMARY KEY,

                session_id TEXT,

                current_state TEXT NOT NULL,

                previous_state TEXT,

                primary_cooling INTEGER NOT NULL,

                backup_cooling INTEGER NOT NULL,

                active_fault TEXT,

                updated_at TEXT NOT NULL
            )
            """
        )
        # ====================================================
        # CONTROL COMMANDS TABLE
        # ====================================================
        #
        # Stores control decisions generated by the backend
        # self-healing engine.
        #
        # During simulation:
        #     Backend -> control_commands -> Simulator
        #
        # During physical deployment:
        #     Backend -> control_commands -> ESP32-S3
        #
        # Command lifecycle:
        #     PENDING -> ACKNOWLEDGED
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS control_commands (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id TEXT NOT NULL,

                session_id TEXT,

                command_type TEXT NOT NULL,

                primary_cooling INTEGER NOT NULL,

                backup_cooling INTEGER NOT NULL,

                reason TEXT NOT NULL,

                triggered_by_fault INTEGER,

                status TEXT NOT NULL DEFAULT 'PENDING',

                created_at TEXT NOT NULL,

                acknowledged_at TEXT,

                FOREIGN KEY(triggered_by_fault)
                    REFERENCES fault_events(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_control_commands_device_status
            ON control_commands(
                device_id,
                status
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_control_commands_created
            ON control_commands(
                device_id,
                created_at
            )
            """
        )
           # ====================================================
        # REROUTING EVENTS TABLE
        # ====================================================
        #
        # Stores Tier-3 emergency rerouting recommendations.
        #
        # This table is used when the cold-chain system enters
        # CRITICAL_FAILURE and cargo should be redirected to a
        # compatible cold-storage destination.
        #
        # During the software-development stage, warehouse and
        # GPS destination information is explicitly marked as
        # SIMULATED.
        # ====================================================

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rerouting_events (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                device_id TEXT NOT NULL,

                session_id TEXT,

                triggered_by_fault INTEGER,

                source_latitude REAL NOT NULL,

                source_longitude REAL NOT NULL,

                destination_id TEXT NOT NULL,

                destination_name TEXT NOT NULL,

                destination_latitude REAL NOT NULL,

                destination_longitude REAL NOT NULL,

                distance_km REAL NOT NULL,

                required_temperature_c REAL,

                available_capacity_kg REAL,

                status TEXT NOT NULL
                    DEFAULT 'RECOMMENDED',

                data_source TEXT NOT NULL
                    DEFAULT 'SIMULATED',

                reason TEXT NOT NULL,

                created_at TEXT NOT NULL,

                FOREIGN KEY(triggered_by_fault)
                    REFERENCES fault_events(id)
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_rerouting_device_time
            ON rerouting_events(
                device_id,
                created_at
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_rerouting_fault
            ON rerouting_events(
                triggered_by_fault
            )
            """
        )
        # ====================================================
        # COMMIT SCHEMA
        # ====================================================

        connection.commit()

    finally:

        connection.close()


# ============================================================
# SAVE TELEMETRY
# ============================================================

def save_telemetry(data, received_at):
    """
    Store one validated telemetry packet.

    Returns:
        True  -> new packet inserted
        False -> duplicate packet ignored

    Packet uniqueness:
        device_id + session_id + sequence
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO telemetry (

                device_id,
                session_id,
                sequence,
                timestamp,

                telemetry_source,
                simulation_mode,

                chamber_temp_c,
                heatsink_temp_c,
                humidity_pct,
                current_a,

                door_open,

                primary_cooling,
                backup_cooling,

                latitude,
                longitude,

                gps_valid,
                gps_source,

                scenario,
                received_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,

            (
                data.device_id,
                data.session_id,
                data.sequence,
                data.timestamp.isoformat(),

                data.telemetry_source,
                int(data.simulation_mode),

                data.chamber_temp_c,
                data.heatsink_temp_c,
                data.humidity_pct,
                data.current_a,

                int(data.door_open),

                int(data.primary_cooling),
                int(data.backup_cooling),

                data.gps.latitude,
                data.gps.longitude,

                int(data.gps.valid),
                data.gps.source,

                data.scenario,
                received_at
            )
        )

        inserted = cursor.rowcount > 0

        connection.commit()

        return inserted

    finally:

        connection.close()


# ============================================================
# GET LATEST TELEMETRY
# ============================================================

def get_latest_telemetry(device_id):
    """
    Get the newest stored telemetry packet for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM telemetry
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        connection.close()


# ============================================================
# GET TELEMETRY HISTORY
# ============================================================

def get_telemetry_history(
    device_id,
    limit=100
):
    """
    Return recent telemetry history for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM telemetry
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                device_id,
                limit
            )
        )

        rows = cursor.fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


# ============================================================
# TELEMETRY COUNT
# ============================================================

def get_telemetry_count():
    """
    Return total telemetry records.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM telemetry
            """
        )

        row = cursor.fetchone()

        return row["count"]

    finally:

        connection.close()


# ============================================================
# CREATE FAULT EVENT
# ============================================================

def create_fault_event(
    device_id,
    session_id,
    fault_type,
    severity,
    system_state,
    description,
    chamber_temp_c,
    heatsink_temp_c,
    humidity_pct,
    current_a,
    detected_at
):
    """
    Store a new detected fault event.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO fault_events (

                device_id,
                session_id,

                fault_type,
                severity,
                system_state,
                description,

                chamber_temp_c,
                heatsink_temp_c,
                humidity_pct,
                current_a,

                detected_at,

                resolved,
                resolved_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, 0, NULL
            )
            """,

            (
                device_id,
                session_id,

                fault_type,
                severity,
                system_state,
                description,

                chamber_temp_c,
                heatsink_temp_c,
                humidity_pct,
                current_a,

                detected_at
            )
        )

        fault_id = cursor.lastrowid

        connection.commit()

        return fault_id

    finally:

        connection.close()


# ============================================================
# GET FAULT HISTORY
# ============================================================

def get_fault_history(
    device_id,
    limit=100
):
    """
    Return fault history for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM fault_events
            WHERE device_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                device_id,
                limit
            )
        )

        rows = cursor.fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


# ============================================================
# GET ACTIVE FAULTS
# ============================================================

def get_active_faults(device_id):
    """
    Return unresolved faults for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM fault_events
            WHERE device_id = ?
            AND resolved = 0
            ORDER BY id DESC
            """,
            (device_id,)
        )

        rows = cursor.fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()

def get_active_fault_by_type(
    device_id,
    fault_type
):
    """
    Return an unresolved fault of the specified type.

    Used to prevent duplicate fault events from being
    created for every telemetry packet.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM fault_events
            WHERE device_id = ?
              AND fault_type = ?
              AND resolved = 0
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                device_id,
                fault_type
            )
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        connection.close()
# ============================================================
# RESOLVE FAULT
# ============================================================

def resolve_fault(
    fault_id,
    resolved_at
):
    """
    Mark a fault event as resolved.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE fault_events

            SET
                resolved = 1,
                resolved_at = ?

            WHERE id = ?
            """,
            (
                resolved_at,
                fault_id
            )
        )

        updated = cursor.rowcount > 0

        connection.commit()

        return updated

    finally:

        connection.close()


# ============================================================
# UPDATE SYSTEM STATE
# ============================================================

def update_system_state(
    device_id,
    session_id,
    current_state,
    primary_cooling,
    backup_cooling,
    active_fault,
    updated_at
):
    """
    Create or update the latest system state for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT current_state
            FROM system_state
            WHERE device_id = ?
            """,
            (device_id,)
        )

        existing = cursor.fetchone()

        previous_state = None

        if existing is not None:

            previous_state = existing[
                "current_state"
            ]

        cursor.execute(
            """
            INSERT INTO system_state (

                device_id,
                session_id,

                current_state,
                previous_state,

                primary_cooling,
                backup_cooling,

                active_fault,
                updated_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(device_id)
            DO UPDATE SET

                session_id =
                    excluded.session_id,

                previous_state =
                    system_state.current_state,

                current_state =
                    excluded.current_state,

                primary_cooling =
                    excluded.primary_cooling,

                backup_cooling =
                    excluded.backup_cooling,

                active_fault =
                    excluded.active_fault,

                updated_at =
                    excluded.updated_at
            """,

            (
                device_id,
                session_id,

                current_state,
                previous_state,

                int(primary_cooling),
                int(backup_cooling),

                active_fault,
                updated_at
            )
        )

        connection.commit()

    finally:

        connection.close()


# ============================================================
# GET SYSTEM STATE
# ============================================================

def get_system_state(device_id):
    """
    Return the current system state for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM system_state
            WHERE device_id = ?
            """,
            (device_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        connection.close()


# ============================================================
# DATABASE HEALTH
# ============================================================

def database_health():
    """
    Verify that SQLite is accessible.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        result = cursor.fetchone()

        return result is not None

    finally:

        connection.close()
        # ============================================================
# CREATE CONTROL COMMAND
# ============================================================

def create_control_command(
    device_id,
    session_id,
    command_type,
    primary_cooling,
    backup_cooling,
    reason,
    triggered_by_fault,
    created_at
):
    """
    Create a new self-healing control command.

    Returns:
        command ID
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO control_commands (

                device_id,
                session_id,

                command_type,

                primary_cooling,
                backup_cooling,

                reason,

                triggered_by_fault,

                status,

                created_at,
                acknowledged_at
            )

            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                'PENDING',
                ?,
                NULL
            )
            """,
            (
                device_id,
                session_id,

                command_type,

                int(primary_cooling),
                int(backup_cooling),

                reason,

                triggered_by_fault,

                created_at
            )
        )

        command_id = cursor.lastrowid

        connection.commit()

        return command_id

    finally:

        connection.close()


# ============================================================
# GET PENDING CONTROL COMMAND
# ============================================================

def get_pending_control_command(device_id):
    """
    Return the oldest pending command for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM control_commands

            WHERE device_id = ?
              AND status = 'PENDING'

            ORDER BY id ASC
            LIMIT 1
            """,
            (device_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        connection.close()


# ============================================================
# GET PENDING COMMAND BY TYPE
# ============================================================

def get_pending_command_by_type(
    device_id,
    command_type
):
    """
    Check whether the same command is already pending.

    Prevents the self-healing engine from generating a new
    command every time another telemetry packet arrives.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM control_commands

            WHERE device_id = ?
              AND command_type = ?
              AND status = 'PENDING'

            ORDER BY id DESC
            LIMIT 1
            """,
            (
                device_id,
                command_type
            )
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:

        connection.close()


# ============================================================
# ACKNOWLEDGE CONTROL COMMAND
# ============================================================

def acknowledge_control_command(
    command_id,
    acknowledged_at
):
    """
    Mark a control command as acknowledged.

    Later:
        Simulator or ESP32-S3 calls this after applying
        the requested output state.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE control_commands

            SET
                status = 'ACKNOWLEDGED',
                acknowledged_at = ?

            WHERE id = ?
              AND status = 'PENDING'
            """,
            (
                acknowledged_at,
                command_id
            )
        )

        updated = cursor.rowcount > 0

        connection.commit()

        return updated

    finally:

        connection.close()


# ============================================================
# GET CONTROL COMMAND HISTORY
# ============================================================

def get_control_command_history(
    device_id,
    limit=100
):
    """
    Return recent control-command history for a device.
    """

    connection = get_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM control_commands

            WHERE device_id = ?

            ORDER BY id DESC
            LIMIT ?
            """,
            (
                device_id,
                limit
            )
        )

        rows = cursor.fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()
        # ============================================================
# CREATE REROUTING EVENT
# ============================================================

def create_rerouting_event(
    device_id,
    session_id,
    triggered_by_fault,
    source_latitude,
    source_longitude,
    destination_id,
    destination_name,
    destination_latitude,
    destination_longitude,
    distance_km,
    required_temperature_c,
    available_capacity_kg,
    status,
    data_source,
    reason,
    created_at
):
    """
    Store a Tier-3 emergency rerouting recommendation.

    Returns:
        ID of the created rerouting event.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO rerouting_events (
                device_id,
                session_id,
                triggered_by_fault,

                source_latitude,
                source_longitude,

                destination_id,
                destination_name,

                destination_latitude,
                destination_longitude,

                distance_km,

                required_temperature_c,
                available_capacity_kg,

                status,
                data_source,

                reason,
                created_at
            )
            VALUES (
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            (
                device_id,
                session_id,
                triggered_by_fault,

                source_latitude,
                source_longitude,

                destination_id,
                destination_name,

                destination_latitude,
                destination_longitude,

                distance_km,

                required_temperature_c,
                available_capacity_kg,

                status,
                data_source,

                reason,
                created_at
            )
        )

        rerouting_id = cursor.lastrowid

        connection.commit()

        return rerouting_id

    finally:
        connection.close()


# ============================================================
# GET REROUTING EVENT BY FAULT
# ============================================================

def get_rerouting_event_by_fault(
    device_id,
    fault_id
):
    """
    Return an existing rerouting event associated with a fault.

    This prevents every critical telemetry packet from creating
    another rerouting recommendation for the same fault.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM rerouting_events

            WHERE device_id = ?
              AND triggered_by_fault = ?

            ORDER BY id DESC
            LIMIT 1
            """,
            (
                device_id,
                fault_id
            )
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        connection.close()


# ============================================================
# GET LATEST REROUTING EVENT
# ============================================================

def get_latest_rerouting_event(device_id):
    """
    Return the latest rerouting recommendation for a device.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM rerouting_events

            WHERE device_id = ?

            ORDER BY id DESC
            LIMIT 1
            """,
            (device_id,)
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return dict(row)

    finally:
        connection.close()


# ============================================================
# GET REROUTING HISTORY
# ============================================================

def get_rerouting_history(
    device_id,
    limit=100
):
    """
    Return recent Tier-3 rerouting history.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM rerouting_events

            WHERE device_id = ?

            ORDER BY id DESC
            LIMIT ?
            """,
            (
                device_id,
                limit
            )
        )

        rows = cursor.fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:
        connection.close()