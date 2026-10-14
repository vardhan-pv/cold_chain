"""Central runtime and hybrid demo configuration."""
import os

# Hybrid demonstration current emulation mode:
# Enables real physical hardware data stream to produce complete ML feature vectors
# without falsifying physical ACS712 sensor calibration.
ENABLE_EMULATED_CURRENT: bool = os.getenv("ENABLE_EMULATED_CURRENT", "true").lower() in ("true", "1", "yes")

# Configured realistic load current when primary cooling is commanded ON
EMULATED_PRIMARY_CURRENT_A: float = float(os.getenv("EMULATED_PRIMARY_CURRENT_A", "3.5"))

# Configured idle current when primary cooling is OFF
EMULATED_IDLE_CURRENT_A: float = 0.0

# Real GIS / Mapping & Emergency Routing Providers:
GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
OPENROUTESERVICE_API_KEY: str = os.getenv("OPENROUTESERVICE_API_KEY", "")
OPENROUTESERVICE_URL: str = os.getenv("OPENROUTESERVICE_URL", "https://api.heigit.org/openrouteservice/v2/directions/driving-car")
OVERPASS_API_URL: str = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")

# Navigation Demo / Fallback Coordinates:
# Priority: Physical ESP32 GPS takes precedence. If no satellite fix, these coordinates allow real map discovery.
DEMO_GPS_LAT: float | None = float(os.getenv("DEMO_GPS_LAT")) if os.getenv("DEMO_GPS_LAT") else None
DEMO_GPS_LNG: float | None = float(os.getenv("DEMO_GPS_LNG")) if os.getenv("DEMO_GPS_LNG") else None

