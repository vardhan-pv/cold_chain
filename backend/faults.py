"""Incident lifecycle. Backup operation mitigates a fault; it does not repair it."""
from sqlalchemy import select
from database.models import FaultEvent

def update_faults(session, telemetry, decision, prediction):
    state = decision['state']
    active = [row for row in session.scalars(select(FaultEvent).where(
        FaultEvent.device_id == telemetry.device_id).order_by(FaultEvent.id.desc()))
        if not row.payload.get('resolved', False)]
    category = ('CRITICAL_FAILURE' if state in ('CRITICAL_FAILURE', 'REROUTING') else
                'PRIMARY_FAILURE' if state == 'PRIMARY_FAULT' else
                'WARNING' if state == 'WARNING' else None)
    if state in ('BACKUP_ACTIVE', 'RECOVERY') and not telemetry.backup_cooling:
        category = 'PRIMARY_FAILURE' if any(r.payload.get('fault_type') == 'PRIMARY_FAILURE' for r in active) else None
    incident = None
    for row in active:
        if row.payload.get('fault_type') == category:
            incident = row
        else:
            row.payload = {**row.payload, 'resolved': True, 'resolved_at': telemetry.timestamp.isoformat(),
                'resolution': 'MITIGATED_BY_BACKUP' if state in ('BACKUP_ACTIVE', 'RECOVERY') else
                              'SUPERSEDED_BY_HIGHER_PRIORITY' if category else 'CONDITION_CLEARED',
                'hardware_repair_verified': False}
    if category and incident is None:
        change = decision['transitions'][-1] if decision['transitions'] else {}
        incident = FaultEvent(device_id=telemetry.device_id, timestamp=telemetry.timestamp.isoformat(),
            payload={'fault_type': category, 'new_state': state, 'system_state': state,
                'boot_id': telemetry.boot_id, 'severity': 'CRITICAL' if category == 'CRITICAL_FAILURE' else
                            'HIGH' if category == 'PRIMARY_FAILURE' else 'MEDIUM',
                'reason': decision['reason'], 'source': change.get('source', 'SENSOR_RULE'),
                'sensor_evidence': telemetry.model_dump(mode='json'), 'mode': telemetry.mode,
                'ml_probability': prediction.get('ensemble_probability'),
                'resolved': False, 'resolved_at': None, 'recovery_verified_in_hardware': False})
        session.add(incident)
        session.flush()
    return incident.id if incident else None
