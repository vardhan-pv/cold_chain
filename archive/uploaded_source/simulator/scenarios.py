"""
Cold-Chain Digital Simulator
Scenario definitions.

These scenarios simulate conditions that will later be produced
by the real ESP32-S3 and physical sensors.

IMPORTANT:
The simulator reports physical/sensor conditions.
It must NOT perform self-healing decisions itself.

For example, during a primary cooling failure:
- Primary cooling is still commanded ON.
- Measured current becomes abnormally low.
- Backup remains OFF until the self-healing controller decides
  to activate it.
"""


SCENARIOS = {

    # ========================================================
    # NORMAL OPERATION
    # ========================================================

    "normal": {
        "name": "Normal Operation",
        "description": "Cold-chain unit operating normally.",

        "temp_target": 4.0,
        "temp_variation": 0.4,

        "humidity_target": 60.0,
        "humidity_variation": 3.0,

        "heatsink_target": 36.0,
        "heatsink_variation": 2.0,

        "current_target": 5.5,
        "current_variation": 0.3,

        "door_open": False,

        "primary_cooling": True,
        "backup_cooling": False,
    },


    # ========================================================
    # DOOR OPEN
    # ========================================================

    "door_open": {
        "name": "Door Open",
        "description": "Cold-chain chamber door left open.",

        "temp_target": 7.5,
        "temp_variation": 0.8,

        "humidity_target": 70.0,
        "humidity_variation": 5.0,

        "heatsink_target": 38.0,
        "heatsink_variation": 2.0,

        "current_target": 5.7,
        "current_variation": 0.3,

        "door_open": True,

        "primary_cooling": True,
        "backup_cooling": False,
    },


    # ========================================================
    # PRIMARY COOLING FAILURE
    # ========================================================
    #
    # Primary is COMMANDED ON but is not drawing its expected
    # electrical current.
    #
    # This represents the actual failure condition.
    #
    # The simulator deliberately does NOT turn the backup
    # cooling ON. That decision belongs to the self-healing
    # controller.
    # ========================================================

    "primary_fault": {
        "name": "Primary Cooling Fault",

        "description": (
            "Primary cooling is commanded ON but abnormal low "
            "current indicates that the primary cooling system "
            "is not operating correctly."
        ),

        "temp_target": 10.0,
        "temp_variation": 1.0,

        "humidity_target": 67.0,
        "humidity_variation": 4.0,

        "heatsink_target": 48.0,
        "heatsink_variation": 3.0,

        # Keep maximum simulated value below the current
        # detector threshold of 1.0 A.
        #
        # Range approximately:
        # 0.10 A to 0.70 A
        "current_target": 0.4,
        "current_variation": 0.3,

        "door_open": False,

        # Controller is requesting the primary cooler to run.
        "primary_cooling": True,

        # Self-healing has NOT happened yet.
        "backup_cooling": False,
    },


    # ========================================================
    # CRITICAL COOLING FAILURE
    # ========================================================

    "critical_fault": {
        "name": "Critical Cooling Failure",
        "description": "Primary and backup cooling are unavailable.",

        "temp_target": 15.0,
        "temp_variation": 1.5,

        "humidity_target": 75.0,
        "humidity_variation": 5.0,

        "heatsink_target": 55.0,
        "heatsink_variation": 4.0,

        "current_target": 0.1,
        "current_variation": 0.05,

        "door_open": False,

        "primary_cooling": False,
        "backup_cooling": False,
    },
}


def get_scenario(name: str):
    """Return a simulator scenario by name."""
    return SCENARIOS.get(name, SCENARIOS["normal"])