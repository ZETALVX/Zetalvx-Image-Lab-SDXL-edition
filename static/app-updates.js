/* Local full-ZIP updates. Import is inert; execution is a separate reauthenticated action. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id),t=(s,v)=>window.ZI18n?.t(s,v)||s;
 if(!by('appUpdatesPanel'))return;
 let csrf='',state=null,version='',available=false,rollback=null,busy=false,rollbackBusy=false,polling=false,timer=0,inFlight=false;
 function message(text,error=false){by('appUpdateStatus').textContent=text;by('appUpdateStatus').classList.toggle('is-error',error);}
 function statusLabel(status){return t({ready:'ZIP checked; awaiting your confirmation.',starting:'Starting the updater…',running:'Checks and installation in progress…',completed:'Update completed. Reload the app.',failed:'Update failed. Read the log before retrying.',interrupted:'Update interrupted. Check the host and log.',discarded:'ZIP discarded; installed version unchanged.'}[status]||'');}
 async function request(path,options={}){
  const res=await fetch('/api/app-updates'+path,{credentials:'same-origin',cache:'no-store',...options,headers:{...(options.headers||{}),'X-CSRF-Token':csrf}});
  let d;try{d=await res.json();}catch(_){throw Error(t('The server is restarting or unavailable. Waiting to reconnect…'));}
  if(!res.ok)throw Error(d.error||t('Update request failed.'));return d;
 }
 function controls(){
  const active=state&&['starting','running'].includes(state.status),ready=state?.status==='ready';
  by('appUpdateImportFields').hidden=!!ready||!!active;
  by('appUpdateReview').hidden=!ready;
  by('appUpdateImport').disabled=busy||!available||!!active||!by('appUpdateFile').files.length;
  by('appUpdateStart').disabled=busy||!ready||!by('appUpdateTrust').checked||!by('appUpdatePassword').value;
  by('appUpdateDiscard').disabled=busy;
  by('appUpdateRefresh').disabled=busy;
  by('appUpdateRunningHelp').hidden=!active;
  by('appUpdateReload').hidden=state?.status!=='completed';
  by('appUpdateBanner').hidden=!active;
  by('appUpdateBanner').textContent=active?t('App update in progress. Data changes are temporarily paused.'):'';
  by('appRollbackPanel').hidden=!rollback?.available;
  by('appRollbackStart').disabled=busy||rollbackBusy||active||!rollback?.available||!by('appRollbackPassword').value;
 }
 function render(){
  by('appUpdateCurrent').textContent=version?t('Installed version: {v}',{v:version}):'';
  by('appRollbackInfo').textContent=rollback?.previous?t('Previous version: {v}',{v:rollback.previous}):'';
  if(state){
   by('appUpdateInfo').textContent=[t('Version')+': '+state.version,t('Platform')+': '+state.platform,
      `${state.files} `+t('verified files'),t('SHA-256')+': '+state.sha256,
      t('Unsigned package. Check its source.')].join('\n');
   message(statusLabel(state.status),['failed','interrupted'].includes(state.status));
   by('appUpdateLog').textContent=state.log_tail||'';by('appUpdateLogPanel').hidden=!state.log_tail;
  }else{by('appUpdateLogPanel').hidden=true;}
  controls();
 }
 async function refresh(){
  if(inFlight)return;inFlight=true;
  try{
   const data=await request('');csrf=data.csrf||csrf;state=data.update;version=data.version;available=!!data.available;rollback=data.rollback||null;
   polling=!!state&&['starting','running'].includes(state.status);render();
   if(!available)message(data.reason||t('Install the app before using GUI updates.'),true);
  }catch(e){if(polling)message(t('The server is restarting or unavailable. Waiting to reconnect…'));else message(e.message,true);}
  finally{inFlight=false;clearTimeout(timer);if(polling)timer=setTimeout(refresh,2500);}
 }
 by('appUpdateFile').addEventListener('change',controls);
 by('appUpdateTrust').addEventListener('change',controls);by('appUpdatePassword').addEventListener('input',controls);by('appRollbackPassword').addEventListener('input',controls);
 by('appUpdateRefresh').addEventListener('click',refresh);
 by('appUpdateImport').addEventListener('click',async()=>{
  if(busy)return;const file=by('appUpdateFile').files[0];if(!file)return;
  if(file.size>128*1024*1024){message(t('Update ZIP exceeds 128 MiB'),true);return;}
  busy=true;controls();message(t('Uploading and checking the ZIP. No installation has started.'));
  try{
   if(!csrf)await refresh();const body=new FormData();body.append('file',file);body.append('sha256',by('appUpdateExpectedHash').value.trim());
   const result=await request('/import',{method:'POST',body});state=result.update;
   by('appUpdateTrust').checked=false;by('appUpdatePassword').value='';by('appUpdateAllowRuntime').checked=false;
   by('appUpdateFile').value='';render();
  }catch(e){message(e.message,true);}finally{busy=false;controls();}
 });
 by('appUpdateStart').addEventListener('click',async()=>{
  if(busy||state?.status!=='ready'||!by('appUpdateTrust').checked)return;
  busy=true;controls();message(t('Starting the updater…'));
  const password=by('appUpdatePassword').value;by('appUpdatePassword').value='';
  try{
   const data=await request('/'+state.id+'/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({trust_source:true,password,allow_new_runtime:by('appUpdateAllowRuntime').checked})});
   state=data.update;polling=true;render();clearTimeout(timer);timer=setTimeout(refresh,1500);
  }catch(e){await refresh();if(!polling)message(e.message,true);}finally{busy=false;controls();}
 });
 by('appUpdateDiscard').addEventListener('click',async()=>{
  if(busy||!state)return;busy=true;controls();
  try{const result=await request('/'+state.id,{method:'DELETE'});state=result.update;render();}
  catch(e){message(e.message,true);}finally{busy=false;controls();}
 });
 by('appUpdateReload').addEventListener('click',()=>location.reload());
 by('appRollbackStart').addEventListener('click',async()=>{
  if(busy||rollbackBusy||!rollback?.available)return;
  const target=rollback.previous;if(!confirm(t('Rollback to version {v}? Finish or cancel active jobs first. The app will restart.',{v:target})))return;
  rollbackBusy=true;controls();by('appRollbackStatus').textContent='';
  const password=by('appRollbackPassword').value;by('appRollbackPassword').value='';
  try{
   await request('/rollback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
   by('appRollbackStatus').textContent=t('Rollback scheduled. The connection will briefly close; reload after the app restarts.');
  }catch(e){by('appRollbackStatus').textContent=e.message;by('appRollbackStatus').classList.add('is-error');}
  finally{rollbackBusy=false;controls();}
 });
 document.addEventListener('click',e=>{const button=e.target.closest('[data-view],[data-goto],[data-guide-view]');
  if(button&&(button.dataset.view||button.dataset.goto||button.dataset.guideView)==='settings')refresh();
 });
 window.addEventListener('languagechange',render);
 // One status read on load resumes observation after a browser refresh/restart.
 refresh();
})();
