"""Keep the uploaded project's read and command URLs on the single new service."""
from fastapi import APIRouter, Depends, Header, Query, HTTPException
from backend import commands
from backend.schemas import CommandAcknowledgement
from database.models import TelemetryRow, ReroutingEvent, ControlCommand, FaultEvent

def router_for(service, operator):
    router = APIRouter(prefix='/api/v1', tags=['Project compatibility'])
    auth = [Depends(operator)]

    @router.get('/control/{device_id}/pending')
    def pending(device_id: str, x_device_token: str = Header(default='')):
        service.authenticate_device(device_id, x_device_token)
        return commands.pending(service, device_id)

    @router.post('/control/{command_id}/acknowledge')
    def acknowledge(command_id: int, data: CommandAcknowledgement, x_device_token: str = Header(default='')):
        service.authenticate_device(data.device_id, x_device_token)
        return commands.acknowledge(service, command_id, data)

    @router.get('/control/{device_id}/history', dependencies=auth)
    def history(device_id: str, limit: int = Query(100, ge=1, le=1000)):
        service.latest(device_id)
        rows = service.rows(ControlCommand, device_id, limit)
        return {'device_id': device_id, 'count': len(rows), 'commands': rows}

    @router.get('/telemetry/{device_id}/latest', dependencies=auth)
    def latest(device_id: str):
        result = service.latest(device_id)['telemetry']
        if not result:
            raise HTTPException(404, 'No live telemetry for this device; original data is under /api/archive')
        return result

    @router.get('/telemetry/{device_id}/history', dependencies=auth)
    def telemetry_history(device_id: str, limit: int = Query(100, ge=1, le=1000)):
        service.latest(device_id)
        rows = service.rows(TelemetryRow, device_id, limit)
        return {'device_id': device_id, 'count': len(rows), 'telemetry': rows}

    @router.get('/rerouting/{device_id}/latest', dependencies=auth)
    def latest_rerouting(device_id: str):
        service.latest(device_id)
        rows = service.rows(ReroutingEvent, device_id, 1)
        return {'device_id': device_id, 'rerouting_available': bool(rows), 'event': rows[0] if rows else None}

    @router.get('/rerouting/{device_id}/history', dependencies=auth)
    def rerouting_history(device_id: str, limit: int = Query(100, ge=1, le=500)):
        service.latest(device_id)
        rows = service.rows(ReroutingEvent, device_id, limit)
        return {'device_id': device_id, 'count': len(rows), 'events': rows}

    @router.get('/faults/{device_id}/history', dependencies=auth)
    def fault_history(device_id: str, limit: int = Query(100, ge=1, le=1000)):
        service.latest(device_id)
        rows = service.rows(FaultEvent, device_id, limit)
        return {'device_id': device_id, 'count': len(rows), 'events': rows}

    return router
