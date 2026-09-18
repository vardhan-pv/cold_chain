"""
Cold-Chain Simulated Warehouse Registry

This module contains development/demo warehouse destinations
used by the Tier-3 rerouting engine.

IMPORTANT:
These facilities are SIMULATED.
They are NOT real warehouse claims.

Later this registry can be replaced with:
- cloud database warehouse records
- logistics partner APIs
- live capacity systems
- real geographic destinations
"""


SIMULATED_WAREHOUSES = [

    {
        "warehouse_id": "SIM-WH-001",
        "name": "Simulated Cold Storage Alpha",

        "latitude": 12.9150,
        "longitude": 77.6400,

        "operational": True,

        "min_temperature_c": 2.0,
        "max_temperature_c": 8.0,

        "available_capacity_kg": 500.0,

        "data_source": "SIMULATED"
    },

    {
        "warehouse_id": "SIM-WH-002",
        "name": "Simulated Cold Storage Beta",

        "latitude": 12.8750,
        "longitude": 77.6700,

        "operational": True,

        "min_temperature_c": 0.0,
        "max_temperature_c": 10.0,

        "available_capacity_kg": 250.0,

        "data_source": "SIMULATED"
    },

    {
        "warehouse_id": "SIM-WH-003",
        "name": "Simulated Cold Storage Gamma",

        "latitude": 12.9400,
        "longitude": 77.6900,

        "operational": True,

        "min_temperature_c": -5.0,
        "max_temperature_c": 5.0,

        "available_capacity_kg": 1000.0,

        "data_source": "SIMULATED"
    },

    {
        "warehouse_id": "SIM-WH-004",
        "name": "Simulated Cold Storage Delta",

        "latitude": 12.8900,
        "longitude": 77.6100,

        "operational": False,

        "min_temperature_c": 2.0,
        "max_temperature_c": 8.0,

        "available_capacity_kg": 700.0,

        "data_source": "SIMULATED"
    },

    {
        "warehouse_id": "SIM-WH-005",
        "name": "Simulated Cold Storage Epsilon",

        "latitude": 12.8600,
        "longitude": 77.6300,

        "operational": True,

        "min_temperature_c": 2.0,
        "max_temperature_c": 8.0,

        "available_capacity_kg": 0.0,

        "data_source": "SIMULATED"
    }
]


def get_all_warehouses():
    """
    Return all simulated warehouse destinations.
    """

    return [
        warehouse.copy()
        for warehouse in SIMULATED_WAREHOUSES
    ]