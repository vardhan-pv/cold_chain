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
OVERPASS_API_URL: str = os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter")

