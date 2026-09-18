"""Direct Uvicorn entry point. CC_ADMIN_TOKEN is optional (auto-generated if not provided)."""
from backend.main import create_app
app = create_app(run_simulation=True)
