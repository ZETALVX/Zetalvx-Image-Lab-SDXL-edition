// Modified in Zetalvx Image Lab — SDXL Edition 0.1.0.18; see BUILD_PROVENANCE.json.
/* Models hub + app settings. No tokens in S, localStorage, presets or project data. */
(()=>{
 'use strict';
 const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
 let hub=null,csrf='',preview=null,pollTimer=null,pollBusy=false,activeTab='installed';
 let target='',parent='',returnFocus=null;const dirty=new Set();const observedJobs=new Map();
 const modelFieldIds=['setupCheckpoint','setupCheckpointRoot','setupLoraRoot','setupInpaint','setupVae','setupIdentityRoot','setupIdentityVendor','hubInstantRoot','hubInsightRoot','hubSwapperFile','setupIdentityAck','hubInstantEnabled','hubSwapEnabled'];
 const txt=(id,value)=>{const el=$('#'+id);if(el)el.textContent=value??''};
 const tr=s=>window.ZI18n?.t(s)||s;
 const bytes=n=>{n=Number(n)||0;const units=['B','KiB','MiB','GiB'];let i=0;while(n>=1024&&i<3){n/=1024;i++}return `${n.toFixed(i>1?1:0)} ${units[i]}`};
 const message=(s,error=false,id='hubMessage')=>{txt(id,s);$('#'+id)?.classList.toggle('is-error',error)};
 function putValue(id,value){const e=$('#'+id);if(!e||dirty.has(id)||document.activeElement===e)return;if(e.type==='checkbox')e.checked=!!value;else e.value=value??'';}
 function badge(id,ready,disabled=false){const e=$('#'+id);if(!e)return;e.textContent=disabled?'Disabilitato':ready?'File presenti':'Da configurare';e.className='status-pill '+(ready&&!disabled?'online':'planned');}
 async function hubApi(path,options={}){
  if(options.method&&options.method!=='GET'){
   options.headers={...(options.headers||{}),'Content-Type':'application/json'};
   if(options.body===undefined)options.body='{}';
  }
  return api('/api/model-hub/'+path,options);
 }

 function tab(name){activeTab=name;$$('[data-hub-panel]').forEach(p=>p.hidden=p.dataset.hubPanel!==name);$$('[data-hub-tab]').forEach(b=>{const on=b.dataset.hubTab===name;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on))})}
 function openDetail(id){tab('installed');const el=$('#'+id);if(el){el.open=true;el.scrollIntoView({behavior:'smooth',block:'nearest'})}}
 async function refreshRegistry(d){
  if(!S.boot)return;
  S.boot.models=d.models||S.boot.models;S.boot.checkpoints=d.checkpoints||[];S.boot.loras=d.loras||[];
  if(typeof populateModelSelect==='function')populateModelSelect();
  if(typeof updateCheckpointControls==='function')updateCheckpointControls();
  if(typeof renderModels==='function')renderModels();
 }
 function fileGuide(label,state,path,files,source){
  const row=document.createElement('div');row.className='hub-guide-row';
  const head=document.createElement('div');head.className='hub-row';
  const title=document.createElement('b');title.textContent=label;head.append(title);
  const status=document.createElement('span');status.className='status-pill '+(state?'online':'planned');status.textContent=state?'File presenti':'Manca';head.append(status);row.append(head);
  const code=document.createElement('code');code.className='hub-path';code.textContent=path;row.append(code);
  const note=document.createElement('small');note.className='muted';note.textContent=files;row.append(note);
  const actions=document.createElement('div');actions.className='hub-inline';
  const link=document.createElement('a');link.href=source;link.textContent='Fonte ufficiale ↗';link.target='_blank';link.rel='noopener noreferrer';link.className='text-button';actions.append(link);
  const copy=document.createElement('button');copy.type='button';copy.className='text-button';copy.textContent='Copia percorso';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(path);copy.textContent='Copiato'}catch(_){message('Copia il percorso mostrato sopra.')}});actions.append(copy);row.append(actions);return row;
 }
 function accounts(data){for(const [p,id] of [['huggingface','hubHfState'],['civitai','hubCivitaiState']]){const a=data?.[p];txt(id,a?.stored?(a.account||'Token salvato'):'Non collegato')}}
 function renderHub(d){
  hub=d;csrf=d.csrf;const cfg=(d.models||[]).find(m=>m.id==='sdxl')?.config||{},st=d.settings||{},id=d.identity||{};
  for(const el of document.querySelectorAll('[data-model-default-path]')){el.textContent=d.paths?.[el.dataset.modelDefaultPath]||'—';}
  const asset=d.sdxl_assets||{}, install=d.base_installation||{}, missing=asset.missing_labels||[];
  const mark=(id,ready,detail='')=>{const el=$('#'+id);if(!el)return;el.textContent=ready?'✓ Presente':'✕ Manca';el.className=ready?'is-ready':'is-missing';if(detail)el.title=detail;};
  mark('hubSdxlCheckpointState',!!asset.checkpoint?.ready,asset.checkpoint?.path||'');
  mark('hubSdxlBaseConfigState',!!asset.base_config?.ready,(asset.base_config?.missing_files||[]).join(', '));
  mark('hubSdxlInpaintConfigState',!!asset.inpaint_config?.ready,(asset.inpaint_config?.missing_files||[]).join(', '));
  const running=['queued','running'].includes(install.status);
  const progress=$('#hubSdxlInstallProgress');if(progress){progress.max=Number(install.total||3);progress.value=Number(install.completed??asset.present_components??0);progress.hidden=asset.ready&&!running;}
  const imsg=$('#hubSdxlInstallMessage');if(imsg){
   let line=install.message||'';
   if(install.status==='interrupted')line='Download precedente interrotto. Premi “Scarica mancanti” per riprendere: i file già presenti vengono riusati.';
   if(install.status==='failed')line='Download non completato: '+(install.error||install.message||'controlla la rete e riprova.');
   if(asset.ready&&!running)line='Tutto pronto: checkpoint e configurazioni necessarie sono presenti.';
   imsg.textContent=line;imsg.classList.toggle('is-error',install.status==='failed');
  }
  if(asset.ready)txt('hubSdxlState','SDXL pronto · 3/3 componenti presenti');
  else txt('hubSdxlState',`SDXL incompleto · ${asset.present_components??0}/3 presenti${missing.length?' · manca: '+missing.join(', '):''}`);
  const checkBtn=$('#hubCheckBase');if(checkBtn){checkBtn.disabled=running;checkBtn.textContent=running?'Controllo…':'Controlla file';}
  const installBtn=$('#hubInstallBase');
  if(installBtn){
   installBtn.disabled=running||!!asset.ready;
   if(running)installBtn.textContent='Download in corso…';
   else if(asset.ready)installBtn.textContent='Tutto presente';
   else installBtn.textContent='Scarica mancanti';
  }
  const shortcut=$('#hubBaseShortcut');if(shortcut){shortcut.disabled=running||!!asset.ready;shortcut.textContent=asset.ready?'SDXL Base completo':'Completa SDXL Base 1.0';}
  const sel=$('#hubCheckpoint'),old=sel.value||cfg.checkpoint||'';
  sel.replaceChildren(new Option('Seleziona un checkpoint…',''));
  const seen=new Set();for(const c of d.checkpoints||[]){if(!seen.has(c.path)){sel.add(new Option(c.name,c.path));seen.add(c.path)}}
  if(cfg.checkpoint&&d.sdxl?.ready&&!seen.has(cfg.checkpoint))sel.add(new Option('Configurato · '+cfg.checkpoint.split('/').pop(),cfg.checkpoint));
  sel.value=[...sel.options].some(o=>o.value===old)?old:(cfg.checkpoint||'');
  txt('hubLoraCount',`${d.loras?.length||0} file disponibili`);txt('hubLoraFolder',st.lora_root||cfg.lora_root||d.paths?.lora);
  window.dispatchEvent(new CustomEvent('model-hub-updated',{detail:d}));
  for(const [field,key] of [['setupCheckpoint','checkpoint'],['setupCheckpointRoot','checkpoint_roots'],['setupLoraRoot','lora_root'],['setupInpaint','inpaint_checkpoint'],['setupVae','vae']])putValue(field,cfg[key]||'');
  for(const [field,key] of [['setupIdentityRoot','identity_root'],['setupIdentityVendor','vendor_root'],['hubInstantRoot','instantid_root'],['hubInsightRoot','insightface_root'],['hubSwapperFile','swapper_path']])putValue(field,id[key]||'');
  putValue('identityParentProbe',id.identity_root||st.identity_root||'');
  putValue('setupIdentityAck',id.license_acknowledged);putValue('hubInstantEnabled',id.instantid_enabled!==false);putValue('hubSwapEnabled',id.faceswap_enabled!==false);
  badge('hubInstantState',id.instantid_files_ready,id.instantid_enabled===false);badge('hubSwapState',id.face_swap_files_ready,id.faceswap_enabled===false);
  txt('hubCodeState',id.vendor_ready?'File codice presenti':'Codice non preparato');if(!$('#hubPrepareCode').disabled)$('#hubPrepareCode').textContent=id.vendor_ready?'Verifica codice':'Installa solo il codice';
  const guide=$('#hubIdentityGuide');guide.replaceChildren(
   fileGuide('Pesi InstantID',id.instantid_adapter_ready&&id.controlnet_config_ready&&id.controlnet_weights_ready,id.instantid_root,'Qui: ip-adapter.bin e ControlNetModel/ con config.json + diffusion_pytorch_model.safetensors.','https://huggingface.co/InstantX/InstantID'),
   fileGuide('Face encoder · antelopev2',id.instantid_face_pack_ready,id.instantid_face_pack_dir,'Estrai la cartella: i file .onnx devono essere direttamente qui, non dentro un’altra antelopev2/.','https://github.com/instantX-research/InstantID#download'),
   fileGuide('Face analysis · buffalo_l',id.swap_face_pack_ready,id.swap_face_pack_dir,'Estrai i file .onnx direttamente qui. Serve per Face Swap.','https://github.com/deepinsight/insightface#license'),
   fileGuide('Modello Face Swap',id.swapper_ready,id.swapper_path,'Qui serve il singolo file inswapper_128.onnx, non una cartella o uno ZIP.','https://github.com/deepinsight/insightface#license')
  );
  txt('hubCodeCurrentPath',id.vendor_root||'');
  txt('hubCodePathWarning',id.vendor_points_to_weights?'Il percorso codice punta ai pesi. Installa il codice: i pesi rimangono dove sono.':'Codice Python separato dai pesi. L’installazione usa una cartella gestita dall’app.');
  accounts(d.accounts);renderDownloads(d.jobs||[]);

 }
 let sdxlBasePollBusy=false;
 function scheduleBasePoll(){
  if(window.__sdxlBasePollTimer)return;
  const tick=async()=>{
   if(sdxlBasePollBusy)return;sdxlBasePollBusy=true;
   try{
    const d=await hubApi('status');renderHub(d);
    if(!['queued','running'].includes((d.base_installation||{}).status)){
      if(window.__sdxlBasePollTimer)clearInterval(window.__sdxlBasePollTimer);window.__sdxlBasePollTimer=null;
      await refreshRegistry(d);
    }
   }catch(e){message(e.message,true)}finally{sdxlBasePollBusy=false}
  };
  window.__sdxlBasePollTimer=setInterval(tick,1200);tick();
 }
 async function refreshHub({registry=false}={}){try{const d=await hubApi('status');renderHub(d);if(['queued','running'].includes((d.base_installation||{}).status))scheduleBasePoll();if(registry)await refreshRegistry(d)}catch(e){message(e.message,true)}}
 async function busy(button,action){if(button?.disabled)return;const old=button?.textContent;if(button){button.disabled=true;button.textContent='Attendi…'}try{await action()}catch(e){message(e.message,true)}finally{if(button){button.disabled=false;button.textContent=old}}}
 function showPreview(p){preview=p;$('#hubPreview').hidden=false;txt('hubPreviewName',p.filename);txt('hubPreviewMeta',`${p.size?bytes(p.size):'Dimensione da verificare'} · ${p.kind==='auto'?'Tipo da rilevare':p.kind} · ${p.license}`);$('#hubPreviewSource').href=p.license_url||p.source;$('#hubAcceptTerms').checked=false;$('#hubPreview').scrollIntoView({block:'nearest',behavior:'smooth'})}
 async function inspect(builtin=false){
  tab('add');message('Controllo della fonte…');$('#hubPreview').hidden=true;preview=null;
  const d=await hubApi('inspect',{method:'POST',body:JSON.stringify(builtin?{package:'sdxl_base'}:{url:$('#hubUrl').value.trim(),kind:$('#hubKind').value,filename:$('#hubFilename').value.trim()})});showPreview(d.preview);message('Verifica la fonte e conferma per iniziare.');
 }
 function statusLabel(s){return ({queued:'In coda',downloading:'Download',validating:'Verifica file',installing:'Installazione',needs_confirmation:'Conferma necessaria',complete:'Completato',failed:'Non riuscito',cancelled:'Annullato',cancelling:'Annullamento…',interrupted:'Interrotto dal riavvio'})[s]||s}
 function renderDownloads(jobs){
  $('#hubDownloadsPanel').hidden=!jobs.length;const box=$('#hubDownloads');
  for(const j of jobs){
   let row=box.querySelector(`[data-download-id="${j.id}"]`);
   if(!row){
    row=document.createElement('div');row.className='hub-download-row';row.dataset.downloadId=j.id;
    row.innerHTML='<div class="hub-row"><b class="download-title"></b><span class="download-state"></span><button type="button" class="text-button download-cancel">Annulla</button></div><progress max="100"></progress><small class="download-info"></small><div class="download-confirm" hidden><label>Tipo del file<select><option value="checkpoint">Checkpoint SDXL</option><option value="lora">LoRA SDXL</option><option value="vae">VAE</option></select></label><button type="button" class="ghost">Conferma compatibilità e installa</button></div>';
    row.querySelector('.download-cancel').onclick=e=>busy(e.currentTarget,async()=>{await hubApi(`downloads/${j.id}/cancel`,{method:'POST'});await pollDownloads()});
    row.querySelector('.download-confirm button').onclick=e=>busy(e.currentTarget,async()=>{const kind=row.querySelector('select').value;if(!confirm('Hai verificato sulla fonte che il file sia compatibile con SDXL e utilizzabile secondo i suoi termini?'))return;await hubApi(`downloads/${j.id}/install`,{method:'POST',body:JSON.stringify({kind,accept_unknown:true})});await refreshHub({registry:true})});
    box.append(row);
   }
   row.querySelector('.download-title').textContent=j.filename||'Modello';row.querySelector('.download-state').textContent=statusLabel(j.status);
   const bar=row.querySelector('progress');if(j.total_bytes)bar.value=Math.min(100,(j.downloaded_bytes||0)/j.total_bytes*100);else bar.removeAttribute('value');
   bar.hidden=!['queued','downloading','validating','installing','cancelling'].includes(j.status);
   row.querySelector('.download-info').textContent=j.error||j.warning||(j.path?'Salvato in '+j.path:(j.total_bytes?`${bytes(j.downloaded_bytes)} / ${bytes(j.total_bytes)}`:''));
   row.querySelector('.download-confirm').hidden=j.status!=='needs_confirmation';
   row.querySelector('.download-cancel').hidden=!['queued','downloading','validating','needs_confirmation','cancelling'].includes(j.status);
   row.querySelector('.download-cancel').disabled=j.status==='cancelling';
   const old=observedJobs.get(j.id);observedJobs.set(j.id,j.status);
   if(old&&old!==j.status&&j.status==='complete')setTimeout(()=>refreshHub({registry:true}),30);
  }
  const active=jobs.some(j=>['queued','downloading','validating','installing','cancelling'].includes(j.status));
  if(active&&!pollTimer)pollTimer=setInterval(pollDownloads,1500);if(!active&&pollTimer){clearInterval(pollTimer);pollTimer=null}
 }
 async function pollDownloads(){if(pollBusy)return;pollBusy=true;try{const d=await hubApi('downloads');renderDownloads(d.jobs)}catch(e){message(e.message,true)}finally{pollBusy=false}}
 async function saveSdxl(){const d={sdxl:{}};for(const [field,key] of [['setupCheckpoint','checkpoint'],['setupCheckpointRoot','checkpoint_roots'],['setupLoraRoot','lora_root'],['setupInpaint','inpaint_checkpoint'],['setupVae','vae']])d.sdxl[key]=$('#'+field).value.trim();await api('/api/setup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});['setupCheckpoint','setupCheckpointRoot','setupLoraRoot','setupInpaint','setupVae'].forEach(x=>dirty.delete(x));message('Percorsi SDXL salvati.',false,'hubSdxlSaveStatus');await refreshHub({registry:true})}
 async function saveIdentity(){const d={identity_root:$('#setupIdentityRoot').value.trim(),identity_vendor:$('#setupIdentityVendor').value.trim(),identity_instantid_root:$('#hubInstantRoot').value.trim(),identity_insightface_root:$('#hubInsightRoot').value.trim(),identity_swapper_model:$('#hubSwapperFile').value.trim(),identity_instantid_enabled:$('#hubInstantEnabled').checked,identity_faceswap_enabled:$('#hubSwapEnabled').checked,identity_license_acknowledged:$('#setupIdentityAck').checked};const old=hub?.settings||{};if(d.identity_root!==old.identity_root){for(const [f,relative] of [['identity_instantid_root','InstantID'],['identity_insightface_root','insightface'],['identity_swapper_model','inswapper_128.onnx']])if(d[f]===old[f])delete d[f];}await api('/api/setup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});['setupIdentityRoot','setupIdentityVendor','hubInstantRoot','hubInsightRoot','hubSwapperFile','setupIdentityAck','hubInstantEnabled','hubSwapEnabled'].forEach(x=>dirty.delete(x));message('Salvato. I nuovi percorsi saranno applicati prima del prossimo lavoro Identity. Puoi anche usare Applica al worker nel rapporto percorsi.',false,'hubIdentitySaveStatus');await refreshHub()}
 async function loadSettings(){try{const d=await api('/api/setup');const saved=d.settings.host==='0.0.0.0'?'lan':'local',effective=d.effective_host==='0.0.0.0'?'lan':'local';putValue('setupNetwork',saved);txt('setupStatus',`SDXL: ${d.image_runtime.ok?'online':'offline'} · Identity: ${d.identity_runtime.online?'online':'offline'} · Training: ${d.training_runtime.ok?'online':'offline'}`);let net=`Salvato: ${saved==='lan'?'LAN':'solo questo PC'} · Attivo ora: ${effective==='lan'?'LAN':'solo questo PC'}`;if(saved!==effective)net+=' · Riavvio necessario per applicare la modifica.';if(effective==='lan'&&d.lan_ip)net+=` · URL LAN: https://${d.lan_ip}:${d.settings.port}`;txt('networkLiveStatus',net);renderFirewall(d.firewall,saved,d.platform);renderDesktopShortcut(d.desktop_shortcut);const a=await api('/api/account');putValue('accountUsername',a.username);txt('accountStatus','Account locale attivo.')}catch(e){txt('setupStatus',e.message)}}
 function renderFirewall(fw,saved,platform){const card=$('#networkFirewallCard'),status=$('#networkFirewallStatus'),button=$('#networkFirewallFix');if(!card)return;const visible=platform==='windows'&&saved==='lan';card.hidden=!visible;if(!visible)return;const blocks=(fw?.conflicting_blocks||[]).length;if(fw?.needs_fix){status.textContent=blocks?`Rilevate ${blocks} regole Windows che bloccano il processo dell’app. Configurazione richiesta.`:tr('Windows Firewall non è ancora configurato per la LAN.');button.hidden=false}else{status.textContent='Windows Firewall configurato per TCP '+(fw?.port||8298)+' sulla rete locale.';button.hidden=true}}
 function renderDesktopShortcut(d={}){const add=$('#desktopShortcutAdd'),remove=$('#desktopShortcutRemove'),status=$('#desktopShortcutStatus');if(!add)return;const on=!!d.enabled;add.hidden=on;remove.hidden=!on;if(status)status.textContent=on?(tr('Collegamento presente')+(d.path?' · '+d.path:'')):tr('Nessun collegamento Desktop creato.')}
 async function setDesktopShortcut(enabled,button){button.disabled=true;try{const d=await api('/api/desktop-shortcut',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});renderDesktopShortcut(d.shortcut)}catch(e){txt('desktopShortcutStatus',e.message)}finally{button.disabled=false}}
 async function configureFirewall(){const b=$('#networkFirewallFix');if(!b)return;b.disabled=true;txt('networkFirewallStatus',tr('Controllo Windows Firewall…'));try{let d=await api('/api/network/firewall');const blocks=d.firewall?.conflicting_blocks||[];let disable=false;let message='Windows richiederà l’autorizzazione amministratore per consentire Zetalvx Image Lab sulla porta 8298 solo dalla rete locale.';if(blocks.length){message+=`\n\nSono state rilevate ${blocks.length} regole Block per il processo Python che ospita Zetalvx Image Lab. Una regola Block prevale sull’autorizzazione della porta. Disabilitarle può consentire connessioni anche ad altre applicazioni che usano lo stesso Python. Verrà salvato un registro per il ripristino controllato. Vuoi disabilitare solo queste regole in conflitto?`;if(!confirm(message)){txt('networkFirewallStatus',tr('Configurazione annullata. Le regole Block restano attive.'));return}disable=true}else if(!confirm(message+'\n\nContinuare?'))return;d=await api('/api/network/firewall/configure',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({disable_conflicts:disable})});renderFirewall(d.firewall,'lan','windows');txt('networkFirewallStatus',d.message||tr('Windows Firewall configurato.'))}catch(e){txt('networkFirewallStatus',e.message)}finally{b.disabled=false}}
 // File picker is for the Linux server's filesystem, never for files on the phone.
 async function browse(path=''){try{const d=await api('/api/setup/browse?path='+encodeURIComponent(path));parent=d.parent;$('#browserPath').value=d.path;$('#browserEntries').replaceChildren();for(const en of d.entries){const b=document.createElement('button');b.type='button';b.textContent=(en.directory?'▸ ':'')+en.name;b.onclick=()=>en.directory?browse(en.path):choose(en.path);$('#browserEntries').append(b)}}catch(e){$('#browserEntries').textContent=e.message}}
 function choose(path){const field=$('#'+target);field.value=path;dirty.add(target);field.dispatchEvent(new Event('input',{bubbles:true}));closeBrowser()}
 function closeBrowser(){$('#fileBrowser').classList.add('hidden');returnFocus?.focus()}
 $$('[data-browse]').forEach(b=>b.addEventListener('click',()=>{target=b.dataset.browse;returnFocus=b;$('#fileBrowser').classList.remove('hidden');let initial=$('#'+target)?.value||'';if(/\.(safetensors|bin|onnx|json)$/i.test(initial))initial=initial.slice(0,initial.lastIndexOf('/'));browse(initial);$('#browserPath').focus()}));
 $('#browserClose').onclick=closeBrowser;$('#browserGo').onclick=()=>browse($('#browserPath').value);$('#browserUp').onclick=()=>browse(parent);$('#browserSelectDir').onclick=()=>choose($('#browserPath').value);
 $$('[data-hub-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.hubTab));$$('[data-hub-open]').forEach(b=>b.onclick=()=>openDetail(b.dataset.hubOpen));
 $$('[data-hub-import]').forEach(b=>b.onclick=()=>{tab('add');$('#hubKind').value=b.dataset.hubImport;$('#hubUrl').focus()});
 $('#hubRefresh').onclick=e=>busy(e.currentTarget,()=>refreshHub({registry:true}));
 $('#hubCheckBase').onclick=async e=>{
  const b=e.currentTarget;if(b.disabled)return;b.disabled=true;const old=b.textContent;b.textContent='Controllo…';
  try{await hubApi('sdxl-base-check',{method:'POST',body:'{}'});await refreshHub({registry:true});message('Controllo SDXL completato.');}
  catch(err){message(err.message,true)}finally{b.disabled=false;b.textContent=old}
 };
 async function startSdxlCompletion(button){
  if(button?.disabled)return;
  try{
   const r=await hubApi('sdxl-base-install',{method:'POST',body:'{}'});renderHub({...hub,base_installation:r.installation,sdxl_assets:r.installation?.assets||hub?.sdxl_assets});
   message(r.installation?.message||'Download dei componenti mancanti avviato.');
   if(['queued','running'].includes(r.installation?.status))scheduleBasePoll();else await refreshHub({registry:true});
  }catch(err){message(err.message,true);await refreshHub()}
 }
 $('#hubInstallBase').onclick=e=>startSdxlCompletion(e.currentTarget);
 $('#hubBaseShortcut').onclick=e=>startSdxlCompletion(e.currentTarget);
 $('#hubInspect').onclick=e=>busy(e.currentTarget,()=>inspect());
 $('#hubStartDownload').onclick=e=>busy(e.currentTarget,async()=>{if(!preview)throw new Error('Analizza prima il link.');if(!$('#hubAcceptTerms').checked)throw new Error('Verifica i termini della fonte e seleziona la conferma.');await hubApi('downloads',{method:'POST',body:JSON.stringify({preview_id:preview.id,accept_terms:true})});preview=null;$('#hubPreview').hidden=true;message('Download aggiunto alla coda. Puoi seguirlo nella scheda Download.');window.ZetalvxDownloadManager?.refresh();await pollDownloads()});
 $('#hubUseCheckpoint').onclick=e=>busy(e.currentTarget,async()=>{const path=$('#hubCheckpoint').value;if(!path)throw new Error('Scegli un checkpoint.');await hubApi('select',{method:'POST',body:JSON.stringify({kind:'checkpoint',path})});await refreshHub({registry:true});message('Checkpoint selezionato.')});
 $('#hubSaveSdxl').onclick=e=>busy(e.currentTarget,saveSdxl);$('#hubSaveIdentity').onclick=e=>busy(e.currentTarget,saveIdentity);
 $('#hubPrepareCode').onclick=async()=>{
  const b=$('#hubPrepareCode');if(b.disabled)return;
  b.disabled=true;
  try{
   // Installation never saves a model directory as a code directory.
   const r=await api('/api/setup/identity-prepare-code',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
   renderCodeInstall(r.installation);scheduleCodePoll();
  }catch(e){txt('hubCodeInstallStatus',e.message);$('#hubCodeInstallStatus')?.classList.add('is-error');b.disabled=false}
 };

 $('#hubCreateFolders').onclick=e=>busy(e.currentTarget,async()=>{await saveIdentity();await api('/api/setup/identity-create-layout',{method:'POST'});await refreshHub();message('Cartelle preparate. I pesi non vengono scaricati.',false,'hubIdentitySaveStatus')});
 $('#hubCheckFiles').onclick=e=>busy(e.currentTarget,()=>refreshHub());
 $$('[data-link-pack]').forEach(b=>b.onclick=e=>busy(e.currentTarget,async()=>{const pack=b.dataset.linkPack,path=$(pack==='antelopev2'?'#hubAntelopeFolder':'#hubBuffaloFolder').value;await saveIdentity();await api('/api/setup/link-face-pack/'+pack,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});await refreshHub();message('Cartella collegata. I percorsi vengono riletti prima del prossimo lavoro Identity.',false,'hubIdentitySaveStatus')}));
 $$('[data-account-save]').forEach(b=>b.onclick=e=>busy(e.currentTarget,async()=>{const provider=b.dataset.accountSave,input=$(provider==='huggingface'?'#hubHfToken':'#hubCivitaiToken');const d=await hubApi('accounts/'+provider,{method:'PUT',body:JSON.stringify({token:input.value.trim(),store_without_test:$('#hubSkipTokenTest').checked})});input.value='';accounts(d.accounts);message('Token salvato sul server. Nessuna password della piattaforma viene richiesta.')}));
 $$('[data-account-delete]').forEach(b=>b.onclick=e=>busy(e.currentTarget,async()=>{const d=await hubApi('accounts/'+b.dataset.accountDelete,{method:'DELETE'});accounts(d.accounts);message('Token rimosso dall’app. Per revocarlo completamente usa anche le impostazioni della piattaforma.')}));
 $('#setupRefresh').onclick=loadSettings;$('#setupSave').onclick=e=>busy(e.currentTarget,async()=>{const mode=$('#setupNetwork').value;await api('/api/setup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({network_mode:mode})});dirty.delete('setupNetwork');txt('setupStatus','Accesso salvato. Riavvia l’app per applicarlo.');await loadSettings();if(mode==='lan'&&!$('#networkFirewallCard')?.hidden&&confirm(tr('Accesso LAN salvato. Vuoi controllare e configurare Windows Firewall adesso?')))await configureFirewall()});
 $('#networkFirewallFix')?.addEventListener('click',configureFirewall);$('#desktopShortcutAdd')?.addEventListener('click',e=>setDesktopShortcut(true,e.currentTarget));$('#desktopShortcutRemove')?.addEventListener('click',e=>setDesktopShortcut(false,e.currentTarget));
 $('#accountSave').onclick=e=>busy(e.currentTarget,async()=>{try{const d={username:$('#accountUsername').value,current_password:$('#accountCurrentPassword').value,new_password:$('#accountNewPassword').value,confirm_password:$('#accountConfirmPassword').value};const r=await api('/api/account',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});txt('accountStatus',r.message);for(const id of ['accountCurrentPassword','accountNewPassword','accountConfirmPassword'])$('#'+id).value='';csrf='';dirty.delete('accountUsername');await refreshHub()}catch(err){txt('accountStatus',err.message)}});
 document.addEventListener('input',e=>{if([...modelFieldIds,'setupNetwork','accountUsername'].includes(e.target.id))dirty.add(e.target.id)});
 async function appControl(action){const status=$('#appControlStatus'),btn=$('#app'+(action==='restart'?'Restart':'Stop'));if(!btn)return;const warning=action==='restart'?'Riavviare Zetalvx Image Lab? I lavori attivi possono essere interrotti.':'Chiudere Zetalvx Image Lab? La pagina diventerà irraggiungibile finché non riavvii l’app dall’icona o dal menu Applicazioni.';if(!confirm(warning))return;btn.disabled=true;if(status)status.textContent=action==='restart'?'Riavvio in corso…':'Chiusura in corso…';try{await api('/api/app-control/'+action,{method:'POST'});if(action==='stop'){if(status)status.textContent='App in chiusura. Per riaprirla usa il collegamento Zetalvx Image Lab.';return;}let attempts=0;const wait=()=>setTimeout(async()=>{attempts++;try{const r=await fetch('/api/health',{cache:'no-store',credentials:'same-origin'});if(r.ok){location.reload();return}}catch(_){}if(attempts<45)wait();else{btn.disabled=false;if(status)status.textContent='Riavvio non confermato. Avvia l’app dal collegamento e controlla i log.'}},1000);wait()}catch(e){btn.disabled=false;if(status)status.textContent=e.message}}
 $('#appRestart')?.addEventListener('click',()=>appControl('restart'));$('#appStop')?.addEventListener('click',()=>appControl('stop'));
 // All entry points, desktop and mobile, load the SAME manager. No path reset during progress polling.
 document.addEventListener('click',e=>{const b=e.target.closest('[data-view],[data-goto]');if(!b)return;const view=b.dataset.view||b.dataset.goto;if(view==='models')refreshHub();if(view==='settings')loadSettings();$('#mobileMoreMenu')?.classList.add('hidden')});
 const more=$('#mobileMoreMenu');$('#mobileMoreToggle')?.addEventListener('click',()=>more?.classList.toggle('hidden'));$('#mobileMoreClose')?.addEventListener('click',()=>more?.classList.add('hidden'));more?.addEventListener('click',e=>{if(e.target===more)more.classList.add('hidden')});$('#mobileUnloadBtn')?.addEventListener('click',()=>{more?.classList.add('hidden');$('#unloadBtn')?.click()});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeBrowser();more?.classList.add('hidden')}});
 let codePollTimer=null,codePolling=false,codeLast='';
 function renderCodeInstall(j={}){
  const running=['queued','running'].includes(j.status);
  $('#hubPrepareCode').disabled=running;
  $('#hubPrepareCode').textContent=running?'Installazione codice…':(hub?.identity?.vendor_ready?'Verifica codice':'Installa solo il codice');
  const line=j.status==='idle'?'':(j.status==='failed'?('Installazione non completata: '+(j.error||j.message||'')):(j.message||j.status||''));
  txt('hubCodeInstallStatus',line);$('#hubCodeInstallStatus')?.classList.toggle('is-error',j.status==='failed');
  const pg=$('#hubCodeProgress');if(pg){pg.hidden=!running;pg.max=j.total||6;pg.value=j.completed||0;}
  txt('hubCodeInstallDetail',[j.target?'Codice: '+j.target:'',j.error||''].filter(Boolean).join('\n'));
 }
 function scheduleCodePoll(){if(!codePollTimer)codePollTimer=setInterval(pollCodeInstall,1000);pollCodeInstall();}
 async function pollCodeInstall(){
  if(codePolling)return;codePolling=true;
  try{
   const r=await api('/api/setup/identity-code-status'),j=r.installation||{};renderCodeInstall(j);
   if(!['queued','running'].includes(j.status)){
    if(codePollTimer)clearInterval(codePollTimer);codePollTimer=null;
    const stamp=(j.id||'')+':'+j.status;
    if(j.status==='completed'&&stamp!==codeLast&&r.status?.vendor_ready&&r.status?.vendor_root===j.target){
     codeLast=stamp;dirty.delete('setupIdentityVendor');
     if(r.status?.vendor_root)putValue('setupIdentityVendor',r.status.vendor_root);
     await refreshHub();
     txt('hubCodeInstallStatus','Codice verificato e collegato. Sarà usato al prossimo lavoro Identity.');
     window.dispatchEvent(new CustomEvent('identity-code-installed',{detail:r.status}));
    }
   } else if(!codePollTimer)codePollTimer=setInterval(pollCodeInstall,1000);
  }catch(e){txt('hubCodeInstallStatus',e.message);if(codePollTimer)clearInterval(codePollTimer);codePollTimer=null;$('#hubPrepareCode').disabled=false;}
  finally{codePolling=false}
 }
 pollCodeInstall();
 window.refreshModelsHub=()=>refreshHub({registry:true});
 refreshHub();loadSettings();
 const onboardingQuery=new URLSearchParams(location.search);
 if(onboardingQuery.get('onboarding')==='1')setTimeout(()=>{refreshHub();if(onboardingQuery.get('network_restart')==='1')setTimeout(async()=>{try{const d=await api('/api/setup');if(d.platform==='windows'&&d.settings?.host==='0.0.0.0'&&d.firewall?.needs_fix&&confirm(tr('Hai scelto accesso LAN. Vuoi configurare ora Windows Firewall per consentire gli altri dispositivi della rete locale?')))await configureFirewall()}catch(_){ }},700)},500);
})();
