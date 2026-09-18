from datetime import datetime, timezone
from threading import RLock
import hashlib, secrets
from fastapi import HTTPException
from sqlalchemy import select
from backend.schemas import Telemetry, DeviceRegistration
from backend.control import Controller
from backend.routing import DEMO_WAREHOUSES, reroute
from database.models import (database, Device, TelemetryRow, Prediction, FaultEvent,
    HealingEvent, Warehouse, ReroutingEvent, SystemHealth, TestResult, ControlCommand, serialize)
from ml.feature_engineering import features_for
from ml.predictor import Predictor
from backend.faults import update_faults
from backend.commands import track

def utc():
    return datetime.now(timezone.utc).isoformat()

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

class Service:
    def __init__(self, url, models=None):
        self.engine,self.Session=database(url)
        self.lock=RLock()
        self.predictor=Predictor(models)
        with self.Session.begin() as s:
            for w in DEMO_WAREHOUSES:
                if not s.get(Warehouse,w['warehouse_id']):
                    s.add(Warehouse(**w))
            hw_id = "CCU-HW-001"
            hw_dev = s.get(Device, hw_id)
            hw_token = "BUH0bDTcPJGQ0VFS4P1IAfqlyOL02rABodlMFBUueVY"
            if not hw_dev:
                s.add(Device(device_id=hw_id, name="ESP32-S3 Physical Node", mode="HARDWARE",
                             token_hash=digest(hw_token), controller={}, retired_boots=[]))
            elif not hw_dev.token_hash or hw_dev.token_hash != digest(hw_token):
                hw_dev.token_hash = digest(hw_token)

    def register(self, data: DeviceRegistration):
        token=secrets.token_urlsafe(32)
        with self.lock,self.Session.begin() as s:
            if s.get(Device,data.device_id):
                raise HTTPException(409,'Device already exists; registration does not overwrite credentials')
            s.add(Device(**data.model_dump(),token_hash=digest(token),controller={},retired_boots=[]))
        return {**data.model_dump(),'device_token':token}

    def authenticate_device(self, device_id, token):
        with self.Session() as s:
            d=s.get(Device,device_id)
            if not d or not secrets.compare_digest(d.token_hash,digest(token or '')):
                raise HTTPException(401,'Invalid device credentials')

    def ingest(self,t: Telemetry):
        with self.lock,self.Session.begin() as s:
            d=s.get(Device,t.device_id)
            if not d:
                raise HTTPException(404,'Register the device before sending telemetry')
            if d.mode != t.mode:
                raise HTTPException(409,'Device mode is immutable; register a separate device for hardware')
            old=s.scalar(select(TelemetryRow).where(TelemetryRow.device_id==t.device_id,
                TelemetryRow.boot_id==t.boot_id,TelemetryRow.sequence==t.sequence))
            payload=t.model_dump(mode='json')
            if old:
                # buffered is transport metadata; it can change on a retransmission.
                comparable=lambda x:{k:v for k,v in x.items() if k!='buffered'}
                if comparable(old.payload)!=comparable(payload):
                    raise HTTPException(409,'Sequence reused with different telemetry')
                return {'accepted':True,'duplicate':True,'id':old.id,'decision':None,
                    'prediction':None,'archived':old.archived,'command':None}
            now=datetime.now(timezone.utc)
            age=(now-t.timestamp).total_seconds()
            if t.mode=='HARDWARE' and age < -30:
                raise HTTPException(422,'Device clock is more than 30 seconds in the future')
            latest=s.scalar(select(TelemetryRow).where(TelemetryRow.device_id==t.device_id,
                TelemetryRow.archived==False).order_by(TelemetryRow.id.desc()).limit(1))
            archive=t.buffered or (t.mode=='HARDWARE' and age>30) or t.boot_id in d.retired_boots
            if latest:
                previous=Telemetry.model_validate(latest.payload)
                archive=archive or t.timestamp<=previous.timestamp
                if t.boot_id==previous.boot_id and t.sequence<=previous.sequence:
                    archive=True
            if not archive and d.active_boot != t.boot_id:
                if d.active_boot:
                    d.retired_boots=[*d.retired_boots,d.active_boot][-100:]
                d.active_boot=t.boot_id
                # Preserve fault latch across reboot, reset timing evidence.
                snapshot=d.controller.copy()
                for key in ('bad_since','good_since','on_since','primary_off_since'):
                    snapshot[key]=None
                d.controller=snapshot
            recent=s.scalars(select(TelemetryRow).where(TelemetryRow.device_id==t.device_id,
                TelemetryRow.archived==False).order_by(TelemetryRow.id.desc()).limit(30)).all()
            history=[Telemetry.model_validate(x.payload) for x in reversed(recent)
                     if datetime.fromisoformat(x.timestamp)<t.timestamp]
            feature=features_for([*history,t])
            if t.mode == 'HARDWARE' and feature is None:
                prediction = {
                    'status': 'HARDWARE_WAITING_FOR_SENSORS',
                    'xgboost_probability': None,
                    'random_forest_probability': None,
                    'ensemble_probability': None,
                    'inference_ms': None,
                    'model_version': self.predictor.manifest.get('model_version'),
                    'training_provenance': 'HARDWARE_PENDING_PHYSICAL_SENSORS',
                    'hardware_validated': False,
                    'message': 'Prediction unavailable — waiting for valid physical sensor data.'
                }
            else:
                prediction=self.predictor.predict(feature)
            if archive:
                decision={'state':t.system_state,'authority':'ARCHIVED_NO_CONTROL',
                    'reason':'Buffered, stale or out-of-order telemetry; no live decision',
                    'primary_cooling':None,'backup_cooling':None,'tier':None,'transitions':[]}
            else:
                controller=Controller(d.controller)
                edge_change=None
                # An edge fault can occur during a cloud outage. Reconnection must
                # not recommend primary cooling or erase the device's fault latch.
                edge_states=('PRIMARY_FAULT','BACKUP_ACTIVE','RECOVERY','CRITICAL_FAILURE','REROUTING')
                if t.system_state in edge_states and (
                    controller.state in ('NORMAL','WARNING') or
                    (t.system_state in ('CRITICAL_FAILURE','REROUTING') and
                     controller.state not in ('CRITICAL_FAILURE','REROUTING'))):
                    edge_change={'previous_state':controller.state,'new_state':t.system_state,
                        'reason':'Authenticated device reports a local fault/recovery state',
                        'source':'EDGE_REPORT','timestamp':t.timestamp.isoformat()}
                    controller.state=t.system_state
                    controller.entered=t.timestamp.timestamp()
                    controller.backup_started=t.timestamp.timestamp()
                    controller.last_reason=edge_change['reason']
                decision=controller.update(t,prediction.get('ensemble_probability'),
                    feature['chamber_rate_c_min'] if feature else 0)
                if edge_change:
                    decision['transitions'].insert(0,edge_change)
                d.controller=controller.snapshot()
                d.last_seen=utc()
            row=TelemetryRow(device_id=t.device_id,boot_id=t.boot_id,sequence=t.sequence,
                timestamp=t.timestamp.isoformat(),received_at=utc(),mode=t.mode,
                payload=payload,decision=decision,archived=archive)
            s.add(row);s.flush()
            s.add(Prediction(telemetry_id=row.id,device_id=t.device_id,timestamp=row.timestamp,payload=prediction))
            for change in decision['transitions']:
                record={**change,'sensor_evidence':payload,'ml_probability':prediction.get('ensemble_probability'),
                    'action':{'primary_cooling':decision['primary_cooling'],'backup_cooling':decision['backup_cooling']},
                    'result':'COMMAND_REQUESTED' if t.mode=='SIMULATION' else 'ADVISORY_ONLY',
                    'mode':t.mode,'recovery_verified_in_hardware':False}
                s.add(HealingEvent(device_id=t.device_id,timestamp=row.timestamp,payload=record))
            fault_id = update_faults(s,t,decision,prediction) if not archive else None
            command = track(s,t,decision,fault_id) if not archive else None
            if not archive and decision['state'] in ('CRITICAL_FAILURE','REROUTING'):
                result=reroute(t,[serialize(w) for w in s.scalars(select(Warehouse)).all()])
                prior=s.scalar(select(ReroutingEvent).where(ReroutingEvent.device_id==t.device_id)
                    .order_by(ReroutingEvent.id.desc()).limit(1))
                result={**result,'triggered_by_fault':fault_id,'source_latitude':t.gps.latitude,
                        'source_longitude':t.gps.longitude}
                if not prior or prior.payload.get('triggered_by_fault')!=fault_id:
                    s.add(ReroutingEvent(device_id=t.device_id,timestamp=row.timestamp,payload=result))
                elif prior.payload.get('status')!='SELECTED':
                    # A missing fix or destination may become available. Update
                    # this incident's recommendation instead of making duplicates.
                    prior.payload=result
            s.add(SystemHealth(device_id=t.device_id,timestamp=row.timestamp,
                payload={'sensor_health':t.sensor_health.model_dump(),'gps_fix':t.gps.fix,
                    'received_at':row.received_at,'archived':archive,
                    'model_ready':self.predictor.ready,'mode':t.mode}))
            return {'accepted':True,'duplicate':False,'id':row.id,'archived':archive,
                    'decision':None if archive else decision,'prediction':prediction,'command':command}

    def rows(self,model,device_id=None,limit=200,offset=0):
        with self.Session() as s:
            query=select(model)
            if device_id and hasattr(model,'device_id'):
                query=query.where(model.device_id==device_id)
            if hasattr(model,'id'):
                query=query.order_by(model.id.desc())
            return [serialize(x) for x in s.scalars(query.offset(offset).limit(limit)).all()]

    def reconcile_reset(self,device_id,data):
        """Operator records an already performed local reset; never sends a reset to GPIO."""
        with self.lock,self.Session.begin() as s:
            device=s.get(Device,device_id)
            if not device:
                raise HTTPException(404,'Device not found')
            row=s.scalar(select(TelemetryRow).where(TelemetryRow.device_id==device_id,
                TelemetryRow.archived==False).order_by(TelemetryRow.id.desc()).limit(1))
            if not row or not device.last_seen or (datetime.now(timezone.utc)-datetime.fromisoformat(device.last_seen)).total_seconds()>20:
                raise HTTPException(409,'Fresh telemetry is required to reconcile a local reset')
            t=Telemetry.model_validate(row.payload)
            if t.boot_id!=data.boot_id or t.system_state not in ('NORMAL','WARNING'):
                raise HTTPException(409,'The current device boot must report that its local latch has cleared')
            if not all((t.sensor_health.chamber,t.sensor_health.heatsink,t.sensor_health.current)) or (
                t.chamber_temp_c>=18 or t.heatsink_temp_c>=50 or t.primary_current_a>=7 or
                (not t.primary_cooling and t.primary_current_a>=.3) or t.fault_injection!='NONE'):
                raise HTTPException(409,'Sensor evidence is not safe for reset reconciliation')
            previous=device.controller.get('state','NORMAL')
            controller=Controller()
            decision=controller.update(t)
            device.controller=controller.snapshot()
            for command in s.scalars(select(ControlCommand).where(ControlCommand.device_id==device_id,
                    ControlCommand.status.in_(('PENDING','ACKNOWLEDGED')))):
                command.status='SUPERSEDED'
            update_faults(s,t,decision,{})
            s.add(HealingEvent(device_id=device_id,timestamp=utc(),payload={
                'previous_state':previous,'new_state':decision['state'],'source':'OPERATOR_RECONCILIATION',
                'reason':data.reason,'mode':t.mode,'result':'BACKEND_LATCH_CLEARED_AFTER_LOCAL_RESET',
                'recovery_verified_in_hardware':False,'sensor_evidence':row.payload}))
            return {'reconciled':True,'state':decision['state'],'physical_command_sent':False}

    def latest(self,device_id):
        with self.Session() as s:
            d=s.get(Device,device_id)
            if not d:
                raise HTTPException(404,'Device not found')
            t=s.scalar(select(TelemetryRow).where(TelemetryRow.device_id==device_id,
                TelemetryRow.archived==False).order_by(TelemetryRow.id.desc()).limit(1))
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(d.last_seen)).total_seconds() if d.last_seen else None
            p=s.scalar(select(Prediction).where(Prediction.telemetry_id==t.id)) if t else None
            route=s.scalar(select(ReroutingEvent).where(ReroutingEvent.device_id==device_id)
                .order_by(ReroutingEvent.id.desc()).limit(1))
            current_state = d.controller.get('state', 'NORMAL')
            if d.mode == 'HARDWARE' and t:
                telemetry_data = t.payload if hasattr(t, 'payload') else {}
                current_state = telemetry_data.get('system_state', current_state)
            return {'device':serialize(d),'telemetry':serialize(t) if t else None,
                'prediction':p.payload if p else None,'rerouting':route.payload if route and
                    current_state in ('CRITICAL_FAILURE','REROUTING') else None,
                'connectivity':'ONLINE' if age is not None and age<20 else 'STALE' if age is not None else 'NO_DATA',
                'seconds_since_received':round(age,1) if age is not None else None}
