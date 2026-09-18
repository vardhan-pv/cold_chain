"""Lossless, idempotent import of earlier SQLite records; never replay control."""
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, func
from fastapi import HTTPException
from database.models import ArchiveImport, ArchiveRecord, serialize

TABLES = ('telemetry', 'fault_events', 'system_state', 'control_commands', 'rerouting_events')

def import_legacy(service, source):
    source = Path(source).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with service.lock, service.Session.begin() as session:
        existing = session.get(ArchiveImport, digest)
        if existing:
            return {**serialize(existing), 'already_imported': True}
        # Read-only connection: source snapshots are never upgraded or mutated.
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as old:
            old.row_factory = sqlite3.Row
            present = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'telemetry' not in present:
                raise ValueError('Source is not a cold-chain telemetry database')
            columns = {r[1] for r in old.execute('PRAGMA table_info(telemetry)')}
            if not {'telemetry_source', 'simulation_mode', 'current_a'} <= columns:
                raise ValueError('Source does not use the older project telemetry schema')
            counts = {}
            records = []
            for table in TABLES:
                if table not in present:
                    continue
                rows = old.execute(f'SELECT * FROM "{table}"').fetchall()  # table names are fixed above
                counts[table] = len(rows)
                for i, row in enumerate(rows):
                    payload = dict(row)
                    records.append(ArchiveRecord(source_sha256=digest, table_name=table,
                        source_key=str(payload.get('id', payload.get('device_id', i))),
                        device_id=payload.get('device_id'), payload=payload))
            entry = ArchiveImport(source_sha256=digest, source_name=source.name,
                imported_at=datetime.now(timezone.utc).isoformat(), table_counts=counts)
            session.add(entry)
            session.flush()
            session.add_all(records)
            return {**serialize(entry), 'already_imported': False}

def archive_rows(service, source, table, device_id=None, limit=100, offset=0):
    if table not in TABLES:
        raise HTTPException(404, 'Unknown archive table')
    with service.Session() as session:
        entry = session.get(ArchiveImport, source)
        if not entry:
            raise HTTPException(404, 'Archive source not found')
        query = select(ArchiveRecord).where(ArchiveRecord.source_sha256 == source,
            ArchiveRecord.table_name == table)
        if device_id:
            query = query.where(ArchiveRecord.device_id == device_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(ArchiveRecord.id.desc()).offset(offset).limit(limit)).all()
        return {'source': serialize(entry), 'table': table, 'total': total, 'offset': offset,
            'records': [r.payload for r in rows], 'control_replayed': False,
            'provenance': 'ORIGINAL_UPLOAD_ARCHIVE',
            'notice': 'Historical records retain original labels and values. Legacy current_a is not a verified primary or backup measurement. No records are physical-validation evidence.'}
