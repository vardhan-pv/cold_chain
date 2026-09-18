"""
Cloud-Integrated Self-Healing & Predictive Maintenance System
for Cold-Chain Logistics

Digital Telemetry Simulator

This program temporarily replaces the physical ESP32-S3 and sensors.

The simulator now also behaves like the future actuator controller:
1. Generate telemetry.
2. Send telemetry to FastAPI.
3. Poll for pending self-healing commands.
4. Apply the commanded cooling state.
5. Acknowledge the command.
6. Preserve the actuator state across later telemetry packets.

When the hardware arrives, the ESP32-S3 will implement the same
telemetry and command lifecycle.
"""

import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone

import requests

from scenarios import get_scenario


# ============================================================
# CONFIGURATION
# ============================================================

DEVICE_ID = "CCU-001"

API_URL = "http://127.0.0.1:8000/api/v1/telemetry"

CONTROL_BASE_URL = (
    "http://127.0.0.1:8000/api/v1/control"
)

# Demonstration coordinates only.
START_LATITUDE = 12.9000
START_LONGITUDE = 77.6500


# ============================================================
# SIMULATOR
# ============================================================

class ColdChainSimulator:

    def __init__(self, scenario_name="normal"):

        self.device_id = DEVICE_ID

        # Unique ID for every simulator run.
        self.session_id = str(uuid.uuid4())

        self.scenario_name = scenario_name

        self.latitude = START_LATITUDE
        self.longitude = START_LONGITUDE

        self.sequence = 0

        # ----------------------------------------------------
        # PERSISTENT ACTUATOR STATE
        # ----------------------------------------------------
        #
        # Scenario values represent the initial physical state.
        #
        # Once a backend control command is applied, these
        # variables preserve the new state instead of allowing
        # scenarios.py to overwrite it on every packet.
        # ----------------------------------------------------

        scenario = get_scenario(
            self.scenario_name
        )

        self.primary_cooling = bool(
            scenario["primary_cooling"]
        )

        self.backup_cooling = bool(
            scenario["backup_cooling"]
        )

        self.control_override_active = False

        self.last_applied_command_id = None


    @staticmethod
    def vary(target, variation):

        return round(
            random.uniform(
                target - variation,
                target + variation
            ),
            2
        )


    def update_location(self):

        self.latitude += random.uniform(
            -0.00005,
            0.00005
        )

        self.longitude += random.uniform(
            -0.00005,
            0.00005
        )


    # ========================================================
    # TELEMETRY GENERATION
    # ========================================================

    def generate_telemetry(self):

        scenario = get_scenario(
            self.scenario_name
        )

        self.sequence += 1

        self.update_location()

        chamber_temp = self.vary(
            scenario["temp_target"],
            scenario["temp_variation"]
        )

        heatsink_temp = self.vary(
            scenario["heatsink_target"],
            scenario["heatsink_variation"]
        )

        humidity = self.vary(
            scenario["humidity_target"],
            scenario["humidity_variation"]
        )

        # ----------------------------------------------------
        # CURRENT SIMULATION
        # ----------------------------------------------------
        #
        # Before self-healing:
        # primary_fault scenario produces abnormal low current.
        #
        # After backup activation:
        # current should represent the backup cooling system,
        # rather than continuing to report the failed primary
        # current forever.
        # ----------------------------------------------------

        if (
            self.control_override_active
            and not self.primary_cooling
            and self.backup_cooling
        ):

            # Development/demo value representing a functioning
            # backup Peltier load.
            current = self.vary(
                2.0,
                0.25
            )

        elif (
            not self.primary_cooling
            and not self.backup_cooling
        ):

            current = self.vary(
                0.1,
                0.05
            )

        else:

            current = max(
                0.0,
                self.vary(
                    scenario["current_target"],
                    scenario[
                        "current_variation"
                    ]
                )
            )

        telemetry = {

            "device_id":
                self.device_id,

            "session_id":
                self.session_id,

            "sequence":
                self.sequence,

            "timestamp":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "telemetry_source":
                "SIMULATOR",

            "simulation_mode":
                True,

            "chamber_temp_c":
                chamber_temp,

            "heatsink_temp_c":
                heatsink_temp,

            "humidity_pct":
                humidity,

            "current_a":
                current,

            "door_open":
                scenario["door_open"],

            # IMPORTANT:
            # These now come from persistent actuator state,
            # not directly from scenarios.py.
            "primary_cooling":
                self.primary_cooling,

            "backup_cooling":
                self.backup_cooling,

            "gps": {

                "latitude":
                    round(
                        self.latitude,
                        6
                    ),

                "longitude":
                    round(
                        self.longitude,
                        6
                    ),

                "valid":
                    True,

                "source":
                    "SIMULATED"
            },

            "scenario":
                self.scenario_name
        }

        return telemetry


    # ========================================================
    # TELEMETRY TRANSMISSION
    # ========================================================

    def send_telemetry(self, telemetry):

        try:

            response = requests.post(
                API_URL,
                json=telemetry,
                timeout=5
            )

            if response.status_code == 200:

                result = response.json()

                print(
                    f"API: 200 OK | "
                    f"Device: "
                    f"{result.get('device_id')} | "
                    f"Sequence: "
                    f"{result.get('sequence')} | "
                    f"Stored: "
                    f"{result.get('stored')}"
                )

                return True

            print(
                f"API ERROR: HTTP "
                f"{response.status_code}"
            )

            print(
                response.text
            )

            return False


        except requests.exceptions.ConnectionError:

            print(
                "API ERROR: Cannot connect to backend."
            )

            print(
                "Make sure FastAPI is running at "
                "http://127.0.0.1:8000"
            )

            return False


        except requests.exceptions.Timeout:

            print(
                "API ERROR: Backend request timed out."
            )

            return False


        except requests.exceptions.RequestException as error:

            print(
                f"API ERROR: {error}"
            )

            return False


    # ========================================================
    # FETCH PENDING CONTROL COMMAND
    # ========================================================

    def fetch_pending_command(self):

        url = (
            f"{CONTROL_BASE_URL}/"
            f"{self.device_id}/pending"
        )

        try:

            response = requests.get(
                url,
                timeout=5
            )

            if response.status_code != 200:

                print(
                    "CONTROL ERROR: "
                    f"HTTP {response.status_code}"
                )

                return None

            result = response.json()

            if not result.get(
                "command_available",
                False
            ):

                return None

            return result.get(
                "command"
            )


        except requests.exceptions.ConnectionError:

            print(
                "CONTROL ERROR: Cannot connect "
                "to backend."
            )

            return None


        except requests.exceptions.Timeout:

            print(
                "CONTROL ERROR: Request timed out."
            )

            return None


        except requests.exceptions.RequestException as error:

            print(
                f"CONTROL ERROR: {error}"
            )

            return None


    # ========================================================
    # APPLY CONTROL COMMAND
    # ========================================================

    def apply_control_command(
        self,
        command
    ):

        if not command:

            return False

        command_id = command.get(
            "id"
        )

        command_type = command.get(
            "command_type"
        )

        # Prevent accidental duplicate local application.
        if (
            self.last_applied_command_id
            == command_id
        ):

            return False

        target_primary = bool(
            command.get(
                "primary_cooling",
                False
            )
        )

        target_backup = bool(
            command.get(
                "backup_cooling",
                False
            )
        )

        print()
        print(
            ">>> SELF-HEALING COMMAND RECEIVED"
        )

        print(
            f"Command ID     : {command_id}"
        )

        print(
            f"Command Type   : {command_type}"
        )

        print(
            f"Primary Target : "
            f"{target_primary}"
        )

        print(
            f"Backup Target  : "
            f"{target_backup}"
        )

        print(
            f"Reason         : "
            f"{command.get('reason')}"
        )

        # ----------------------------------------------------
        # INTERLOCK SAFETY
        # ----------------------------------------------------
        #
        # Architecture requires that primary and backup
        # Peltiers must not be active simultaneously.
        # ----------------------------------------------------

        if (
            target_primary
            and target_backup
        ):

            print(
                "CONTROL REJECTED: Primary and "
                "backup cooling cannot both be ON."
            )

            return False

        # Apply commanded state.
        self.primary_cooling = (
            target_primary
        )

        self.backup_cooling = (
            target_backup
        )

        self.control_override_active = True

        self.last_applied_command_id = (
            command_id
        )

        print(
            "Command applied locally."
        )

        print(
            f"Primary Cooling: "
            f"{self.primary_cooling}"
        )

        print(
            f"Backup Cooling : "
            f"{self.backup_cooling}"
        )

        return True


    # ========================================================
    # ACKNOWLEDGE CONTROL COMMAND
    # ========================================================

    def acknowledge_command(
        self,
        command_id
    ):

        url = (
            f"{CONTROL_BASE_URL}/"
            f"{command_id}/acknowledge"
        )

        try:

            response = requests.post(
                url,
                timeout=5
            )

            if response.status_code == 200:

                result = response.json()

                print(
                    f"Command #{command_id} "
                    f"ACKNOWLEDGED by backend."
                )

                return result.get(
                    "acknowledged",
                    False
                )

            print(
                "ACK ERROR: "
                f"HTTP {response.status_code}"
            )

            print(
                response.text
            )

            return False


        except requests.exceptions.ConnectionError:

            print(
                "ACK ERROR: Cannot connect "
                "to backend."
            )

            return False


        except requests.exceptions.Timeout:

            print(
                "ACK ERROR: Request timed out."
            )

            return False


        except requests.exceptions.RequestException as error:

            print(
                f"ACK ERROR: {error}"
            )

            return False


    # ========================================================
    # CONTROL LOOP
    # ========================================================

    def process_control_commands(self):

        command = (
            self.fetch_pending_command()
        )

        if command is None:

            return

        applied = (
            self.apply_control_command(
                command
            )
        )

        if not applied:

            return

        acknowledged = (
            self.acknowledge_command(
                command["id"]
            )
        )

        if acknowledged:

            print(
                "Self-healing command lifecycle "
                "completed."
            )

        else:

            print(
                "WARNING: Command was applied "
                "locally but acknowledgement "
                "failed."
            )


    # ========================================================
    # MAIN LOOP
    # ========================================================

    def run(self, interval=5):

        scenario = get_scenario(
            self.scenario_name
        )

        print()
        print("=" * 72)

        print(
            " COLD-CHAIN DIGITAL TELEMETRY SIMULATOR"
        )

        print("=" * 72)

        print(
            f"Device       : {self.device_id}"
        )

        print(
            f"Session      : {self.session_id}"
        )

        print(
            f"Scenario     : {scenario['name']}"
        )

        print(
            f"Description  : "
            f"{scenario['description']}"
        )

        print(
            f"Interval     : {interval} seconds"
        )

        print(
            "Data Source  : SIMULATED"
        )

        print(
            f"Backend API  : {API_URL}"
        )

        print(
            f"Control API  : "
            f"{CONTROL_BASE_URL}"
        )

        print("=" * 72)

        print(
            "Press Ctrl+C to stop.\n"
        )

        try:

            while True:

                # --------------------------------------------
                # 1. Generate telemetry representing current
                #    physical / simulated state.
                # --------------------------------------------

                telemetry = (
                    self.generate_telemetry()
                )

                print(
                    json.dumps(
                        telemetry,
                        indent=2
                    )
                )

                # --------------------------------------------
                # 2. Report current state to backend.
                # --------------------------------------------

                success = (
                    self.send_telemetry(
                        telemetry
                    )
                )

                if success:

                    print(
                        "Transmission : SUCCESS"
                    )

                    # ----------------------------------------
                    # 3. After backend processes telemetry,
                    #    check for self-healing commands.
                    # ----------------------------------------

                    self.process_control_commands()

                else:

                    print(
                        "Transmission : FAILED"
                    )

                print(
                    "-" * 72
                )

                time.sleep(
                    interval
                )


        except KeyboardInterrupt:

            print()

            print("=" * 72)

            print(
                "Simulator stopped safely."
            )

            print("=" * 72)


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Cold-Chain IoT Digital "
            "Telemetry Simulator"
        )
    )

    parser.add_argument(
        "--scenario",

        default="normal",

        choices=[
            "normal",
            "door_open",
            "primary_fault",
            "critical_fault"
        ],

        help="Operating scenario"
    )

    parser.add_argument(
        "--interval",

        type=int,

        default=5,

        help="Telemetry interval in seconds"
    )

    args = parser.parse_args()

    if args.interval < 1:

        parser.error(
            "--interval must be at least "
            "1 second"
        )

    simulator = ColdChainSimulator(
        scenario_name=args.scenario
    )

    simulator.run(
        interval=args.interval
    )


if __name__ == "__main__":
    main()