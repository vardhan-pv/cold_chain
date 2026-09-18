"""Persist intent, receive device ACK, then independently confirm later telemetry.

Every command is bound to a device, boot and fresh decision. The local safety
controller is authoritative; an ACK cannot bypass its interlock or fault latch.
"""
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from database.models import ControlCommand, Device, serialize

ACTIVE = ('PENDING', 'ACKNOWLEDGED')

def expire(session, device_id, now):
    device = session.get(Device, device_id)
    for row in session.scalars(select(ControlCommand).where(
            ControlCommand.device_id == device_id, ControlCommand.status.in_(ACTIVE))):
        if not device or device.active_boot != row.boot_id:
            row.status = 'SUPERSEDED'
        elif datetime.fromisoformat(row.expires_at) <= now:
            row.status = 'EXPIRED'

def track(session, telemetry, decision, fault_id):
    now = datetime.now(timezone.utc)
    expire(session, telemetry.device_id, now)
    recent = session.scalars(select(ControlCommand).where(
        ControlCommand.device_id == telemetry.device_id).order_by(ControlCommand.id.desc())).all()
    for command in recent:
        if command.status == 'ACKNOWLEDGED' and command.boot_id == telemetry.boot_id:
            ack_sequence = command.acknowledgement['sequence']
            if telemetry.sequence > max(command.based_on_sequence, ack_sequence) and (
                telemetry.primary_cooling == command.primary_cooling and
                telemetry.backup_cooling == command.backup_cooling):
                command.status = 'CONFIRMED'
                command.confirmed_at = telemetry.timestamp.isoformat()
    target = (decision['primary_cooling'], decision['backup_cooling'])
    command_type = ('ACTIVATE_BACKUP_COOLING' if target[1] else
                    'RESTORE_PRIMARY_COOLING' if target[0] else 'STOP_ALL_COOLING')
    last = recent[0] if recent else None
    if last and last.boot_id == telemetry.boot_id and (
            last.primary_cooling, last.backup_cooling) == target and last.status not in (
                'EXPIRED', 'REJECTED', 'SUPERSEDED'):
        return {**serialize(last), 'created': False}
    for command in recent:
        if command.status in ACTIVE:
            command.status = 'SUPERSEDED'
    # No command needed when already stable, unless recording a new transition.
    if target == (telemetry.primary_cooling, telemetry.backup_cooling) and not decision['transitions']:
        return None
    command = ControlCommand(device_id=telemetry.device_id, boot_id=telemetry.boot_id,
        based_on_sequence=telemetry.sequence, command_type=command_type,
        primary_cooling=target[0], backup_cooling=target[1], reason=decision['reason'],
        triggered_by_fault=fault_id, status='PENDING', created_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=30)).isoformat())
    session.add(command)
    session.flush()
    return {**serialize(command), 'created': True}

def pending(service, device_id):
    with service.lock, service.Session.begin() as session:
        if not session.get(Device, device_id):
            raise HTTPException(404, 'Device not found')
        expire(session, device_id, datetime.now(timezone.utc))
        session.flush()
        command = session.scalar(select(ControlCommand).where(
            ControlCommand.device_id == device_id, ControlCommand.status == 'PENDING')
            .order_by(ControlCommand.id.desc()).limit(1))
        return {'device_id': device_id, 'command_available': command is not None,
            'command': {**serialize(command), 'session_id': command.boot_id,
                'execution_policy': 'LOCAL_INTERLOCK_REQUIRED'} if command else None}

def acknowledge(service, command_id, data):
    error = None
    with service.lock, service.Session.begin() as session:
        command = session.get(ControlCommand, command_id)
        if not command or command.device_id != data.device_id:
            raise HTTPException(404, 'Command not found for this device')
        expire(session, data.device_id, datetime.now(timezone.utc))
        payload = data.model_dump()
        if command.boot_id != data.boot_id:
            error = 'Command belongs to a different boot'
        elif command.acknowledgement == payload and command.status in ('ACKNOWLEDGED', 'CONFIRMED', 'REJECTED'):
            pass  # Lost HTTP responses can be retried without duplicating effects.
        elif command.status != 'PENDING':
            error = 'Command is expired, superseded or already acknowledged differently'
        elif data.sequence < command.based_on_sequence:
            error = 'Acknowledgement predates the command evidence'
        elif data.outcome == 'APPLIED' and (data.primary_cooling, data.backup_cooling) != (
                command.primary_cooling, command.backup_cooling):
            error = 'Reported outputs do not match requested outputs'
        else:
            command.acknowledgement = payload
            command.acknowledged_at = datetime.now(timezone.utc).isoformat()
            command.status = 'ACKNOWLEDGED' if data.outcome == 'APPLIED' else 'REJECTED'
        result = serialize(command)
    if error:
        raise HTTPException(409, error)
    return {'acknowledged': True, 'command_id': command_id, 'status': result['status'],
        'acknowledged_at': result['acknowledged_at'], 'physical_verification': 'PENDING_HARDWARE'}
