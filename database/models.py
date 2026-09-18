"""SQLAlchemy mappings; SQLite default, PostgreSQL-compatible column types."""
from sqlalchemy import create_engine, String, Integer, Float, Boolean, Text, JSON, ForeignKey, UniqueConstraint, CheckConstraint, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

class Base(DeclarativeBase):
    pass

class Device(Base):
    __tablename__ = 'devices'
    device_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64))
    last_seen: Mapped[str | None] = mapped_column(String(40), nullable=True)
    controller: Mapped[dict] = mapped_column(JSON, default=dict)
    active_boot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retired_boots: Mapped[list] = mapped_column(JSON, default=list)

class TelemetryRow(Base):
    __tablename__ = 'telemetry'
    __table_args__ = (UniqueConstraint('device_id', 'boot_id', 'sequence'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    boot_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[str] = mapped_column(String(40), index=True)
    received_at: Mapped[str] = mapped_column(String(40))
    mode: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[dict] = mapped_column(JSON)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

class Prediction(Base):
    __tablename__ = 'predictions'
    id: Mapped[int] = mapped_column(primary_key=True)
    telemetry_id: Mapped[int] = mapped_column(ForeignKey('telemetry.id'), unique=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class FaultEvent(Base):
    __tablename__ = 'fault_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class HealingEvent(Base):
    __tablename__ = 'self_healing_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class Warehouse(Base):
    __tablename__ = 'warehouses'
    warehouse_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    available: Mapped[bool] = mapped_column(Boolean)
    capacity: Mapped[float] = mapped_column(Float)
    minimum_temperature: Mapped[float] = mapped_column(Float)
    maximum_temperature: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))

class ReroutingEvent(Base):
    __tablename__ = 'rerouting_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class SystemHealth(Base):
    __tablename__ = 'system_health'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class TestResult(Base):
    __tablename__ = 'test_results'
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    timestamp: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)

class ControlCommand(Base):
    __tablename__ = 'control_commands'
    __table_args__ = (CheckConstraint('NOT (primary_cooling AND backup_cooling)', name='cooling_interlock'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.device_id'), index=True)
    boot_id: Mapped[str] = mapped_column(String(64))
    based_on_sequence: Mapped[int] = mapped_column(Integer)
    command_type: Mapped[str] = mapped_column(String(40))
    primary_cooling: Mapped[bool] = mapped_column(Boolean)
    backup_cooling: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    triggered_by_fault: Mapped[int | None] = mapped_column(ForeignKey('fault_events.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default='PENDING', index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))
    acknowledged_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confirmed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    acknowledgement: Mapped[dict | None] = mapped_column(JSON, nullable=True)

class ArchiveImport(Base):
    __tablename__ = 'archive_imports'
    source_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100))
    imported_at: Mapped[str] = mapped_column(String(40))
    table_counts: Mapped[dict] = mapped_column(JSON)

class ArchiveRecord(Base):
    __tablename__ = 'archive_records'
    __table_args__ = (UniqueConstraint('source_sha256', 'table_name', 'source_key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_sha256: Mapped[str] = mapped_column(ForeignKey('archive_imports.source_sha256'), index=True)
    table_name: Mapped[str] = mapped_column(String(40), index=True)
    source_key: Mapped[str] = mapped_column(String(100))
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)

def database(url):
    args = {'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}
    options = {'poolclass': StaticPool} if url in ('sqlite://', 'sqlite:///:memory:') else {}
    engine = create_engine(url, connect_args=args, **options)
    inspector = inspect(engine)
    if inspector.has_table('telemetry') and 'payload' not in {c['name'] for c in inspector.get_columns('telemetry')}:
        engine.dispose()
        raise RuntimeError('This is the older project database. Keep it unchanged and use scripts/import_legacy.py to archive it into a NEW runtime database. See docs/MERGE_GUIDE.md.')
    engine.dispose()  # Ensure the first schema connection receives the PRAGMAs below.
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def pragmas(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)

def serialize(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name != 'token_hash'}
