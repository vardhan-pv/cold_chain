from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.telemetry import router as telemetry_router
from backend.api.control import router as control_router
from backend.database.db import (
    DATABASE_PATH,
    initialize_database,
)
from backend.api.rerouting import router as rerouting_router

# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Cold-Chain Predictive Maintenance API",
    description=(
        "Backend API for the Cloud-Integrated Self-Healing & "
        "Predictive Maintenance System for Cold-Chain Logistics."
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

initialize_database()

print(
    f"Cold-Chain database initialized: {DATABASE_PATH}"
)


# ============================================================
# API ROUTES
# ============================================================

app.include_router(telemetry_router)
app.include_router(control_router)
app.include_router(rerouting_router)

# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():
    return {
        "project": "Cold-Chain Predictive Maintenance System",
        "api_version": "1.0.0",
        "status": "running",
    }


# ============================================================
# HEALTH ENDPOINT
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "cold-chain-backend",
        "database": "connected",
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
    }