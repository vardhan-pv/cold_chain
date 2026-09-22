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
