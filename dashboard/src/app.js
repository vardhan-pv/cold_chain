const $=id=>document.getElementById(id);
const esc=v=>String(v??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pages=[['overview','Overview','◈'],['live','Live monitoring','∿'],['predictive','Predictive maintenance','◇'],['healing','Self-healing','↻'],['equipment','Cold-chain equipment','▣'],['routing','GPS & rerouting','⌖'],['alerts','Alerts','△'],['history','Event history','≡'],['analytics','ML analytics','▥'],['health','System health','◎'],['validation','Testing & validation','✓'],['archive','Original project records','▤']];
const titles={overview:['System overview','Monitor chamber metrics, analyze ML risk, and inspect control responses.'],live:['Live monitoring','Acquired sensor values and their recent history.'],predictive:['Predictive maintenance','Actual model inference, with training provenance shown.'],healing:['Self-healing timeline','Every transition keeps its reason, evidence, and requested action.'],equipment:['Cold-chain equipment','Final hardware components list controls this architecture.'],routing:['GPS & rerouting','Compatible facilities ranked by straight-line distance.'],alerts:['Fault alerts','Sensor-driven warnings, confirmed faults, and critical events.'],history:['Event history','Persistent telemetry and the recorded sequence of decisions.'],analytics:['Model evaluation','Held-out simulation episodes. Physical validation is pending.'],health:['System health','Connection freshness, sensor health, and software availability.'],validation:['Testing & validation','Keep simulation evidence separate from physical measurements.'],archive:['Original project records','Preserved readings and events from the uploaded project. No historical commands are replayed.']};

let token=sessionStorage.getItem('cc_token')||'';
let apiUrl=localStorage.getItem('cc_api_url')||'';
let appMode=localStorage.getItem('cc_app_mode')||'SIMULATION';
let device='',cache={},busy=false,page='overview';

const hashParams=new URLSearchParams(location.hash.slice(1));
if(hashParams.has('token')){token=hashParams.get('token');sessionStorage.setItem('cc_token',token);history.replaceState(null,'',location.pathname+'#overview');}
if(hashParams.has('api')){apiUrl=hashParams.get('api');localStorage.setItem('cc_api_url',apiUrl);}

function route(){
  page=pages.some(x=>x[0]===location.hash.slice(1))?location.hash.slice(1):'overview';
  render();
  const activeLink=document.querySelector(`[data-page="${page}"]`);
  if(activeLink&&window.innerWidth<=820){
    activeLink.scrollIntoView({behavior:'smooth',inline:'center',block:'nearest'});
  }
}
function badge(text,kind=''){return `<span class="badge ${kind}">${esc(text)}</span>`;}
function empty(title,detail='Start a simulation or connect a registered device.'){return `<div class="card empty"><strong>${esc(title)}</strong>${esc(detail)}</div>`;}
function fmt(v,d=1){return Number.isFinite(v)?v.toFixed(d):'—';}
function clock(v){return v?new Date(v).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';}

async function api(path,body,method){
  const base=apiUrl?apiUrl.replace(/\/$/,''):'';
  const r=await fetch(base+'/api/'+path,{
    method:method||(body?'POST':'GET'),
    headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:body?JSON.stringify(body):undefined
  });
  if(!r.ok){
    let text='Request failed';
    try{text=(await r.json()).detail||text;}catch{}
    throw Error(typeof text==='string'?text:JSON.stringify(text));
  }
  return r.json();
}

function login(){
  $('login').hidden=!!token;
  $('shell').hidden=!token;
  if($('api-url'))$('api-url').value=apiUrl||location.origin;
  if(token)refresh();
}

$('login-form').addEventListener('submit',async e=>{
  e.preventDefault();
  token=$('token').value.trim();
  apiUrl=$('api-url').value.trim();
  if(apiUrl===location.origin)apiUrl='';
  try{
    await api('devices');
    sessionStorage.setItem('cc_token',token);
    localStorage.setItem('cc_api_url',apiUrl);
    $('login-error').textContent='';
    login();
  }catch(err){
    token='';
    $('login-error').textContent=err.message;
  }
});

const doLogout=()=>{token='';sessionStorage.removeItem('cc_token');cache={};login();};
$('logout').onclick=doLogout;
if($('logout-mobile'))$('logout-mobile').onclick=doLogout;
$('nav').innerHTML=pages.map(([id,label,icon])=>`<a href="#${id}" data-page="${id}"><span aria-hidden="true">${icon}</span>${label}</a>`).join('');
window.addEventListener('hashchange',route);
$('refresh').onclick=refresh;

// Mode Switcher handlers
function setAppMode(mode){
  appMode=mode;
  localStorage.setItem('cc_app_mode',mode);
  $('mode-sim-tab').classList.toggle('active',mode==='SIMULATION');
  $('mode-live-tab').classList.toggle('active',mode==='HARDWARE');
  $('sim-controls').hidden=mode!=='SIMULATION';
  $('live-controls').hidden=mode==='SIMULATION';
  $('mode-eyebrow').textContent=mode==='SIMULATION'?'SIMULATION ENGINE ACTIVE':'LIVE ESP32 HARDWARE INGESTION';
  device='';
  refresh();
}

$('mode-sim-tab').onclick=()=>setAppMode('SIMULATION');
$('mode-live-tab').onclick=()=>setAppMode('HARDWARE');

$('device').onchange=()=>{device=$('device').value;refresh();};

async function action(fn){
  document.querySelectorAll('.simulation-bar button').forEach(b=>b.disabled=true);
  try{await fn();await refresh();}catch(e){$('notice').textContent=e.message;}finally{document.querySelectorAll('.simulation-bar button').forEach(b=>b.disabled=false);}
}

$('start').onclick=()=>action(async()=>{const x=await api('simulation/start',{scenario:$('scenario').value});device=x.device_id;});
$('apply').onclick=()=>action(()=>api('simulation/scenario',{scenario:$('scenario').value}));
$('pause').onclick=()=>action(()=>api('simulation/pause',{}));

// ESP32 Code & Registration Modals
$('btn-show-code').onclick=()=>{
  const targetHost=apiUrl||location.origin;
  const targetDevice=device||'ESP32-S3-01';
  $('cfg-endpoint').textContent=targetHost.replace(/\/$/,'')+'/api/v1/telemetry';
  $('cfg-device-id').textContent=targetDevice;
  $('cfg-token').textContent=cache.lastRegisteredToken||'YourDeviceToken';
  $('cpp-snippet').textContent=`// ESP32-S3 Telemetry POST
#include <HTTPClient.h>

const char* API_URL = "${targetHost.replace(/\/$/,'')}/api/v1/telemetry";
const char* DEVICE_TOKEN = "${cache.lastRegisteredToken||'YOUR_DEVICE_TOKEN'}";

void sendTelemetry() {
  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  // POST payload ...
  int code = http.POST(payload);
  http.end();
}`;
  $('modal-hw').showModal();
};

$('btn-copy-code').onclick=()=>{
  navigator.clipboard.writeText($('cpp-snippet').textContent);
  $('btn-copy-code').textContent='Copied!';
  setTimeout(()=>$('btn-copy-code').textContent='Copy Config',2000);
};

const openRegisterModal=()=>{
  $('reg-device-id').value='ESP32-'+Math.floor(1000+Math.random()*9000);
  $('reg-device-name').value='Laboratory ESP32 Node';
  $('reg-result').hidden=true;
  $('modal-register').showModal();
};

if($('btn-register-device'))$('btn-register-device').onclick=openRegisterModal;
if($('btn-register-live'))$('btn-register-live').onclick=openRegisterModal;
if($('btn-cancel-reg'))$('btn-cancel-reg').onclick=()=>$('modal-register').close();

$('form-register-device').onsubmit=async e=>{
  e.preventDefault();
  const devId=$('reg-device-id').value.trim();
  const devName=$('reg-device-name').value.trim();
  try{
    const res=await api('devices',{device_id:devId,name:devName,mode:'HARDWARE'});
    cache.lastRegisteredToken=res.device_token;
    $('reg-result').hidden=false;
    $('reg-result').className='notice success';
    $('reg-result').innerHTML=`Device <strong>${esc(res.device_id)}</strong> registered!<br>Device Token: <code>${esc(res.device_token)}</code>`;
    setTimeout(()=>{
      $('modal-register').close();
      setAppMode('HARDWARE');
      device=res.device_id;
      $('btn-show-code').click();
    },1800);
  }catch(err){
    $('reg-result').hidden=false;
    $('reg-result').className='notice danger';
    $('reg-result').textContent=err.message;
  }
};

async function refresh(){
  if(!token||busy)return;
  busy=true;
  try{
    const [devices,system]=await Promise.all([api('devices'),api('system-status')]);
    cache.system=system;cache.devices=devices;
    cache.archives=await api('archive');
    if(!cache.archiveData&&cache.archives.length){
      const source=cache.archives.find(x=>x.source_name==='cold_chain.db')||cache.archives[0];
      await loadArchive(source.source_sha256,'telemetry',0,false);
    }
    
    // Filter devices based on active mode
    const modeDevices=devices.filter(d=>d.mode===appMode);
    if(!modeDevices.some(x=>x.device_id===device)){
      if(appMode==='SIMULATION'){
        device=system.simulation.device_id||modeDevices.at(-1)?.device_id||'';
      }else{
        device=modeDevices.at(-1)?.device_id||'';
      }
    }

    $('server-url-badge').textContent='Server: '+(apiUrl?new URL(apiUrl).hostname:'Localhost');
    $('device').innerHTML=modeDevices.length?modeDevices.map(d=>`<option value="${esc(d.device_id)}">${esc(d.device_id)} · ${esc(d.name)}</option>`).join(''):`<option value="">No ${appMode==='SIMULATION'?'simulations':'hardware devices'} registered</option>`;
    if(device)$('device').value=device;

    if(device){
      const q='?device_id='+encodeURIComponent(device);
      const names=['latest','history','self-healing','faults','warehouses','validation','commands'];
      const data=await Promise.all(names.map(n=>api(n+(n==='warehouses'?'':q))));
      names.forEach((n,i)=>cache[n]=data[i]);
    }else{
      for(const n of ['latest','history','self-healing','faults','warehouses','validation','commands'])delete cache[n];
    }

    if(appMode==='SIMULATION'){
      $('sim-label').textContent=system.simulation?`${system.simulation.running?'Running':'Paused / idle'} · ${system.simulation.scenario||'no scenario'} · 5× simulated clock · ${system.simulation.buffered_samples} queued`:'Hardware pending';
    }else{
      const latestSec=cache.latest?.seconds_since_received;
      const isFresh=Number.isFinite(latestSec)&&latestSec<15;
      $('live-label').textContent=device?`Active Device: ${device} · ${isFresh?`Streaming live (${fmt(latestSec)}s ago)`:`Offline / Stale (${Number.isFinite(latestSec)?fmt(latestSec)+'s ago':'No telemetry received'})`}`:'Register or select an ESP32 hardware device below.';
    }

    $('notice').textContent=system.simulation?.error||'';
    render();
  }catch(e){
    $('notice').textContent='Connection unavailable: '+e.message;
    $('connection').textContent='DISCONNECTED';
    $('connection').className='badge danger';
  }finally{
    busy=false;
  }
}

function chart(field,label,unit,range=false){
  const rows=(cache.history||[]).slice().reverse().filter(x=>Number.isFinite(x.payload[field])).slice(-80);
  if(rows.length<2)return `<div class="empty">Waiting for two valid ${esc(label.toLowerCase())} readings.</div>`;
  const values=rows.map(x=>x.payload[field]);
  const min=Math.min(...values,range?5:Infinity)-.5,max=Math.max(...values,range?8:-Infinity)+.5;
  const X=i=>45+i*570/(rows.length-1),Y=v=>210-(v-min)/(max-min)*175;
  const grid=Array.from({length:5},(_,i)=>{const v=min+(max-min)*i/4;return `<line x1="45" x2="615" y1="${Y(v)}" y2="${Y(v)}"/><text x="2" y="${Y(v)+4}">${v.toFixed(1)}</text>`;}).join('');
  return `<svg class="chart" viewBox="0 0 650 252" role="img" aria-label="${esc(label)} history in ${esc(unit)}">${range?`<rect class="range" x="45" width="570" y="${Y(8)}" height="${Y(5)-Y(8)}"/>`:''}${grid}<polyline points="${values.map((v,i)=>`${X(i)},${Y(v)}`).join(' ')}"/><text x="45" y="241">${esc(clock(rows[0].timestamp))}</text><text x="615" y="241" text-anchor="end">${esc(clock(rows.at(-1).timestamp))}</text></svg>`;
}

function chartCard(field,label,unit,range=false){
  return `<section class="card"><div class="card-head"><div><h2>${esc(label)}</h2><p class="card-sub">Latest 80 valid samples · ${esc(unit)}</p></div>${badge('RECORDED','neutral')}</div>${chart(field,label,unit,range)}<div class="legend"><span>${esc(label)}</span>${range?'<span>Demonstration band 5–8 °C</span>':''}</div></section>`;
}

function kpis(){
  const t=cache.latest?.telemetry?.payload||{};
  const isHardware = appMode === 'HARDWARE';
  const list = [
    ['Chamber temperature',t.chamber_temp_c,'°C','DS18B20 / chamber'],
    ['Heatsink temperature',t.heatsink_temp_c,'°C','DS18B20 / hot side'],
    ['Ambient temperature',t.sht31_temp_c,'°C','SHT31 / ambient secondary'],
    ['Relative humidity',t.humidity_pct,'%','SHT31 / humidity'],
    ['Primary current',t.primary_current_a,'A','ACS712 / primary branch'],
    ['Door state',t.door_open,'','Reed switch / GPIO7'],
    ['GPS location',t.gps,'','NEO-6M / UART1'],
    ['Vibration',t.vibration_detected,'','LM393 / GPIO11']
  ];
  return `<div class="kpis">${list.map(([l,v,u,f])=>{
    let valueDisplay = '—';
    let footerText = '';
    if(l==='Primary current'){
      if(Number.isFinite(v)){
        valueDisplay=`${fmt(v)}<small>${u}</small>`;
        footerText=`<span class="status-dot"></span>${f}`;
      } else if(isHardware){
        valueDisplay=`<span class="pending-badge">Waiting for calibration</span>`;
        footerText=`ACS712 · Pending calibration (not failure)`;
      } else {
        valueDisplay='—';
        footerText=`△ Simulated sensor unavailable`;
      }
    } else if(l==='Door state'){
      if(v==null){
        valueDisplay='—';
        footerText=`△ Door state unavailable`;
      } else {
        valueDisplay=v?`OPEN ${t.door_open_s?`<small>${fmt(t.door_open_s,0)}s</small>`:''}`:'CLOSED';
        footerText=`<span class="status-dot"></span>${f} · ${v?'Open duration':'Secure'}`;
      }
    } else if(l==='GPS location'){
      const g=v||{};
      if(g.fix){
        valueDisplay=`FIX <small>${g.satellites||0} sats</small>`;
        footerText=`<span class="status-dot"></span>${fmt(g.latitude,3)}, ${fmt(g.longitude,3)}`;
      } else {
        valueDisplay=`NO FIX <small>${g.satellites||0} sats</small>`;
        footerText=`Indoor test · No satellite lock (normal)`;
      }
    } else if(l==='Vibration'){
      if(v===true){
        valueDisplay=`<span style="color:#b23b2b">DETECTED</span>`;
        footerText=`△ Shock or vibration detected`;
      } else {
        valueDisplay=`NORMAL`;
        footerText=`<span class="status-dot"></span>No shock detected`;
      }
    } else {
      const hasValue = Number.isFinite(v);
      valueDisplay = hasValue ? `${fmt(v)}<small>${u}</small>` : '—';
      footerText = hasValue ? `<span class="status-dot"></span>${f}` : (isHardware ? `△ Pending hardware sensor (${f.split('/')[0].trim()})` : `△ Simulated sensor unavailable`);
    }
    return `<section class="card"><div class="kpi-label">${l}<span>↗</span></div><div class="kpi-value">${valueDisplay}</div><div class="kpi-foot">${footerText}</div></section>`;
  }).join('')}</div>`;
}

function row(label,val){return `<div class="status-row"><span>${esc(label)}</span><strong>${esc(val)}</strong></div>`;}

function control(){
  const latest=cache.latest,t=latest?.telemetry?.payload||{},d=latest?.telemetry?.decision||{};
  const isHardware = (t.mode || appMode) === 'HARDWARE';
  const edgeState = t.system_state || 'NORMAL';
  const authoritativeState = isHardware ? edgeState : (d.state || edgeState || 'NO_DATA');
  const advisoryNote = isHardware
    ? (d.advisory_status === 'HARDWARE_PENDING_SENSORS'
        ? 'ESP32 edge safety loop authoritative · Physical probes pending'
        : (d.reason || 'ESP32 edge safety loop authoritative'))
    : (d.reason || 'Simulated closed-loop control');

  const primaryCoolingText = t.primary_cooling === undefined ? 'UNAVAILABLE' : (t.primary_cooling ? 'ON' : 'OFF');
  const backupCoolingText = isHardware ? 'NOT COMMISSIONED' : (t.backup_cooling === undefined ? 'UNAVAILABLE' : t.backup_cooling ? 'ON' : 'OFF');
  const doorText = t.door_open == null ? 'UNAVAILABLE' : (t.door_open ? ('OPEN (' + fmt(t.door_open_s, 0) + 's)') : 'CLOSED');
  const gpsText = t?.gps?.fix
    ? ('FIX (' + (t.gps.satellites || 0) + ' sats · ' + fmt(t.gps.latitude, 4) + ', ' + fmt(t.gps.longitude, 4) + ')')
    : ('NO FIX (' + (t?.gps?.satellites || 0) + ' satellites)');

  return `<section class="card">
    <div class="card-head">
      <div>
        <h2>Current System State</h2>
        <p class="card-sub">${isHardware ? 'Live ESP32-S3 edge authority' : 'Autonomous simulated closed loop'}</p>
      </div>
      ${badge(isHardware ? 'HARDWARE' : 'SIMULATION', isHardware ? 'success' : 'neutral')}
    </div>
    <div class="state-panel">
      <p>${isHardware ? 'AUTHORITATIVE CURRENT STATE' : 'ANALYZED SYSTEM STATE'}</p>
      <div class="big-state">${esc(authoritativeState.replaceAll('_',' '))}</div>
      <p>${esc(advisoryNote)}</p>
    </div>
    ${row('Primary cooling', primaryCoolingText)}
    ${row('Backup cooling', backupCoolingText)}
    ${row('Door (Reed switch)', doorText)}
    ${row('GPS status', gpsText)}
    ${row('Edge-reported state', edgeState)}
    ${row('Cloud advisory analysis', (d.state || 'NORMAL').replaceAll('_',' '))}
    ${row('Control authority', isHardware ? 'ESP32 local safety loop (Hardware)' : 'Simulated local loop')}
    <div class="state-steps">${[0,1,2,3].map(i=>`<span class="${(d.tier??-1)>=i?'done':''}"></span>`).join('')}</div>
    <p class="card-sub">${isHardware ? 'Local edge protection governs physical outputs. Cloud operates in advisory supervision.' : 'Requested actions and observed outputs are recorded separately.'}</p>
  </section>`;
}

function risks(){
  const p=cache.latest?.prediction||{};
  const isHardware = appMode === 'HARDWARE';
  const hasInference = Number.isFinite(p.ensemble_probability);

  return `<div class="three-col">${[
    ['XGBoost','xgboost_probability'],
    ['Random Forest','random_forest_probability'],
    ['Weighted ensemble','ensemble_probability']
  ].map(([name,key])=>{
    let valueText = 'Unavailable';
    let barWidth = 0;
    let noteText = '';

    if (hasInference && !isHardware) {
      valueText = fmt(p[key]*100,1)+'%';
      barWidth = (p[key]||0)*100;
      noteText = `${esc(p.training_provenance||'SIMULATED_DATA')} · INFERENCE ACTIVE`;
    } else if (isHardware) {
      if (hasInference) {
        valueText = fmt(p[key]*100,1)+'%';
        barWidth = (p[key]||0)*100;
        noteText = 'HARDWARE DATA · LIVE INFERENCE';
      } else {
        valueText = '<span style="font-size:15px;color:var(--muted);font-weight:500;">Waiting for physical sensor data</span>';
        barWidth = 0;
        noteText = 'HARDWARE DATA · WAITING FOR SENSOR INPUT';
      }
    } else {
      valueText = 'Waiting for telemetry';
      noteText = 'SIMULATION · IDLE';
    }

    return `<section class="card">
      <div class="card-head">
        <h2>${name}</h2>
        ${badge(isHardware ? (hasInference ? 'LIVE ML' : 'PENDING SENSORS') : 'ML SIM', isHardware && !hasInference ? 'neutral' : 'success')}
      </div>
      <div class="risk">${valueText}</div>
      <div class="bar">
        <svg viewBox="0 0 100 5" preserveAspectRatio="none">
          <rect width="${barWidth}" height="5" fill="#4c9070"/>
        </svg>
      </div>
      <p class="model-note">${noteText}</p>
    </section>`;
  }).join('')}</div>`;
}

function timeline(limit=8){
  const events=(cache['self-healing']||[]).slice(0,limit);
  return `<section class="card">
    <div class="card-head">
      <div>
        <h2>Self-healing event history</h2>
        <p class="card-sub">Historical transition log · newest first · non-active historical events</p>
      </div>
      ${badge(events.length+' LOGGED','neutral')}
    </div>
    <div class="timeline">${events.length?events.map(e=>{
      const p = e.payload || {};
      const eventMode = p.mode || (e.device_id?.startsWith('CCU-SIM') ? 'SIMULATION' : 'HARDWARE');
      const isResolved = p.resolved !== false;
      const isFaultInjection = p.source === 'FAULT_INJECTION';
      return `<div class="timeline-item">
        <time>${esc(clock(e.timestamp))}</time>
        <div>
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
            <strong>${esc((p.new_state || 'UNKNOWN').replaceAll('_',' '))}</strong>
            <span class="badge ${eventMode==='HARDWARE'?'success':'neutral'}">${esc(eventMode)}</span>
            <span class="badge ${isResolved?'neutral':'danger'}">${isResolved?'HISTORICAL / RESOLVED':'ACTIVE'}</span>
            ${isFaultInjection?'<span class="badge warn">FAULT INJECTION</span>':''}
          </div>
          <p>${esc(p.reason || 'Transition recorded')}</p>
          <p class="card-sub">Previous: ${esc((p.previous_state||'NONE').replaceAll('_',' '))} · Source: ${esc(p.source || 'SYSTEM')} · Result: ${esc(p.result || 'LOGGED')}</p>
        </div>
      </div>`;
    }).join(''):'<div class="empty">No historical self-healing transitions for this device. Current state is healthy.</div>'}
    </div>
  </section>`;
}

function map(){
  const t=cache.latest?.telemetry?.payload,route=cache.latest?.rerouting,warehouses=cache.warehouses||[];
  if(!t?.gps.fix)return empty('No valid GPS fix','No coordinates or destination are fabricated.');
  const points=[{latitude:t.gps.latitude,longitude:t.gps.longitude,name:'Vehicle',vehicle:true},...warehouses];
  let lats=points.map(p=>p.latitude),lons=points.map(p=>p.longitude);
  let lo=Math.min(...lons)-.009,hi=Math.max(...lons)+.009,bottom=Math.min(...lats)-.009,top=Math.max(...lats)+.009;
  const xy=p=>[40+(p.longitude-lo)/(hi-lo)*540,255-(p.latitude-bottom)/(top-bottom)*220];
  const [vx,vy]=xy(points[0]);
  const selected=route?.selected;
  const [sx,sy]=selected?xy(selected):[0,0];
  return `<section class="card"><div class="card-head"><div><h2>Location & facilities</h2><p class="card-sub">Geographic schematic · not a road navigation map</p></div>${badge(t.gps.source==='SIMULATED'?'SIMULATED LOCATION':'GPS FIX','warn')}</div><svg class="map" viewBox="0 0 630 285" role="img" aria-label="Vehicle and demonstration cold storage locations">${Array.from({length:9},(_,i)=>`<path class="map-grid" d="M ${30+i*70} 0 V 285 M 0 ${i*38} H 630"/>`).join('')}${selected?`<line x1="${vx}" y1="${vy}" x2="${sx}" y2="${sy}"/>`:''}${points.map(p=>{const [x,y]=xy(p);return `<circle cx="${x}" cy="${y}" r="${p.vehicle?8:5}" class="${p.vehicle?'vehicle':'facility'}"/><text x="${x}" y="${y-13}" text-anchor="middle">${esc(p.name)}</text>`;}).join('')}</svg><p class="card-sub">${selected?'Selected: '+esc(selected.name)+' · '+fmt(selected.distance_km,2)+' km straight-line':esc(route?.reason||'Rerouting activates after a critical failure.')}</p></section>`;
}

function table(headers,rows){
  return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function commandTable(){
  return `<section class="card"><h2>Control command lifecycle</h2><p class="card-sub">ACK records the device response. CONFIRMED requires matching later telemetry.</p>${table(['ID','Command','Status','Boot','Evidence sequence','ACK received','Telemetry confirmed'],(cache.commands||[]).map(c=>[c.id,c.command_type,c.status,c.boot_id.slice(0,8),c.based_on_sequence,clock(c.acknowledged_at),clock(c.confirmed_at)]))}</section>`;
}

async function loadArchive(source,tableName,offset=0,redraw=true){
  cache.archiveData=await api(`archive/${encodeURIComponent(source)}/${encodeURIComponent(tableName)}?limit=50&offset=${offset}`);
  if(redraw)render();
}

function archiveView(){
  const sources=cache.archives||[],data=cache.archiveData;
  if(!sources.length||!data)return empty('No original records imported','Use scripts/import_legacy.py to preserve an earlier project database.');
  const keys=Object.keys(data.records[0]||{});
  return `<section class="card"><div class="card-head"><div><h2>Preserved project history</h2><p class="card-sub">${esc(data.notice)}</p></div>${badge('ARCHIVED','neutral')}</div><div class="archive-controls"><label>Snapshot <select id="archive-source">${sources.map(x=>`<option value="${esc(x.source_sha256)}" ${x.source_sha256===data.source.source_sha256?'selected':''}>${esc(x.source_name)}</option>`).join('')}</select></label><label>Records <select id="archive-table">${Object.keys(data.source.table_counts).map(x=>`<option ${x===data.table?'selected':''}>${esc(x)}</option>`).join('')}</select></label><button class="secondary" id="archive-export">Export all JSON</button></div>${row('Source SHA-256',data.source.source_sha256)}${row('Historical rows in this table',data.total)}${row('Control replay','DISABLED')}${table(keys,data.records.map(r=>keys.map(k=>r[k])))}<div class="archive-controls"><button class="secondary" id="archive-prev" ${data.offset===0?'disabled':''}>Previous</button><span>${data.total?data.offset+1:0}–${Math.min(data.offset+data.records.length,data.total)} of ${data.total}</span><button class="secondary" id="archive-next" ${data.offset+data.records.length>=data.total?'disabled':''}>Next</button></div></section>`;
}

function bindArchive(){
  const data=cache.archiveData;
  if(!data)return;
  const run=fn=>async()=>{try{await fn();$('notice').textContent='';}catch(e){$('notice').textContent=e.message;}};
  $('archive-source').onchange=run(()=>loadArchive($('archive-source').value,'telemetry'));
  $('archive-table').onchange=run(()=>loadArchive(data.source.source_sha256,$('archive-table').value));
  $('archive-prev').onclick=run(()=>loadArchive(data.source.source_sha256,data.table,Math.max(0,data.offset-50)));
  $('archive-next').onclick=run(()=>loadArchive(data.source.source_sha256,data.table,data.offset+50));
  $('archive-export').onclick=run(async()=>{
    const all=[];let offset=0;
    while(offset<data.total){
      const pageData=await api(`archive/${encodeURIComponent(data.source.source_sha256)}/${encodeURIComponent(data.table)}?limit=2000&offset=${offset}`);
      all.push(...pageData.records);
      if(!pageData.records.length)break;
      offset+=pageData.records.length;
    }
    download(JSON.stringify({...data,offset:0,records:all},null,2),`original-${data.table}.json`,'application/json');
  });
}

function render(){
  if(!token)return;
  document.querySelectorAll('[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===page));
  const [title,sub]=titles[page];
  $('page-title').textContent=title;
  $('page-subtitle').textContent=sub;
  $('crumb').textContent=pages.find(p=>p[0]===page)[1];
  
  const latest=cache.latest,t=latest?.telemetry?.payload,d=latest?.telemetry?.decision,system=cache.system||{};
  $('connection').textContent=(t?.mode||appMode)+' · '+(latest?.connectivity||'NO DATA');
  $('connection').className='badge '+(latest?.connectivity==='ONLINE'?'success':'warn');
  
  if(!device&&page!=='archive'){
    if(appMode==='SIMULATION'){
      $('content').innerHTML=empty('Laboratory simulation sandbox','Click New run above to spawn simulated telemetry and test fault scenarios.');
    }else{
      $('content').innerHTML=empty('No physical ESP32 device selected','Click + Register ESP32 above to register a physical unit and obtain its device token.');
    }
    return;
  }

  let html='';
  if(page==='overview')html=kpis()+`<div class="two-col">${chartCard('chamber_temp_c','Chamber thermal trend','°C',true)}${control()}</div>`+risks()+`<div class="two-col equal">${timeline(5)}${map()}</div>`;
  if(page==='live')html=kpis()+`<div class="two-col equal">${chartCard('chamber_temp_c','Chamber temperature (DS18B20)','°C',true)}${chartCard('heatsink_temp_c','Heatsink temperature (DS18B20)','°C')}${chartCard('sht31_temp_c','Ambient temperature (SHT31)','°C')}${chartCard('humidity_pct','Humidity (SHT31)','%')}${chartCard('primary_current_a','Primary current (ACS712)','A')}</div>`;
  if(page==='predictive')html=risks()+`<section class="card"><h2>Inference details</h2>${row('Model version',latest?.prediction?.model_version)}${row('Measured inference duration',fmt(latest?.prediction?.inference_ms,2)+' ms')}${row('Decision threshold',fmt(latest?.prediction?.threshold,3))}${row('Validation scope','Anomaly classification on active telemetry stream')}<p class="card-sub">ML risk can raise a warning. Confirmed primary faults require sensor evidence. Critical safety rules take precedence.</p></section>`;
  if(page==='healing')html=`<div class="two-col">${timeline(100)}${control()}</div>`+commandTable();
  if(page==='equipment')html=`<div class="equipment">${[['ESP32-S3','Edge controller','Acquisition and local control. Pin assignment awaits exact board.'],['DS18B20 × 2','Temperature probes','One chamber probe, one shared heatsink probe.'],['SHT31','Temperature & humidity','Secondary chamber temperature and humidity.'],['ACS712 20A × 1','Primary current only','Backup current requires an external meter.'],['Reed switch','Door monitoring','Door events are distinguished from cooling failures.'],['NEO-6M','GPS location','No-fix state uses null coordinates.'],['TEC1-12706','Primary cooling','Independently switched, fused primary branch.'],['TEC1-12701 / 12703','Backup cooling','Primary OFF confirmation precedes activation.'],['2-channel MOSFET','Cooling interlock','Both Peltiers must never be commanded ON together.'],['Shared heatsink + fan','Thermal assembly','Fan uses unswitched 12 V; shared overheating inhibits both Peltiers.'],['12 V / 15 A + 5 V','Separate supplies','Cooling supply and regulated controller USB supply.'],['Buzzer + 2–3 LEDs','Local indication','OLED and push buttons optional additions.']].map(([a,b,c])=>`<section class="card">${badge(appMode==='HARDWARE'?'HARDWARE MODE':'SIMULATION','neutral')}<h2>${esc(a)}</h2><h3>${esc(b)}</h3><p>${esc(c)}</p></section>`).join('')}</div>`;
  if(page==='routing')html=map()+`<section class="card"><h2>Facility catalogue</h2><p class="card-sub">Demo records are fictional. Real hardware uses VERIFIED facilities only.</p>${table(['Facility','Available','Temperature °C','Capacity kg','Source'],(cache.warehouses||[]).map(w=>[w.name,w.available?'Yes':'No',w.minimum_temperature+' to '+w.maximum_temperature,w.capacity,w.source]))}</section>`;
  if(page==='alerts')html=`<section class="card"><h2>Recorded faults</h2>${(cache.faults||[]).length?table(['Time','Mode','State','Reason','Source','Lifecycle'],cache.faults.map(e=>[clock(e.timestamp),e.payload.mode||'SYSTEM',e.payload.new_state,e.payload.reason,e.payload.source,e.payload.resolved?(e.payload.resolution||'RESOLVED'):'ACTIVE'])):'<div class="empty">No fault events recorded for this device.</div>'}</section>`;
  if(page==='history')html=`<section class="card"><div class="card-head"><h2>Telemetry history</h2><button id="download-history" class="secondary">Export JSON</button></div>${table(['Acquired','Sequence','Chamber °C','Current A','Observed state','Decision','Mode','Archived'],(cache.history||[]).map(r=>[clock(r.timestamp),r.sequence,fmt(r.payload.chamber_temp_c),fmt(r.payload.primary_current_a),r.payload.system_state,r.decision.state,r.mode,r.archived?'Yes':'No']))}</section>`;
  if(page==='analytics'){const m=system.model||{};html=`<section class="card"><div class="card-head"><h2>Held-out test results</h2>${badge(m.training_provenance||'UNAVAILABLE','warn')}</div>${table(['Estimator','Precision','Recall','F1','ROC AUC','Test samples'],Object.entries(m.test||{}).map(([name,v])=>[name,fmt(v.precision,3),fmt(v.recall,3),fmt(v.f1,3),fmt(v.roc_auc,3),v.samples]))}<p class="card-sub">${esc(m.split_method)}. Test evaluation on held-out datasets.</p></section><div class="three-col">${Object.entries(m.test||{}).map(([n,v])=>`<section class="card"><h2>${esc(n)} confusion matrix</h2>${table(['Actual / Predicted','Normal','Anomaly'],[['Normal',...v.confusion_matrix[0]],['Anomaly',...v.confusion_matrix[1]]])}</section>`).join('')}</div>`;}
  if(page==='health')html=`<div class="two-col equal"><section class="card"><h2>Software & connectivity</h2>${row('Telemetry freshness',latest?.connectivity)}${row('Seconds since reception',fmt(latest?.seconds_since_received))}${row('XGBoost + Random Forest',system.ml_ready?'LOADED':'UNAVAILABLE')}${row('Active Mode',appMode)}${row('Hardware validation',system.hardware_status)}${row('Buffered / dropped',system.simulation?.buffered_samples+' / '+system.simulation?.dropped_samples)}</section><section class="card"><h2>Sensor health reported by source</h2>${Object.entries(t?.sensor_health||{}).map(([k,v])=>row(k === 'current' && !v && (t?.mode || appMode) === 'HARDWARE' ? 'current (ACS712)' : k, k === 'current' && !v && (t?.mode || appMode) === 'HARDWARE' ? 'PENDING CALIBRATION' : (v?'VALID':'INVALID'))).join('')}${row('GPS',t?.gps?.fix?'FIX':'NO FIX')}${t?.vibration_detected !== undefined ? row('Vibration', t.vibration_detected ? 'DETECTED' : 'NORMAL') : ''}</section></div>`;
  if(page==='validation')html=`<section class="card"><div class="card-head"><div><h2>Physical measurement register</h2><p class="card-sub">Values stay empty until hardware evidence is submitted.</p></div><button id="export-validation" class="secondary">Export CSV</button></div>${table(['Measurement','Value','Status','Evidence source'],(cache.validation?.metrics||[]).map(m=>[m.metric,m.value??'—',m.status,m.measurement_source]))}</section>`;
  if(page==='archive')html=archiveView();
  
  $('content').innerHTML=html;
  if(page==='archive')bindArchive();
  if($('download-history'))$('download-history').onclick=async()=>{try{const base=apiUrl?apiUrl.replace(/\/$/,''):'';const r=await fetch(base+'/api/history/export?device_id='+encodeURIComponent(device),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('History export failed');download(await r.text(),device+'-telemetry.json','application/json');}catch(e){$('notice').textContent=e.message;}};
  if($('export-validation'))$('export-validation').onclick=async()=>{try{const base=apiUrl?apiUrl.replace(/\/$/,''):'';const r=await fetch(base+'/api/validation/export?format=csv&device_id='+encodeURIComponent(device),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('Export failed');download(await r.text(),'hardware-validation.csv','text/csv');}catch(e){$('notice').textContent=e.message;}};
}

function download(data,name,type){
  const a=document.createElement('a'),url=URL.createObjectURL(new Blob([data],{type}));
  a.href=url;a.download=name;a.click();
  setTimeout(()=>URL.revokeObjectURL(url),500);
}

// Init
setAppMode(appMode);
route();
login();
setInterval(refresh,2000);
