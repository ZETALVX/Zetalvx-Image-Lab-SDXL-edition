/* Destructive action requires explicit plan, one-time word and two password entries.
   Never treats a dropped connection as confirmed successful removal. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id),t=s=>window.ZI18n?.t(s)||s;
 if(!by('appUninstallPanel'))return;
 let csrf='',plan=null,challenge=null,busy=false,accepted=false,lastFocus=null;
 const fields=['uninstallWordInput','uninstallPassword','uninstallPasswordRepeat'];
 function erase(){fields.forEach(id=>by(id).value='');by('uninstallUnderstand').checked=false;}
 function warning(purge){return t(purge?'PERMANENT REMOVAL: app, runtimes, account, models and all data inside the default app folder will be deleted. External paths are preserved.':'REMOVE APP ONLY: app, runtimes and shortcuts will be removed. Your models, images, training, presets and account will remain.');}
 function controls(){
  const ready=!!challenge&&by('uninstallWordInput').value.trim()===challenge.word&&by('uninstallUnderstand').checked&&by('uninstallPassword').value.length>0&&by('uninstallPassword').value===by('uninstallPasswordRepeat').value;
  by('uninstallConfirm').disabled=busy||!ready||accepted;by('uninstallPrepare').disabled=busy||accepted;
  by('uninstallClose').disabled=busy;by('uninstallPurge').disabled=busy||accepted||(plan&&plan.can_purge_data===false);
  by('uninstallScope').textContent=warning(by('uninstallPurge').checked);
 }
 async function request(path,options={}){
  const res=await fetch('/api/app-uninstall'+path,{...options,credentials:'same-origin',cache:'no-store',headers:{'X-CSRF-Token':csrf,...options.headers}});
  let d;try{d=await res.json();}catch(_){throw Error(t('The connection was interrupted. Do not repeat uninstall blindly. Check the host before retrying.'));}
  if(!res.ok)throw Error(t(d.error||'Uninstall request failed.'));return d;
 }
 function revoke(){if(!challenge)return;const id=challenge.id;challenge=null;request('/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({challenge_id:id})}).catch(()=>{});}
 function close(){if(busy||accepted)return;revoke();by('uninstallModal').classList.add('hidden');erase();challenge=null;by('uninstallConfirmError').textContent='';controls();lastFocus?.focus();}
 by('uninstallPurge').addEventListener('change',()=>{revoke();erase();controls();});
 by('uninstallPrepare').addEventListener('click',async()=>{
  if(busy||accepted)return;busy=true;controls();by('uninstallStatus').textContent='';
  try{
   const state=await request('');csrf=state.csrf;plan=state.plan;
   const d=await request('/challenge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({purge_data:by('uninstallPurge').checked})});
   challenge=d.challenge;plan=d.plan;erase();by('uninstallWord').textContent=challenge.word;
   by('uninstallWarning').textContent=warning(plan.purge_data);by('uninstallPath').textContent=plan.home;by('uninstallConfirmError').textContent='';
   lastFocus=document.activeElement;by('uninstallModal').classList.remove('hidden');by('uninstallWordInput').focus();
  }catch(e){by('uninstallStatus').textContent=e.message;challenge=null;}finally{busy=false;controls();}
 });
 by('uninstallForm').addEventListener('submit',async event=>{
  event.preventDefault();if(busy||accepted||by('uninstallConfirm').disabled)return;
  busy=true;controls();
  const payload={challenge_id:challenge.id,word:by('uninstallWordInput').value.trim(),purge_data:plan.purge_data,understand:by('uninstallUnderstand').checked,password:by('uninstallPassword').value,password_repeat:by('uninstallPasswordRepeat').value};
  by('uninstallPassword').value='';by('uninstallPasswordRepeat').value='';
  try{
   const d=await request('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   accepted=true;erase();challenge=null;by('uninstallModal').classList.add('hidden');
   by('uninstallBanner').textContent=t('Uninstall accepted. Zetalvx Image Lab is stopping. Do not restart it or submit the action again. A disconnection is expected; it does not confirm successful removal.')+'\n\n'+warning(!d.uninstall.data_preserved)+'\n\n'+t('Final result on the host:')+'\n'+d.uninstall.report+(d.uninstall.native_windows?'\n\n'+t('A separate uninstall window on the Windows host shows process shutdown, file removal and the verified final result.'): '');
   by('uninstallBanner').hidden=false;
  }catch(e){by('uninstallConfirmError').textContent=e.message+' '+t('Close and reopen this dialog for a new confirmation.');challenge=null;}
  finally{payload.password='';payload.password_repeat='';busy=false;controls();}
 });
 fields.forEach(id=>by(id).addEventListener('input',controls));by('uninstallUnderstand').addEventListener('change',controls);
 by('uninstallClose').addEventListener('click',close);
 by('uninstallModal').addEventListener('click',e=>{if(e.target===by('uninstallModal'))close();});
 window.addEventListener('keydown',e=>{if(by('uninstallModal').classList.contains('hidden'))return;if(e.key==='Escape')close();if(e.key==='Tab'){
  const nodes=[...by('uninstallModal').querySelectorAll('button:not(:disabled),input:not(:disabled)')];const i=nodes.indexOf(document.activeElement);
  if(e.shiftKey&&i<=0){e.preventDefault();nodes.at(-1)?.focus();}else if(!e.shiftKey&&i===nodes.length-1){e.preventDefault();nodes[0]?.focus();}
 }});
 window.addEventListener('languagechange',()=>{controls();if(plan)by('uninstallWarning').textContent=warning(plan.purge_data);});
 controls();
})();
