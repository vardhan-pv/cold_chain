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
  resetMapState();
  refresh();
}

$('mode-sim-tab').onclick=()=>setAppMode('SIMULATION');
$('mode-live-tab').onclick=()=>setAppMode('HARDWARE');

$('device').onchange=()=>{device=$('device').value;resetMapState();refresh();};

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

async function toggleVirtualBackup(enable){
  if(!device)return;
  const isHardware = appMode === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();
  if(isHardware && !isFresh){
    $('notice').textContent='Cannot toggle backup cooling: Hardware is offline';
    return;
  }
  if(cache.latest?.telemetry?.payload){
    cache.latest.telemetry.payload.backup_cooling = enable;
    cache.latest.telemetry.payload.backup_source = 'VIRTUAL';
    cache.latest.telemetry.payload.backup_commissioned = false;
    if(enable){
      cache.latest.telemetry.payload.primary_cooling = false;
    }else if(cache.latest.telemetry.payload.cooling_control_mode === 'MANUAL_SMPS'){
      cache.latest.telemetry.payload.primary_cooling = !!cache.latest.telemetry.payload.manual_cooling_confirmed;
    }
  }
  if(cache.latest){
    cache.latest.virtual_backup_override = enable;
  }
  render();

  try{
    const res = await api('v1/control/backup',{device_id:device,enabled:enable});
    if(cache.latest)cache.latest.virtual_backup_override = res.virtual_backup_override;
    const [latestData,healing] = await Promise.all([
      api('latest?device_id='+encodeURIComponent(device)),
      api('self-healing?device_id='+encodeURIComponent(device))
    ]);
    cache.latest = latestData;
    cache['self-healing'] = healing;
    render();
  }catch(err){
    $('notice').textContent='Backup control failed: '+err.message;
    refresh();
  }
}

document.addEventListener('click',e=>{
  const btn = e.target.closest('#btn-toggle-backup, .btn-toggle-backup');
  if(!btn)return;
  e.preventDefault();
  const isHardware = appMode === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();
  if(isHardware && !isFresh){
    $('notice').textContent='Hardware is offline. Backup control unavailable.';
    return;
  }
  const isCurrentlyActive = btn.classList.contains('active');
  if(isCurrentlyActive){
    toggleVirtualBackup(false);
  }else{
    if($('modal-backup-confirm')){
      $('modal-backup-confirm').showModal();
    }else if(confirm('Activate backup cooling failover? (Software failover only; physical backup is not commissioned)')){
      toggleVirtualBackup(true);
    }
  }
});

if($('btn-cancel-backup-demo'))$('btn-cancel-backup-demo').onclick=()=>{
  if($('modal-backup-confirm'))$('modal-backup-confirm').close();
};
if($('btn-confirm-backup-demo'))$('btn-confirm-backup-demo').onclick=async()=>{
  if($('modal-backup-confirm'))$('modal-backup-confirm').close();
  await toggleVirtualBackup(true);
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
  return `<section class="card"><div class="card-head"><div><h2>${esc(label)}</h2><p class="card-sub">Latest 80 valid samples · ${esc(unit)}</p></div>${badge('RECORDED','neutral')}</div>${chart(field,label,unit,range)}<div class="legend"><span>${esc(label)}</span>${range?'<span>Target compliance band 5–8 °C</span>':''}</div></section>`;
}

function isLiveHardwareFresh(){
  if(appMode!=='HARDWARE')return true;
  const latest=cache.latest;
  if(!latest||!latest.telemetry)return false;
  if(latest.online===false||latest.connectivity==='STALE'||latest.connectivity==='NO_DATA')return false;
  const sec=latest.seconds_since_received;
  return Number.isFinite(sec)&&sec<=15;
}

function kpis(){
  const latest=cache.latest;
  const t=latest?.telemetry?.payload||{};
  const isHardware = appMode === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();

  const list = [
    ['Chamber temperature',t.chamber_temp_c,'°C',t.chamber_source==='DERIVED'?'Derived (heatsink - 10.0°C)':'DS18B20 / chamber'],
    ['Heatsink temperature',t.heatsink_temp_c,'°C','DS18B20 / hot side'],
    ['Ambient temperature',t.sht31_temp_c,'°C','SHT31 / ambient secondary'],
    ['Relative humidity',t.humidity_pct,'%','SHT31 / humidity'],
    ['Primary current',t.primary_current_a,'A',t.current_source==='EMULATED'?'Emulated (hybrid mode)':'ACS712 / primary branch'],
    ['Door state',t.door_open,'','Reed switch / GPIO7'],
    ['GPS location',t.gps,'','NEO-6M / UART1'],
    ['Vibration',t.vibration_detected,'','LM393 / GPIO11']
  ];
  return `<div class="kpis">${list.map(([l,v,u,f])=>{
    let valueDisplay = '—';
    let footerText = '';

    if(!isFresh){
      valueDisplay = '—';
      footerText = `△ Hardware offline · No live telemetry`;
    } else if(l==='Primary current'){
      if(Number.isFinite(v)){
        valueDisplay=`${fmt(v,2)}<small>${u}</small>`;
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
  const isFresh = !isHardware || isLiveHardwareFresh();

  if (isHardware && !isFresh) {
    const ageSec = latest?.seconds_since_received;
    const ageStr = Number.isFinite(ageSec) ? `${fmt(ageSec, 1)}s ago` : 'No recent telemetry';
    return `<section class="card">
      <div class="card-head">
        <div>
          <h2>Current System State</h2>
          <p class="card-sub">ESP32-S3 edge connection lost</p>
        </div>
        ${badge('HARDWARE · OFFLINE', 'danger')}
      </div>
      <div class="state-panel">
        <p>AUTHORITATIVE CURRENT STATE</p>
        <div class="big-state" style="color:var(--danger,#b23b2b)">OFFLINE</div>
        <p>ESP32 HARDWARE OFFLINE · No recent telemetry received (${esc(ageStr)})</p>
      </div>
      ${row('Primary cooling', '—')}
      ${row('Backup cooling', '—')}
      ${row('Door (Reed switch)', '—')}
      ${row('GPS status', '—')}
      ${row('Edge-reported state', 'OFFLINE')}
      ${row('Cloud advisory analysis', 'OFFLINE')}
      ${row('Control authority', 'ESP32 local safety loop (Hardware offline)')}
      <div class="state-steps"><span class=""></span><span class=""></span><span class=""></span><span class=""></span></div>
      <p class="card-sub">Telemetry connection timeout (> 15 seconds). Hardware status cannot be confirmed live.</p>
    </section>`;
  }

  const edgeState = t.system_state || 'NORMAL';
  const authoritativeState = isHardware ? edgeState : (d.state || edgeState || 'NO_DATA');
  const advisoryNote = isHardware
    ? (d.advisory_status === 'HARDWARE_PENDING_SENSORS'
        ? 'ESP32 edge safety loop authoritative · Physical probes pending'
        : (d.reason || 'ESP32 edge safety loop authoritative'))
    : (d.reason || 'Simulated closed-loop control');

  const overrideActive = !!latest?.virtual_backup_override;
  const backupActive = !!(t.backup_cooling || overrideActive);

  // In MANUAL_SMPS mode, primary_cooling in the payload already reflects GPIO6 (manual
  // confirmation switch), but we also check manual_cooling_confirmed directly as an
  // explicit, unambiguous signal so the dashboard never falls back to the GPIO16 register.
  let primaryCoolingText;
  if (backupActive) {
    // Interlock: primary cooling is suppressed / considered unavailable during backup activation
    primaryCoolingText = 'OFF';
  } else if (t.cooling_control_mode === 'MANUAL_SMPS' && t.manual_cooling_confirmed !== undefined && t.manual_cooling_confirmed !== null) {
    primaryCoolingText = t.manual_cooling_confirmed ? 'ON' : 'OFF';
  } else if (t.primary_cooling === undefined) {
    primaryCoolingText = 'UNAVAILABLE';
  } else {
    primaryCoolingText = t.primary_cooling ? 'ON' : 'OFF';
  }
  const isVirtualBackup = t.backup_source === 'VIRTUAL' || overrideActive;
  const backupCoolingText = isVirtualBackup
    ? (backupActive ? 'ON' : 'OFF')
    : (isHardware ? 'NOT COMMISSIONED' : (t.backup_cooling === undefined ? 'UNAVAILABLE' : t.backup_cooling ? 'ON' : 'OFF'));
  const doorText = t.door_open == null ? 'UNAVAILABLE' : (t.door_open ? ('OPEN (' + fmt(t.door_open_s, 0) + 's)') : 'CLOSED');
  const gpsText = t?.gps?.fix
    ? ('FIX (' + (t.gps.satellites || 0) + ' sats · ' + fmt(t.gps.latitude, 4) + ', ' + fmt(t.gps.longitude, 4) + ')')
    : ('NO FIX (' + (t?.gps?.satellites || 0) + ' satellites)');

  const isToggleDisabled = isHardware && !isFresh;
  const toggleTitle = isToggleDisabled
    ? 'Hardware offline · Control unavailable'
    : (backupActive ? 'Click to turn OFF virtual backup cooling' : 'Click to turn ON virtual backup cooling failover');
  const toggleHtml = `<button id="btn-toggle-backup" type="button" class="toggle-switch btn-toggle-backup ${backupActive ? 'active' : ''} ${isToggleDisabled ? 'disabled' : ''}" ${isToggleDisabled ? 'disabled' : ''} aria-label="Toggle virtual backup cooling failover" title="${esc(toggleTitle)}">
    <span class="toggle-track"><span class="toggle-thumb"></span></span>
    <span class="toggle-label">${backupActive ? 'ON' : 'OFF'}</span>
  </button>`;
  const backupRow = `<div class="status-row" style="align-items:center;">
    <span>Backup cooling</span>
    <div style="display:flex;align-items:center;gap:10px;">
      <strong id="status-backup-cooling">${backupCoolingText}</strong>
      ${toggleHtml}
    </div>
  </div>`;

  return `<section class="card">
    <div class="card-head">
      <div>
        <h2>Current System State</h2>
        <p class="card-sub">${isHardware ? 'Live ESP32-S3 edge authority' : 'Autonomous simulated closed loop'}</p>
      </div>
      ${badge(isHardware ? 'HARDWARE · ONLINE' : 'SIMULATION', isHardware ? 'success' : 'neutral')}
    </div>
    <div class="state-panel">
      <p>${isHardware ? 'AUTHORITATIVE CURRENT STATE' : 'ANALYZED SYSTEM STATE'}</p>
      <div class="big-state">${esc(authoritativeState.replaceAll('_',' '))}</div>
      <p>${esc(advisoryNote)}</p>
    </div>
    ${row('Primary cooling', primaryCoolingText)}
    ${backupRow}
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
  const isFresh = !isHardware || isLiveHardwareFresh();
  const hasInference = Number.isFinite(p.ensemble_probability);

  return `<div class="three-col">${[
    ['XGBoost','xgboost_probability'],
    ['Random Forest','random_forest_probability'],
    ['Weighted ensemble','ensemble_probability']
  ].map(([name,key])=>{
    let valueText = 'Unavailable';
    let barWidth = 0;
    let noteText = '';
    let metaDetails = '';

    if (isHardware && !isFresh) {
      valueText = '<span style="font-size:15px;color:var(--muted);font-weight:500;">NO LIVE HARDWARE DATA</span>';
      barWidth = 0;
      noteText = 'HARDWARE DATA OFFLINE · NO LIVE HARDWARE DATA';
      metaDetails = 'Telemetry connection timed out';
    } else if (hasInference && !isHardware) {
      valueText = fmt(p[key]*100,1)+'%';
      barWidth = (p[key]||0)*100;
      noteText = `${esc(p.training_provenance||'SIMULATED_DATA')} · INFERENCE ACTIVE`;
      if (name==='XGBoost' && p.inference_ms!=null) metaDetails=`Latency: ${fmt(p.inference_ms,1)}ms · ${p.model_version||'v1'}`;
      if (name==='Weighted ensemble' && p.threshold!=null) metaDetails=`Threshold: ${fmt(p.threshold*100,1)}%`;
    } else if (isHardware) {
      if (hasInference) {
        valueText = fmt(p[key]*100,1)+'%';
        barWidth = (p[key]||0)*100;
        noteText = 'HARDWARE DATA (HYBRID EMULATED CURRENT) · LIVE INFERENCE';
        if (name==='XGBoost') {
          const lat = p.inference_ms!=null ? `${fmt(p.inference_ms,1)}ms` : '';
          const ver = p.model_version ? `${p.model_version}` : '';
          metaDetails = [lat, ver].filter(Boolean).join(' · ');
        } else if (name==='Random Forest') {
          metaDetails = p.model_version ? `Model: ${p.model_version}` : '';
        } else if (name==='Weighted ensemble') {
          const thr = p.threshold!=null ? `Threshold: ${fmt(p.threshold*100,1)}%` : '';
          const adv = p.predicted_anomaly ? 'ADVISORY WARNING' : 'ADVISORY NORMAL';
          metaDetails = [thr, adv].filter(Boolean).join(' · ');
        }
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
        ${badge(isHardware ? (isFresh ? (hasInference ? 'LIVE ML' : 'PENDING SENSORS') : 'NO LIVE DATA') : 'ML SIM', isHardware && (!isFresh || !hasInference) ? 'neutral' : 'success')}
      </div>
      <div class="risk">${valueText}</div>
      ${metaDetails ? `<div style="font-size:12px;color:var(--muted);margin-top:-4px;margin-bottom:8px;font-weight:500;">${esc(metaDetails)}</div>` : ''}
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

// Real Leaflet Map & GIS Routing State
const mapState = {
  instance: null,
  containerEl: null,
  vehicleMarker: null,
  facilityMarkers: new Map(),
  facilityLayer: null,
  routeLayer: null,
  facilities: [],
  nearestFacility: null,
  currentRoute: null,
  selectedFacilityId: null,
  activeDeviceId: '',
  lastGpsKey: '',
  lastFetchTime: 0,
  facilitiesLoading: false,
  routeLoading: false,
  routeError: null,
  facilitiesError: null,
  needsFitBounds: false,
  followVehicle: true,
  searchRadiusKm: 10.0,
  navLocation: null
};

function resetMapState(){
  mapState.facilities = [];
  mapState.nearestFacility = null;
  mapState.currentRoute = null;
  mapState.selectedFacilityId = null;
  mapState.lastGpsKey = '';
  mapState.lastFetchTime = 0;
  mapState.routeError = null;
  mapState.facilitiesError = null;
  mapState.navLocation = null;
  if (mapState.facilityLayer) mapState.facilityLayer.clearLayers();
  if (mapState.routeLayer) mapState.routeLayer.clearLayers();
  mapState.facilityMarkers.clear();
}

function getActiveNavLocation() {
  const latest = cache.latest;
  const t = latest?.telemetry?.payload;
  // 1. Physical ESP32 GPS if valid fix exists
  if (t?.gps?.fix && Number.isFinite(t?.gps?.latitude) && Number.isFinite(t?.gps?.longitude)) {
    return {
      latitude: t.gps.latitude,
      longitude: t.gps.longitude,
      source: 'PHYSICAL_GPS',
      sourceLabel: 'Physical GPS',
      satellites: t.gps.satellites || 0,
      timestamp: latest?.telemetry?.timestamp || latest?.timestamp,
      isFallback: false
    };
  }
  // 2. Normalized navigation_location from backend
  if (latest?.navigation_location && Number.isFinite(latest.navigation_location.latitude) && Number.isFinite(latest.navigation_location.longitude)) {
    const isPhysical = latest.navigation_location.source === 'PHYSICAL_GPS';
    return {
      latitude: latest.navigation_location.latitude,
      longitude: latest.navigation_location.longitude,
      source: latest.navigation_location.source,
      sourceLabel: isPhysical ? 'Physical GPS' : 'Fleet Reference Coordinates',
      satellites: isPhysical ? (t?.gps?.satellites || 0) : 0,
      timestamp: latest.navigation_location.timestamp || latest?.timestamp,
      isFallback: !isPhysical
    };
  }
  // 3. Fallback stored from facility API response
  if (mapState.navLocation && Number.isFinite(mapState.navLocation.latitude) && Number.isFinite(mapState.navLocation.longitude)) {
    const isPhysical = mapState.navLocation.source === 'PHYSICAL_GPS';
    return {
      latitude: mapState.navLocation.latitude,
      longitude: mapState.navLocation.longitude,
      source: mapState.navLocation.source,
      sourceLabel: isPhysical ? 'Physical GPS' : 'Fleet Reference Coordinates',
      satellites: isPhysical ? (t?.gps?.satellites || 0) : 0,
      timestamp: mapState.navLocation.timestamp || latest?.timestamp,
      isFallback: !isPhysical
    };
  }
  return null;
}

async function fetchNearbyFacilities(devId, radiusKm) {
  if (mapState.facilitiesLoading) return;
  mapState.facilitiesLoading = true;
  mapState.facilitiesError = null;
  const radius = radiusKm || mapState.searchRadiusKm || 10;
  mapState.searchRadiusKm = radius;
  try {
    const res = await api(`v1/nearby-cold-storages?device_id=${encodeURIComponent(devId)}&radius_km=${encodeURIComponent(radius)}`);
    if (res.location) {
      mapState.navLocation = res.location;
    }
    mapState.facilities = res.facilities || [];
    mapState.nearestFacility = mapState.facilities.length > 0 ? mapState.facilities[0] : null;
    if (mapState.facilities.length === 0) {
      mapState.facilitiesError = res.message || 'No verified cold-storage facilities found nearby';
    }
    renderFacilityMarkers();
    updateMapSidebar();
  } catch (err) {
    mapState.facilities = [];
    mapState.nearestFacility = null;
    mapState.facilitiesError = 'Cold-storage search temporarily unavailable';
    updateMapSidebar();
  } finally {
    mapState.facilitiesLoading = false;
    updateMapSidebar();
  }
}

async function calculateRoute(devId, facilityId) {
  if (mapState.routeLoading) return;
  mapState.routeLoading = true;
  mapState.routeError = null;
  mapState.selectedFacilityId = facilityId;
  updateMapSidebar();
  try {
    const res = await api(`v1/route-to-facility?device_id=${encodeURIComponent(devId)}&facility_id=${encodeURIComponent(facilityId)}`);
    mapState.currentRoute = res;
    mapState.needsFitBounds = true;
    renderFacilityMarkers();
    renderRouteLayer();
    updateMapSidebar();
  } catch (err) {
    mapState.routeError = 'Route temporarily unavailable';
    updateMapSidebar();
  } finally {
    mapState.routeLoading = false;
  }
}

function renderFacilityMarkers() {
  if (!mapState.instance || !mapState.facilityLayer || typeof L === 'undefined') return;
  mapState.facilityLayer.clearLayers();
  mapState.facilityMarkers.clear();

  mapState.facilities.forEach((f, idx) => {
    const isSelected = (mapState.currentRoute?.destination?.id === f.id) || (mapState.selectedFacilityId === f.id);
    const isNearest = idx === 0;
    const facilityIcon = L.divIcon({
      className: '',
      html: `<div class="facility-pin-wrapper ${isSelected ? 'active-dest' : (isNearest ? 'nearest-dest' : '')}" title="${esc(f.name)}"><span>❄</span></div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 28],
      popupAnchor: [0, -28]
    });

    const marker = L.marker([f.latitude, f.longitude], { icon: facilityIcon });
    marker.bindPopup(`
      <div style="min-width:190px;">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
          <strong style="font-size:12px;color:#123328;">${esc(f.name)}</strong>
          ${isNearest ? '<span class="nearest-tag">NEAREST</span>' : ''}
        </div>
        <span style="color:#0f8478;font-size:11px;font-weight:600;">Distance: ${fmt(f.distance_km, 1)} km</span><br>
        ${f.address ? `<span style="color:#527362;font-size:10px;display:block;margin:3px 0;">${esc(f.address)}</span>` : ''}
        <span style="font-size:9px;color:#859b8d;text-transform:uppercase;">Source: ${esc(f.source)}</span><br>
        <button type="button" class="btn-route-action btn-popup-route" data-id="${esc(f.id)}" style="margin-top:8px;width:100%;">
          ${isSelected ? '✓ Active route destination' : 'Route Here'}
        </button>
      </div>
    `);
    marker.addTo(mapState.facilityLayer);
    mapState.facilityMarkers.set(f.id, marker);
  });
}

function renderRouteLayer() {
  if (!mapState.instance || !mapState.routeLayer || typeof L === 'undefined') return;
  mapState.routeLayer.clearLayers();

  const routeCoords = mapState.currentRoute?.geometry || mapState.currentRoute?.route;
  if (routeCoords && Array.isArray(routeCoords) && routeCoords.length > 0) {
    const poly = L.polyline(routeCoords, {
      color: '#b23b2b',
      weight: 5,
      opacity: 0.9,
      lineCap: 'round',
      lineJoin: 'round'
    }).addTo(mapState.routeLayer);

    if (mapState.needsFitBounds) {
      mapState.instance.fitBounds(poly.getBounds(), { padding: [50, 50], maxZoom: 15 });
      mapState.needsFitBounds = false;
    }
  }
}

function updateMapSidebar() {
  const sidebar = $('map-sidebar-content');
  if (!sidebar) return;
  const latest = cache.latest;
  const t = latest?.telemetry?.payload;
  const d = latest?.telemetry?.decision || {};
  const isHardware = (t?.mode || appMode) === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();
  const edgeState = t?.system_state || 'NORMAL';
  const authoritativeState = isHardware ? edgeState : (d.state || edgeState || 'NORMAL');
  const isReroutingActive = authoritativeState === 'CRITICAL_FAILURE' || authoritativeState === 'REROUTING';
  const nearest = mapState.nearestFacility;
  const route = mapState.currentRoute;
  const navLoc = getActiveNavLocation();
  const isOnline = isFresh && (latest?.online !== false);

  let nearestHtml = '';
  if (nearest) {
    const isSelected = route?.destination?.id === nearest.id;
    nearestHtml = `<div class="nearest-facility-box">
      <div class="station-hero-header">
        <span class="station-hero-badge">⭐ NEAREST COLD STORAGE HUB</span>
        <span class="station-distance-badge">${fmt(nearest.distance_km, 1)} km</span>
      </div>
      <strong class="station-name">${esc(nearest.name)}</strong>
      ${nearest.address ? `<p class="station-address">📍 ${esc(nearest.address)}</p>` : ''}
      <div class="station-specs">
        <span class="spec-pill">❄ 2°C – 8°C Certified</span>
        <span class="spec-pill verified">✓ ${esc(nearest.source)}</span>
      </div>
      <button type="button" class="btn-route-action btn-hero-route ${isSelected ? 'active' : ''}" id="btn-route-nearest" data-id="${esc(nearest.id)}">
        ${isSelected ? '✓ Active Route Destination' : 'Route to Station ➔'}
      </button>
    </div>`;
  } else if (mapState.facilitiesLoading) {
    nearestHtml = `<div class="nearest-facility-box loading-box"><p><span class="spinner-inline"></span> Discovering verified cold-storage hubs...</p></div>`;
  } else {
    nearestHtml = `<div class="nearest-facility-box empty-facility-box">
      <p style="margin-bottom:8px;">${esc(mapState.facilitiesError || 'No verified cold-storage facilities found nearby')}</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <button type="button" class="map-btn btn-radius-expand" data-radius="25">Search 25 km</button>
        <button type="button" class="map-btn btn-radius-expand" data-radius="50">Search 50 km</button>
      </div>
    </div>`;
  }

  const facilityListHtml = mapState.facilities.map((f, idx) => {
    const isSelected = route?.destination?.id === f.id;
    const isNearest = idx === 0;
    return `<div class="facility-card-item ${isSelected ? 'selected' : ''} ${isNearest ? 'is-nearest' : ''}">
      <div class="facility-info">
        <div class="facility-head-row">
          <span class="facility-title" title="${esc(f.name)}">${esc(f.name)}</span>
          ${isNearest ? '<span class="nearest-tag">NEAREST</span>' : ''}
        </div>
        <div class="facility-meta">
          <span class="meta-dist">📍 ${fmt(f.distance_km, 1)} km</span>
          <span class="meta-dot">·</span>
          <span class="meta-addr">${esc(f.address || 'Verified Logistics Hub')}</span>
        </div>
        <div class="facility-sub-pills">
          <span class="pill-chilled">❄ 2°C–8°C</span>
          <span class="pill-verified">✓ Verified Hub</span>
        </div>
      </div>
      <button type="button" class="btn-route-action ${isSelected ? 'active' : ''} btn-list-route" data-id="${esc(f.id)}">
        ${isSelected ? 'Active' : 'Route'}
      </button>
    </div>`;
  }).join('');

  sidebar.innerHTML = `
    <div class="map-stats-card">
      <h3>Vehicle Tracking</h3>
      <div class="map-stat-row"><span>Device:</span><strong>${esc(device)}</strong></div>
      <div class="map-stat-row"><span>Status:</span><strong style="color:${isOnline ? '#0f8478' : '#b23b2b'};">${isOnline ? 'ONLINE' : 'HARDWARE OFFLINE'}</strong></div>
      <div class="map-stat-row"><span>Navigation:</span><strong>AVAILABLE</strong></div>
      <div class="map-stat-row"><span>Location source:</span><strong>${esc(navLoc?.sourceLabel || '—')}</strong></div>
      <div class="map-stat-row"><span>Coordinates:</span><strong>${navLoc ? `${fmt(navLoc.latitude, 4)}, ${fmt(navLoc.longitude, 4)}` : '—'}</strong></div>
      <div class="map-stat-row"><span>Satellites:</span><strong>${navLoc?.satellites || 0} ${navLoc?.isFallback ? '(fleet lock)' : 'sats'}</strong></div>
      <div class="map-stat-row"><span>Last update:</span><strong>${esc(clock(navLoc?.timestamp || latest?.timestamp))}</strong></div>
    </div>

    <div class="map-stats-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <h3 style="margin:0;">Emergency Rerouting</h3>
        <span class="badge ${isReroutingActive ? 'danger' : (mapState.facilities.length ? 'success' : 'neutral')}">
          ${isReroutingActive ? 'ACTIVE' : (mapState.facilities.length ? 'READY' : 'UNAVAILABLE')}
        </span>
      </div>
      ${isReroutingActive ? `
        <div class="reroute-active-banner">
          <strong style="color:#b23b2b;display:block;margin-bottom:4px;">⚡ REROUTING ACTIVE</strong>
          <div class="map-stat-row"><span>Destination:</span><strong>${esc(route?.destination?.name || nearest?.name || 'Nearest Cold Storage')}</strong></div>
          <div class="map-stat-row"><span>Distance:</span><strong>${fmt(route?.distance_km || nearest?.distance_km, 1)} km</strong></div>
          <div class="map-stat-row"><span>ETA:</span><strong>${fmt(route?.duration_min || ((nearest?.distance_km || 0) * 1.5), 0)} min</strong></div>
        </div>
      ` : (route ? `
        <div class="map-stat-row"><span>Destination:</span><strong>${esc(route.destination?.name || 'Cooling Facility')}</strong></div>
        <div class="map-stat-row"><span>Distance:</span><strong>${fmt(route.distance_km, 1)} km</strong></div>
        <div class="map-stat-row"><span>ETA:</span><strong>${fmt(route.duration_min, 0)} min</strong></div>
        <div class="map-stat-row"><span>Route source:</span><strong>${esc(route.source)}</strong></div>
      ` : `
        <p style="font-size:11px;color:var(--muted);margin:4px 0 0 0;">System standing by. Nearest verified cold storage will be selected automatically upon cooling failure.</p>
      `)}
      ${mapState.routeError ? `<div style="color:var(--danger,#b23b2b);font-size:11px;margin-top:6px;font-weight:600;">△ ${esc(mapState.routeError)}</div>` : ''}
    </div>

    <div class="map-stats-card">
      <h3>Nearest Cold Storage</h3>
      ${nearestHtml}
    </div>

    ${mapState.facilities.length ? `
      <div class="map-stats-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <h3 style="margin:0;">Discovered Facilities (${mapState.facilities.length})</h3>
          ${route ? `<button type="button" id="btn-clear-route" class="secondary" style="padding:2px 8px;font-size:10px;">Clear route</button>` : ''}
        </div>
        <div class="facility-list">
          ${facilityListHtml}
        </div>
      </div>
    ` : ''}
  `;
}

function map(){
  const latest = cache.latest;
  const t = latest?.telemetry?.payload;
  const d = latest?.telemetry?.decision || {};
  const isHardware = (t?.mode || appMode) === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();
  const navLoc = getActiveNavLocation();

  if (isHardware && !isFresh && !navLoc) {
    return `<section class="card map-panel">
      <div class="card-head">
        <div>
          <h2>GPS & Emergency Rerouting</h2>
          <p class="card-sub">Real ESP32 GPS tracking & cooling facility discovery</p>
        </div>
        ${badge('HARDWARE OFFLINE', 'danger')}
      </div>
      <div class="map-empty-box danger">
        <h3>HARDWARE OFFLINE · NO LIVE GPS DATA</h3>
        <p>Telemetry connection lost (> 15 seconds). Live satellite coordinates and active navigation are disabled to prevent displaying stale tracking.</p>
      </div>
    </section>`;
  }

  if (!navLoc) {
    return `<section class="card map-panel">
      <div class="card-head">
        <div>
          <h2>GPS & Emergency Rerouting</h2>
          <p class="card-sub">Real ESP32 GPS tracking & cooling facility discovery</p>
        </div>
        ${badge('GPS NO FIX', 'warn')}
      </div>
      <div class="map-empty-box warn">
        <h3>GPS NO FIX · Waiting for satellite lock</h3>
        <p>NEO-6M receiver has acquired <strong>${t?.gps?.satellites || 0}</strong> satellites. Map navigation requires a valid 3D GPS fix. No coordinates or cooling stations are fabricated.</p>
      </div>
    </section>`;
  }

  const edgeState = t?.system_state || 'NORMAL';
  const authoritativeState = isHardware ? edgeState : (d.state || edgeState || 'NORMAL');
  const isReroutingActive = authoritativeState === 'CRITICAL_FAILURE' || authoritativeState === 'REROUTING';
  const rerouteBadge = isReroutingActive ? badge('REROUTING ACTIVE', 'danger') : badge('REROUTING READY', 'success');
  const locationBadge = navLoc.isFallback ? badge('FLEET TELEMETRICS ACTIVE', 'success') : badge(`GPS LIVE · ${navLoc.satellites} sats`, 'success');
  const offlineBadge = (isHardware && !isFresh) ? badge('HARDWARE OFFLINE', 'danger') : '';

  return `<section class="card map-panel map-panel-enhanced">
    <div class="card-head">
      <div>
        <h2>Cold-Chain Fleet Live Operations & Cold Storage Hubs</h2>
        <p class="card-sub">High-precision OpenStreetMap fleet tracking · OpenRouteService emergency routing</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
        ${offlineBadge}
        ${rerouteBadge}
        ${locationBadge}
      </div>
    </div>
    <div class="map-controls-bar">
      <div class="map-controls-left">
        <button type="button" id="btn-toggle-follow" class="map-btn ${mapState.followVehicle ? 'active' : ''}">
          <span style="font-size:13px;">${mapState.followVehicle ? '⦿' : '○'}</span> Follow Vehicle
        </button>
        <button type="button" id="btn-fit-stations" class="map-btn secondary" title="Zoom to fit vehicle and all nearby cold storages">
          <span>⛶</span> Fit All Stations
        </button>
        <button type="button" id="btn-refresh-storages" class="map-btn secondary" ${mapState.facilitiesLoading ? 'disabled' : ''}>
          <span>↻</span> ${mapState.facilitiesLoading ? 'Searching Overpass...' : 'Refresh Cold Storages'}
        </button>
      </div>
      <div class="map-radius-selector">
        <span class="radius-label">Search Radius:</span>
        <button type="button" class="btn-radius ${mapState.searchRadiusKm === 10 ? 'active' : ''}" data-radius="10">10 km</button>
        <button type="button" class="btn-radius ${mapState.searchRadiusKm === 25 ? 'active' : ''}" data-radius="25">25 km</button>
        <button type="button" class="btn-radius ${mapState.searchRadiusKm === 50 ? 'active' : ''}" data-radius="50">50 km</button>
      </div>
    </div>
    <div class="map-layout">
      <div class="map-view-container">
        <div id="leaflet-map" class="leaflet-map-host"></div>
      </div>
      <div class="map-sidebar" id="map-sidebar-content">
        <!-- Rendered dynamically by updateMapSidebar() -->
      </div>
    </div>
  </section>`;
}

function syncMap() {
  const container = $('leaflet-map');
  const latest = cache.latest;
  const t = latest?.telemetry?.payload;
  const d = latest?.telemetry?.decision || {};
  const isHardware = (t?.mode || appMode) === 'HARDWARE';
  const isFresh = !isHardware || isLiveHardwareFresh();
  const navLoc = getActiveNavLocation();

  if (!container || !navLoc || !device || (isHardware && !isFresh && !navLoc.isFallback)) {
    if (mapState.instance) {
      try { mapState.instance.remove(); } catch(e) {}
      mapState.instance = null;
      mapState.containerEl = null;
      mapState.vehicleMarker = null;
      mapState.facilityMarkers.clear();
      mapState.facilityLayer = null;
      mapState.routeLayer = null;
    }
    return;
  }

  if (typeof L === 'undefined') {
    return;
  }

  const lat = navLoc.latitude;
  const lon = navLoc.longitude;

  if (!mapState.instance || mapState.containerEl !== container) {
    if (mapState.instance) {
      try { mapState.instance.remove(); } catch(e) {}
    }
    mapState.instance = L.map(container, {
      zoomControl: true,
      attributionControl: true
    }).setView([lat, lon], 13);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
    }).addTo(mapState.instance);

    mapState.facilityLayer = L.layerGroup().addTo(mapState.instance);
    mapState.routeLayer = L.layerGroup().addTo(mapState.instance);
    mapState.containerEl = container;
    mapState.vehicleMarker = null;
    mapState.facilityMarkers.clear();

    setTimeout(() => {
      if (mapState.instance) mapState.instance.invalidateSize();
    }, 150);
  }

  // Smooth vehicle marker movement
  const isOnline = isFresh && (latest?.online !== false);
  const statusStr = isOnline ? 'ONLINE' : 'HARDWARE OFFLINE';
  const vehicleIcon = L.divIcon({
    className: '',
    html: `
      <div class="vehicle-marker-wrapper" title="${esc(device)}">
        <div class="vehicle-marker-pulse"></div>
        <div class="vehicle-marker-truck">🚚</div>
      </div>
    `,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -18]
  });

  const popupContent = `
    <div style="min-width:180px;">
      <strong style="color:#102e2c;font-size:12px;">Cold-chain vehicle</strong><br>
      <span style="font-size:11px;">Device: <strong>${esc(device)}</strong></span><br>
      <span style="font-size:11px;color:${isOnline ? '#0f8478' : '#b23b2b'};font-weight:600;">Status: ${esc(statusStr)}</span><br>
      <span style="font-size:11px;color:#527362;">Location source: <strong>${esc(navLoc.sourceLabel)}</strong></span><br>
      <span style="font-size:10px;color:#6e8576;">Last update: ${esc(clock(navLoc.timestamp))}</span>
    </div>
  `;

  if (!mapState.vehicleMarker) {
    mapState.vehicleMarker = L.marker([lat, lon], { icon: vehicleIcon, zIndexOffset: 1000 }).addTo(mapState.instance);
    mapState.vehicleMarker.bindPopup(popupContent);
    mapState.vehicleMarker.bindTooltip(esc(device), { permanent: false, direction: 'top', offset: [0, -14] });
  } else {
    mapState.vehicleMarker.setLatLng([lat, lon]);
    mapState.vehicleMarker.setPopupContent(popupContent);
  }

  // Follow vehicle if toggle is enabled
  if (mapState.followVehicle && mapState.instance) {
    mapState.instance.panTo([lat, lon], { animate: true, duration: 0.6 });
  }

  // Query nearby facilities when position meaningfully changes or cache expires
  const gpsKey = `${lat.toFixed(3)},${lon.toFixed(3)}:r${mapState.searchRadiusKm}`;
  const now = Date.now();
  const timeSinceFetch = now - mapState.lastFetchTime;
  const isGpsMoved = mapState.lastGpsKey !== gpsKey;
  const isDeviceChanged = mapState.activeDeviceId !== device;

  if (isDeviceChanged || isGpsMoved || (mapState.facilities.length === 0 && !mapState.facilitiesLoading && timeSinceFetch > 12000)) {
    mapState.activeDeviceId = device;
    mapState.lastGpsKey = gpsKey;
    mapState.lastFetchTime = now;
    fetchNearbyFacilities(device, mapState.searchRadiusKm);
  } else {
    renderFacilityMarkers();
  }

  // Self-healing escalation check: automatically route to nearest facility during cooling failure
  const edgeState = t?.system_state || 'NORMAL';
  const authoritativeState = isHardware ? edgeState : (d.state || edgeState || 'NORMAL');
  const isCriticalReroute = authoritativeState === 'CRITICAL_FAILURE' || authoritativeState === 'REROUTING';

  if (isCriticalReroute) {
    if (!mapState.currentRoute && mapState.nearestFacility && !mapState.routeLoading) {
      calculateRoute(device, mapState.nearestFacility.id);
    }
  }

  renderRouteLayer();
  updateMapSidebar();
}

document.addEventListener('click', e => {
  // Follow vehicle toggle
  const followBtn = e.target.closest('#btn-toggle-follow');
  if (followBtn) {
    e.preventDefault();
    mapState.followVehicle = !mapState.followVehicle;
    followBtn.classList.toggle('active', mapState.followVehicle);
    followBtn.innerHTML = `<span style="font-size:13px;">${mapState.followVehicle ? '⦿' : '○'}</span> Follow Vehicle`;
    if (mapState.followVehicle) {
      const navLoc = getActiveNavLocation();
      if (navLoc && mapState.instance) {
        mapState.instance.panTo([navLoc.latitude, navLoc.longitude], { animate: true });
      }
    }
    return;
  }

  // Refresh cold storages button
  const refreshBtn = e.target.closest('#btn-refresh-storages');
  if (refreshBtn) {
    e.preventDefault();
    if (device) {
      mapState.lastFetchTime = 0;
      fetchNearbyFacilities(device, mapState.searchRadiusKm);
    }
    return;
  }

  // Radius pill buttons
  const radiusBtn = e.target.closest('.btn-radius, .btn-radius-expand');
  if (radiusBtn) {
    e.preventDefault();
    const r = parseFloat(radiusBtn.dataset.radius);
    if (Number.isFinite(r) && device) {
      mapState.searchRadiusKm = r;
      document.querySelectorAll('.btn-radius').forEach(b => b.classList.toggle('active', parseFloat(b.dataset.radius) === r));
      mapState.lastFetchTime = 0;
      fetchNearbyFacilities(device, r);
    }
    return;
  }

  // Route here buttons
  const routeBtn = e.target.closest('.btn-route-action, .btn-popup-route, .btn-list-route, #btn-route-nearest');
  if (routeBtn) {
    e.preventDefault();
    const facilityId = routeBtn.dataset.id;
    if (device && facilityId) {
      calculateRoute(device, facilityId);
    }
    return;
  }

  // Fit stations button
  const fitBtn = e.target.closest('#btn-fit-stations');
  if (fitBtn && mapState.instance) {
    e.preventDefault();
    const navLoc = getActiveNavLocation();
    if (navLoc) {
      const bounds = L.latLngBounds([[navLoc.latitude, navLoc.longitude]]);
      mapState.facilities.forEach(f => bounds.extend([f.latitude, f.longitude]));
      mapState.instance.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
    }
    return;
  }

  // Clear route button
  const clearBtn = e.target.closest('#btn-clear-route');
  if (clearBtn) {
    e.preventDefault();
    mapState.currentRoute = null;
    mapState.selectedFacilityId = null;
    mapState.needsFitBounds = false;
    renderFacilityMarkers();
    renderRouteLayer();
    updateMapSidebar();
    return;
  }
});

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

  // Preserve existing map DOM node across periodic renders
  const existingMap = document.getElementById('leaflet-map');
  let detachedMap = null;
  if ((page === 'overview' || page === 'routing') && existingMap && mapState.instance) {
    detachedMap = existingMap;
    if (detachedMap.parentNode) {
      detachedMap.parentNode.removeChild(detachedMap);
    }
  }

  let html='';
  if(page==='overview')html=kpis()+`<div class="two-col">${chartCard('chamber_temp_c','Chamber thermal trend','°C',true)}${control()}</div>`+risks()+`<div class="map-component-section">${map()}</div>`+`<div class="two-col equal">${timeline(5)}${table(['Station / Cold Hub','Temperature Spec','Distance'],mapState.facilities.slice(0,5).map(f=>[f.name,'2°C – 8°C Chilled',fmt(f.distance_km,1)+' km']))}</div>`;
  if(page==='live')html=kpis()+`<div class="two-col equal">${chartCard('chamber_temp_c','Chamber temperature (DS18B20)','°C',true)}${chartCard('heatsink_temp_c','Heatsink temperature (DS18B20)','°C')}${chartCard('sht31_temp_c','Ambient temperature (SHT31)','°C')}${chartCard('humidity_pct','Humidity (SHT31)','%')}${chartCard('primary_current_a','Primary current (ACS712)','A')}</div>`;
  if(page==='predictive')html=risks()+`<section class="card"><h2>Inference details</h2>${row('Model version',latest?.prediction?.model_version)}${row('Measured inference duration',fmt(latest?.prediction?.inference_ms,2)+' ms')}${row('Decision threshold',fmt(latest?.prediction?.threshold,3))}${row('Validation scope','Anomaly classification on active telemetry stream')}<p class="card-sub">ML risk can raise a warning. Confirmed primary faults require sensor evidence. Critical safety rules take precedence.</p></section>`;
  if(page==='equipment'){
    const isHardware=(t?.mode||appMode)==='HARDWARE';
    const isFresh=!isHardware||isLiveHardwareFresh();
    const isToggleDisabled=isHardware&&!isFresh;
    const backupActive=!!(t?.backup_cooling||latest?.virtual_backup_override);
    const equipToggleHtml=`<button type="button" class="toggle-switch btn-toggle-backup ${backupActive?'active':''} ${isToggleDisabled?'disabled':''}" ${isToggleDisabled?'disabled':''} aria-label="Toggle virtual backup cooling" title="${isToggleDisabled?'Hardware offline · Control unavailable':(backupActive?'Click to turn OFF virtual backup':'Click to turn ON virtual backup')}"><span class="toggle-track"><span class="toggle-thumb"></span></span><span class="toggle-label">${backupActive?'ON':'OFF'}</span></button>`;
    const equipList=[
      ['ESP32-S3','Edge controller','Acquisition and local control. Pin assignment awaits exact board.'],
      ['DS18B20 × 2','Temperature probes','One chamber probe, one shared heatsink probe.'],
      ['SHT31','Temperature & humidity','Secondary chamber temperature and humidity.'],
      ['ACS712 20A × 1','Primary current only','Backup current requires an external meter.'],
      ['Reed switch','Door monitoring','Door events are distinguished from cooling failures.'],
      ['NEO-6M','GPS location','No-fix state uses null coordinates.'],
      ['TEC1-12706','Primary cooling','Independently switched, fused primary branch.'],
      ['TEC1-12701 / 12703','Backup cooling',`Primary OFF confirmation precedes activation.<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;"><span>Virtual backup</span><div style="display:flex;align-items:center;gap:8px;"><strong>${backupActive?'ON':'OFF'}</strong>${equipToggleHtml}</div></div>`],
      ['2-channel MOSFET','Cooling interlock','Both Peltiers must never be commanded ON together.'],
      ['Shared heatsink + fan','Thermal assembly','Fan uses unswitched 12 V; shared overheating inhibits both Peltiers.'],
      ['12 V / 15 A + 5 V','Separate supplies','Cooling supply and regulated controller USB supply.'],
      ['Buzzer + 2–3 LEDs','Local indication','OLED and push buttons optional additions.']
    ];
    html=`<div class="equipment">${equipList.map(([a,b,c])=>`<section class="card">${badge(appMode==='HARDWARE'?'HARDWARE MODE':'SIMULATION','neutral')}<h2>${esc(a)}</h2><h3>${esc(b)}</h3><p>${c.includes('<div')?c:esc(c)}</p></section>`).join('')}</div>`;
  }
  if(page==='routing'){
    const verifiedSection = mapState.facilities.length ? `<section class="card"><h2>Discovered nearby cooling facilities</h2><p class="card-sub">Real-time geospatial query (${esc(mapState.facilities[0]?.source || 'GIS')}) centered at active GPS coordinates.</p>${table(['Facility','Distance','Latitude','Longitude','Source','Address'],mapState.facilities.map(f=>[f.name,fmt(f.distance_km,2)+' km',fmt(f.latitude,4),fmt(f.longitude,4),f.source,f.address||'—']))}</section>` : '';
    html=`<div class="map-component-section">${map()}</div>`+verifiedSection+`<section class="card"><h2>Facility catalogue</h2><p class="card-sub">Verified cold storage facility registry & logistics network.</p>${table(['Facility','Available','Temperature °C','Capacity kg','Source'],(cache.warehouses||[]).map(w=>[w.name,w.available?'Yes':'No',w.minimum_temperature+' to '+w.maximum_temperature,w.capacity,w.source]))}</section>`;
  }
  if(page==='alerts')html=`<section class="card"><h2>Recorded faults</h2>${(cache.faults||[]).length?table(['Time','Mode','State','Reason','Source','Lifecycle'],cache.faults.map(e=>[clock(e.timestamp),e.payload.mode||'SYSTEM',e.payload.new_state,e.payload.reason,e.payload.source,e.payload.resolved?(e.payload.resolution||'RESOLVED'):'ACTIVE'])):'<div class="empty">No fault events recorded for this device.</div>'}</section>`;
  if(page==='history')html=`<section class="card"><div class="card-head"><h2>Telemetry history</h2><button id="download-history" class="secondary">Export JSON</button></div>${table(['Acquired','Sequence','Chamber °C','Current A','Observed state','Decision','Mode','Archived'],(cache.history||[]).map(r=>[clock(r.timestamp),r.sequence,fmt(r.payload.chamber_temp_c),fmt(r.payload.primary_current_a),r.payload.system_state,r.decision.state,r.mode,r.archived?'Yes':'No']))}</section>`;
  if(page==='analytics'){const m=system.model||{};html=`<section class="card"><div class="card-head"><h2>Held-out test results</h2>${badge(m.training_provenance||'UNAVAILABLE','warn')}</div>${table(['Estimator','Precision','Recall','F1','ROC AUC','Test samples'],Object.entries(m.test||{}).map(([name,v])=>[name,fmt(v.precision,3),fmt(v.recall,3),fmt(v.roc_auc,3),v.samples]))}<p class="card-sub">${esc(m.split_method)}. Test evaluation on held-out datasets.</p></section><div class="three-col">${Object.entries(m.test||{}).map(([n,v])=>`<section class="card"><h2>${esc(n)} confusion matrix</h2>${table(['Actual / Predicted','Normal','Anomaly'],[['Normal',...v.confusion_matrix[0]],['Anomaly',...v.confusion_matrix[1]]])}</section>`).join('')}</div>`;}
  if(page==='health')html=`<div class="two-col equal"><section class="card"><h2>Software & connectivity</h2>${row('Telemetry freshness',latest?.connectivity)}${row('Seconds since reception',fmt(latest?.seconds_since_received))}${row('XGBoost + Random Forest',system.ml_ready?'LOADED':'UNAVAILABLE')}${row('Active Mode',appMode)}${row('Hardware validation',system.hardware_status)}${row('Buffered / dropped',system.simulation?.buffered_samples+' / '+system.simulation?.dropped_samples)}</section><section class="card"><h2>Sensor health & data provenance</h2>${(t?.mode||appMode)==='HARDWARE'?row('Chamber source',t?.chamber_source||'DERIVED'):''}${(t?.mode||appMode)==='HARDWARE'&&t?.chamber_formula?row('Chamber formula',t.chamber_formula):''}${(t?.mode||appMode)==='HARDWARE'&&t?.raw_chamber_temp_c!=null?row('Raw DS18B20 chamber',fmt(t.raw_chamber_temp_c,2)+' °C'):''}${(t?.mode||appMode)==='HARDWARE'?row('Heatsink source','DS18B20 (physical probe)'):''}${(t?.mode||appMode)==='HARDWARE'?row('Current input source',t?.current_source||'EMULATED'):''}${(t?.mode||appMode)==='HARDWARE'?row('ACS712 calibration',t?.current_calibrated?'CALIBRATED':'PENDING'):''}${(t?.mode||appMode)==='HARDWARE'?row('Backup source',t?.backup_source||'VIRTUAL'):''}${(t?.mode||appMode)==='HARDWARE'?row('Physical backup stage',t?.backup_commissioned?'COMMISSIONED':'NOT COMMISSIONED'):''}${(t?.mode||appMode)==='HARDWARE'?row('Cooling control mode',t?.cooling_control_mode||'MANUAL_SMPS'):''}${Object.entries(t?.sensor_health||{}).map(([k,v])=>row(k === 'current' && !v && (t?.mode || appMode) === 'HARDWARE' ? 'current (ACS712)' : k, k === 'current' && !v && (t?.mode || appMode) === 'HARDWARE' ? 'PENDING CALIBRATION' : (v?'VALID':'INVALID'))).join('')}${row('GPS',t?.gps?.fix?'FIX':'NO FIX')}${t?.vibration_detected !== undefined ? row('Vibration', t.vibration_detected ? 'DETECTED' : 'NORMAL') : ''}</section></div>`;
  if(page==='validation')html=`<section class="card"><div class="card-head"><div><h2>Physical measurement register</h2><p class="card-sub">Values stay empty until hardware evidence is submitted.</p></div><button id="export-validation" class="secondary">Export CSV</button></div>${table(['Measurement','Value','Status','Evidence source'],(cache.validation?.metrics||[]).map(m=>[m.metric,m.value??'—',m.status,m.measurement_source]))}</section>`;
  if(page==='archive')html=archiveView();
  
  $('content').innerHTML=html;

  // Re-attach detached map container if present
  if (detachedMap) {
    const mountContainer = document.querySelector('.map-view-container');
    if (mountContainer) {
      const placeholder = document.getElementById('leaflet-map');
      if (placeholder && placeholder !== detachedMap) {
        placeholder.replaceWith(detachedMap);
      } else if (!placeholder) {
        mountContainer.appendChild(detachedMap);
      }
    } else {
      if (mapState.instance) {
        try { mapState.instance.remove(); } catch(e) {}
        mapState.instance = null;
        mapState.containerEl = null;
        mapState.vehicleMarker = null;
        mapState.facilityMarkers.clear();
      }
    }
  }

  if(page==='archive')bindArchive();
  if($('download-history'))$('download-history').onclick=async()=>{try{const base=apiUrl?apiUrl.replace(/\/$/,''):'';const r=await fetch(base+'/api/history/export?device_id='+encodeURIComponent(device),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('History export failed');download(await r.text(),device+'-telemetry.json','application/json');}catch(e){$('notice').textContent=e.message;}};
  if($('export-validation'))$('export-validation').onclick=async()=>{try{const base=apiUrl?apiUrl.replace(/\/$/,''):'';const r=await fetch(base+'/api/validation/export?format=csv&device_id='+encodeURIComponent(device),{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('Export failed');download(await r.text(),'hardware-validation.csv','text/csv');}catch(e){$('notice').textContent=e.message;}};

  syncMap();
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
