"""Register physical CCU-HW-001 hardware device with dedicated device token."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import hashlib
import json
import secrets
from database.models import database, Device

DB_PATH = ROOT / "runtime/cold_chain.db"
HW_SECRETS_PATH = ROOT / "runtime/hardware_device.json"

def main():
    engine, Session = database(f"sqlite:///{DB_PATH}")
    device_id = "CCU-HW-001"
    
    # Load or generate a dedicated device token for the ESP32
    if HW_SECRETS_PATH.exists():
        try:
            token = json.loads(HW_SECRETS_PATH.read_text()).get("device_token", "")
        except Exception:
            token = ""
    else:
        token = ""

    if not token or len(token) < 16:
        token = secrets.token_urlsafe(32)
        HW_SECRETS_PATH.write_text(json.dumps({"device_id": device_id, "device_token": token}, indent=2))
        print(f"Generated new dedicated hardware token and saved to {HW_SECRETS_PATH}")
    else:
        print(f"Using existing dedicated hardware token from {HW_SECRETS_PATH}")

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with Session.begin() as s:
        existing = s.get(Device, device_id)
        if existing:
            existing.token_hash = token_hash
            existing.mode = "HARDWARE"
            existing.name = "ESP32-S3 Physical Node"
            print(f"Updated existing hardware device in database: {device_id}")
        else:
            dev = Device(
                device_id=device_id,
                name="ESP32-S3 Physical Node",
                mode="HARDWARE",
                token_hash=token_hash,
                controller={},
                retired_boots=[],
            )
            s.add(dev)
            print(f"Registered new hardware device in database: {device_id}")

    print("\n--- HARDWARE REGISTRATION DETAILS ---")
    print(f"Device ID:    {device_id}")
    print(f"Device Mode:  HARDWARE")
    print(f"Device Token: {token}")
    print("------------------------------------\n")

if __name__ == "__main__":
    main()
