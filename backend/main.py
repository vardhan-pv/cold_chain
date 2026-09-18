import asyncio, csv, io, json, logging, os, secrets, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response, JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.schemas import (Telemetry,DeviceRegistration,WarehouseInput,ScenarioRequest,ValidationRecord)
from backend.service import Service, utc
from backend.validation import validation_report
from database.models import (Device,TelemetryRow,Prediction,FaultEvent,HealingEvent,Warehouse,
    ReroutingEvent,SystemHealth,TestResult,ControlCommand,ArchiveImport,serialize)
from simulator.engine import Simulator
from backend import commands
from backend.archive import import_legacy, archive_rows
from backend.api.compatibility import router_for
from backend.schemas import CommandAcknowledgement,ResetReconciliation

ROOT=Path(__file__).resolve().parents[1]
log=logging.getLogger('cold_chain')

def create_app(database_url=None,admin_token=None,models=None,run_simulation=False,import_archives=True):
    token=admin_token or os.getenv('CC_ADMIN_TOKEN','')
    if len(token)<16:
        (ROOT/'runtime').mkdir(exist_ok=True)
        secrets_path=ROOT/'runtime/operator.json'
        if secrets_path.exists():
            try: token=json.loads(secrets_path.read_text()).get('operator_token','')
            except Exception: pass
        if len(token)<16:
            token=secrets.token_urlsafe(32)
            try: secrets_path.write_text(json.dumps({'operator_token':token}))
            except Exception: pass
    (ROOT/'runtime').mkdir(exist_ok=True)
    service=Service(database_url or os.getenv('CC_DATABASE_URL',f'sqlite:///{ROOT / "runtime/cold_chain.db"}'),models or os.getenv('CC_MODEL_DIR'))
    if import_archives:
        for snapshot in sorted((ROOT/'archive/databases').glob('*.db')):
            import_legacy(service,snapshot)
    simulation={'engine':None,'paused':False,'error':None}

    def tick():
        with service.lock:
            sim=simulation['engine']
            if not sim or simulation['paused']:
                return
            t,_,_=sim.step()
            if not sim.network_available():
                sim.enqueue(t)
                return
            while sim.queue:
                service.ingest(sim.queue[0]);sim.queue.pop(0)
            result=service.ingest(t)
            sim.last_prediction=result['prediction']
            command=commands.pending(service,sim.device_id)['command']
            if command:
                commands.acknowledge(service,command['id'],CommandAcknowledgement(**sim.acknowledgement(command)))

    async def worker():
        while True:
            try:
                await asyncio.to_thread(tick)
                simulation['error']=None
            except Exception:
                log.exception('Simulation step failed')
                simulation['error']='Simulation step failed; inspect backend log'
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(worker()) if run_simulation else None
        yield
        if task:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        service.engine.dispose()

    app=FastAPI(title='Cold Chain Integrated Prototype API',version='2.0.0',lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.service=service
    app.state.simulation=simulation
    app.state.tick=tick

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Never echo invalid NaN/Infinity or credentials in an error response.
        return JSONResponse(status_code=422,content={'detail':[
            {'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]})

    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['X-Frame-Options']='DENY'
        if request.url.path=='/':
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        return response

    def admin(authorization: str=Header(default='')):
        if not secrets.compare_digest(authorization,'Bearer '+token):
            raise HTTPException(401,'Provide a valid operator token')
    auth=[Depends(admin)]
    app.include_router(router_for(service,admin))

    @app.get('/health')
    def health():
        from sqlalchemy import text
        with service.engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'status':'ok','service':'cold-chain','version':'2.0.0','database':'connected'}

    @app.post('/api/devices',dependencies=auth,status_code=201)
    def register(data:DeviceRegistration):
        return service.register(data)

    @app.get('/api/devices',dependencies=auth)
    def devices():
        return service.rows(Device)

    @app.post('/api/devices/{device_id}/reconcile-reset',dependencies=auth)
    def reconcile_reset(device_id:str,data:ResetReconciliation):
        return service.reconcile_reset(device_id,data)

    @app.post('/api/telemetry')
    @app.post('/api/v1/telemetry',include_in_schema=False)
    def telemetry(data:Telemetry,x_device_token:str=Header(default='')):
        service.authenticate_device(data.device_id,x_device_token)
        result=service.ingest(data)
        return {**result,'device_id':data.device_id,'sequence':data.sequence,
                'stored':not result['duplicate'],'session_id':data.boot_id}

    @app.get('/api/latest',dependencies=auth)
    def latest(device_id:str):
        return service.latest(device_id)

    @app.get('/api/v1/status/{device_id}',dependencies=auth,include_in_schema=False)
    def status_alias(device_id:str):
        return service.latest(device_id)

    def listing(model):
        def handler(device_id:str,limit:int=Query(default=200,ge=1,le=2000),offset:int=Query(default=0,ge=0)):
            service.latest(device_id) # explicit 404 for an unknown device
            return service.rows(model,device_id,limit,offset)
        return handler
    for path,model in [('history',TelemetryRow),('predictions',Prediction),('faults',FaultEvent),
        ('self-healing',HealingEvent),('rerouting',ReroutingEvent),('system-health',SystemHealth),
        ('commands',ControlCommand)]:
        app.add_api_route('/api/'+path,listing(model),methods=['GET'],dependencies=auth,
            name=path.replace('-','_'))
    for path,model in [('history',TelemetryRow),('events',HealingEvent),('predictions',Prediction)]:
        app.add_api_route('/api/v1/'+path+'/{device_id}',listing(model),methods=['GET'],dependencies=auth,
            include_in_schema=False)

    @app.get('/api/history/export',dependencies=auth)
    def export_history(device_id:str):
        from sqlalchemy import select
        service.latest(device_id)
        def stream():
            with service.Session() as session:
                yield '['
                first=True
                rows=session.scalars(select(TelemetryRow).where(TelemetryRow.device_id==device_id)
                    .order_by(TelemetryRow.id).execution_options(yield_per=200))
                for row in rows:
                    yield ('' if first else ',')+json.dumps(serialize(row),allow_nan=False)
                    first=False
                yield ']'
        return StreamingResponse(stream(),media_type='application/json',headers={
            'Content-Disposition':f'attachment; filename="{device_id}-telemetry.json"'})

    @app.get('/api/archive',dependencies=auth)
    def archives():
        return service.rows(ArchiveImport)

    @app.get('/api/archive/{source}/{table}',dependencies=auth)
    def archived_records(source:str,table:str,device_id:str|None=None,
                         limit:int=Query(100,ge=1,le=2000),offset:int=Query(0,ge=0)):
        return archive_rows(service,source,table,device_id,limit,offset)

    @app.get('/api/warehouses',dependencies=auth)
    def warehouses():
        return service.rows(Warehouse)

    @app.put('/api/warehouses',dependencies=auth)
    def warehouse(data:WarehouseInput):
        with service.lock,service.Session.begin() as s:
            s.merge(Warehouse(**data.model_dump()))
        return data

    @app.get('/api/system-status',dependencies=auth)
    def system_status():
        sim=simulation['engine']
        return {'software_stage':'SIMULATION_VALIDATION','hardware_status':'PENDING_HARDWARE',
            'ml_ready':service.predictor.ready,'ml_error':service.predictor.error,
            'model':service.predictor.manifest,'firmware_target_build':'NOT_VERIFIED',
            'simulation':{'running':bool(sim) and not simulation['paused'],
                'scenario':sim.scenario if sim else None,'device_id':sim.device_id if sim else None,
                'buffered_samples':len(sim.queue) if sim else 0,'dropped_samples':sim.dropped if sim else 0,
                'speed':'5 simulated seconds per 1 wall-clock second','error':simulation['error']},
            'architecture':{'controller':'ESP32-S3','primary':'TEC1-12706',
                'backup':'TEC1-12701 / TEC1-12703','current_sensors':1,'fan':'Unswitched 12 V',
                'oled_required':False,'physical_fault_buttons_required':False}}

    @app.post('/api/simulation/start',dependencies=auth)
    def start(data:ScenarioRequest):
        if not run_simulation:
            raise HTTPException(403,'Built-in simulator disabled')
        with service.lock:
            device='CCU-SIM-'+uuid.uuid4().hex[:8]
            service.register(DeviceRegistration(device_id=device,name='Laboratory simulation',mode='SIMULATION'))
            simulation.update(engine=Simulator(device_id=device,scenario=data.scenario),paused=False,error=None)
            tick()
        return {'device_id':device,'mode':'SIMULATION'}

    @app.post('/api/simulation/scenario',dependencies=auth)
    def scenario(data:ScenarioRequest):
        if not run_simulation or not simulation['engine']:
            raise HTTPException(409,'Start a simulation first')
        with service.lock:
            simulation['engine'].scenario=data.scenario
        return {'scenario':data.scenario,'mode':'SIMULATION',
                'note':'Changing scenario does not clear latched faults; start a new run to reset'}

    @app.post('/api/simulation/pause',dependencies=auth)
    def pause():
        simulation['paused']=not simulation['paused']
        return {'paused':simulation['paused']}

    @app.get('/api/validation',dependencies=auth)
    def validation(device_id:str):
        service.latest(device_id)
        return validation_report(device_id,service.rows(TestResult,device_id,2000))

    @app.post('/api/validation',dependencies=auth,status_code=201)
    def record(data:ValidationRecord):
        device=service.latest(data.device_id)['device']
        if device['mode']!=data.mode:
            raise HTTPException(409,'Evidence mode must match registered device')
        if data.metric=='backup_current_a' and 'external meter' not in data.evidence.lower():
            raise HTTPException(422,'Backup current requires documented external meter evidence')
        with service.Session.begin() as s:
            s.add(TestResult(device_id=data.device_id,timestamp=utc(),payload=data.model_dump(mode='json')))
        return {'recorded':True,'verification':'OPERATOR_SUPPLIED_EVIDENCE'}

    @app.get('/api/validation/export',dependencies=auth)
    def export(device_id:str,format:str=Query(default='json',pattern='^(json|csv)$')):
        report=validation(device_id)
        if format=='json': return report
        output=io.StringIO();writer=csv.DictWriter(output,fieldnames=report['metrics'][0].keys())
        writer.writeheader();writer.writerows(report['metrics'])
        return Response(output.getvalue(),media_type='text/csv',
            headers={'Content-Disposition':'attachment; filename="validation.csv"'})

    dist=ROOT/'dashboard/dist'
    assets=dist if dist.exists() else ROOT/'dashboard/src'
    if assets.exists():
        app.mount('/assets',StaticFiles(directory=assets),name='assets')
        @app.get('/',include_in_schema=False)
        def index():
            return FileResponse(assets/'index.html')
    return app
