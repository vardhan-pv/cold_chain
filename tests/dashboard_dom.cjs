// Behaviour test in JSDOM, not a claim of real-browser visual verification.
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require(process.env.CC_JSDOM_PATH||'jsdom');
const root=path.resolve(__dirname,'..');
const base=process.env.CC_TEST_URL,token=process.env.CC_TEST_TOKEN;
const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
const dom=new JSDOM(fs.readFileSync(path.join(root,'dashboard/src/index.html'),'utf8'),
  {url:base+'/#overview',runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
const w=dom.window;w.fetch=(url,options)=>fetch(new URL(url,base),options);w.sessionStorage.setItem('cc_token',token);
const downloads=[];w.URL.createObjectURL=blob=>{downloads.push(blob);return 'blob:test';};w.URL.revokeObjectURL=()=>{};
w.HTMLAnchorElement.prototype.click=function(){};
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<120;i++){if(fn())return;await wait(50);}throw Error('Timed out: '+label);}
async function run(){
  w.eval(fs.readFileSync(path.join(root,'dashboard/src/app.js'),'utf8'));
  await until(()=>w.document.querySelector('#content .kpis'),'initial API render');
  assert.equal(w.document.getElementById('login').hidden,true);
  const checks=[];
  for(const id of ['overview','live','predictive','healing','equipment','routing','alerts','history','analytics','health','validation','archive']){
    w.location.hash='#'+id;await wait(40);
    assert(w.document.getElementById('content').textContent.trim().length>20);
    assert(w.document.querySelector(`a[data-page="${id}"]`).classList.contains('active'));
    assert(!/NaN|undefined/.test(w.document.getElementById('content').textContent));
    checks.push(id);
  }
  assert(w.document.getElementById('content').textContent.includes('103'));
  w.document.getElementById('archive-next').click();
  await until(()=>w.document.getElementById('content').textContent.includes('51–100 of 103'),'archive pagination');
  w.document.getElementById('archive-export').click();
  await until(()=>downloads.length===1,'complete archive export');
  w.location.hash='#validation';await wait(40);
  assert(w.document.getElementById('content').textContent.includes('PENDING_HARDWARE'));
  w.document.getElementById('export-validation').click();
  await until(()=>downloads.length===2,'CSV export');
  w.location.hash='#history';await wait(40);
  w.document.getElementById('download-history').click();
  await until(()=>downloads.length===3,'complete telemetry export');
  w.document.getElementById('scenario').value='normal';w.document.getElementById('start').click();
  await until(()=>!w.document.getElementById('start').disabled,'simulation start');
  assert(w.document.getElementById('device').value.startsWith('CCU-SIM-'));
  w.document.getElementById('scenario').value='overheat';w.document.getElementById('apply').click();
  await until(()=>!w.document.getElementById('apply').disabled,'scenario applied');
  w.location.hash='#healing';
  await until(()=>w.document.getElementById('content').textContent.includes('CRITICAL FAILURE')||
    w.document.getElementById('content').textContent.includes('REROUTING'),'fault timeline update');
  assert(w.document.getElementById('content').textContent.includes('Control command lifecycle'));
  assert.equal(w.document.getElementById('notice').textContent,'');
  w.document.getElementById('pause').click();await until(()=>!w.document.getElementById('pause').disabled,'pause');
  assert.equal(errors.length,0,errors.join('\n'));
  const report={status:'PASS',environment:'JSDOM against live FastAPI HTTP server',pages:checks,
    actions:['authenticated API render','new simulation','fault injection','live fault timeline','command lifecycle','pause','CSV export','archive pagination','complete archive export','complete telemetry export'],
    errors,visual_browser_verification:'PENDING_ENVIRONMENT_ACCESS'};
  fs.writeFileSync(path.join(root,'docs/evidence/dashboard-dom.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));dom.window.close();
}
run().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
