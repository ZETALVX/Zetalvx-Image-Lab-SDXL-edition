/* 0.1.0.18: strict local catalogue + server-link/browser-upload add flow. */
(()=>{
 'use strict';
 const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
 const tr=s=>window.ZI18n?.t(s)||s;
 const pageSize=6;
 let catalog={checkpoint:[],lora:[],sources:[]}, page={checkpoint:0,lora:0};
 let modalKind='checkpoint', method='upload', opener=null, working=false, activeUpload='', cancelUpload=false;
 const mk=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
 const note=(s,bad=false)=>{const e=$('#localCatalogMessage');if(!e)return;e.textContent=tr(s);e.classList.toggle('is-error',bad)};
 async function request(path='',method='GET',data={}){return api('/api/model-hub/local'+path,method==='GET'?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
 async function refresh(){try{const d=await request();catalog=d.catalog;render();}catch(e){note(e.message,true)}}
 function size(v){if(!v)return '';const g=v/1024**3;return g>=1?g.toFixed(1)+' GiB':(v/1024**2).toFixed(1)+' MiB'}
 function button(label,fn,cls='text-button'){const b=mk('button',cls,tr(label));b.type='button';b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){note(e.message,true)}finally{b.disabled=false}};return b}
 async function use(row,kind){
  if(!row.present)return;
  if(kind==='checkpoint'){
   await api('/api/model-hub/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,path:row.path})});
   // A new Models default must become the default in Generate too. Remove only stale
   // per-task checkpoint overrides; every other generation setting is preserved.
   for(const st of Object.values(S.imageSettings||{})){if(st?.controls)st.controls.checkpointSelect=''}
   if($('#checkpointSelect'))$('#checkpointSelect').value='';
   saveUiSession?.();
   await window.refreshModelsHub?.();if($('#hubCheckpoint'))$('#hubCheckpoint').value=row.path;
   try{const live=await api('/api/checkpoints');applyLiveCheckpointInventory(live.checkpoints||[],live.default_checkpoint||row.path)}catch(_){}
   captureImageSettings?.();
   note('Checkpoint selected as default. Generate will use it unless you choose a per-job override.');
  }else{
   S.loras=S.loras||[];
   if(!S.loras.some(x=>x.path===row.path))S.loras.push({name:row.name,path:row.path,strength:1});
   renderLoraStack();captureImageSettings();showView('image');note('LoRA added to Create.');
  }
 }
 async function remove(id){
  if(!confirm(tr('Remove only the link? The file on disk will not be deleted.')))return;
  const d=await request('/'+encodeURIComponent(id),'DELETE');catalog=d.catalog;render();await window.refreshModelsHub?.();
  note(d.still_visible?'Link removed. The file remains visible because it is active or in a scanned folder.':'Link removed. No files deleted.');
 }
 function draw(kind){
  const cp=kind==='checkpoint',prefix=cp?'localCheckpoint':'localLora',host=$(cp?'#localCheckpointList':'#hubLoraFiles'),pager=$('#'+prefix+'Pages');
  const q=$('#'+prefix+'Search').value.toLocaleLowerCase();
  const all=catalog[kind]||[];const rows=all.filter(x=>(x.name+' '+x.path).toLocaleLowerCase().includes(q));
  page[kind]=Math.max(0,Math.min(page[kind],Math.ceil(rows.length/pageSize)-1));host.replaceChildren();pager.replaceChildren();
  if(cp)$('#localCheckpointCount').textContent=all.filter(x=>x.generation_enabled!==false).length+' / '+all.length+' '+tr('available');else $('#hubLoraCount').textContent=all.filter(x=>x.generation_enabled!==false).length+' / '+all.length+' '+tr('available');
  if(!rows.length){host.append(mk('p','hub-note',tr('No models found. Link a file, upload one, or add a folder.')));return}
  for(const row of rows.slice(page[kind]*pageSize,(page[kind]+1)*pageSize)){
   const el=mk('article','local-model-row');const head=mk('div','local-model-main');const n=mk('div','local-model-name');
   const title=mk('b','',row.name);title.setAttribute('data-no-i18n','');n.append(title);
   n.append(mk('small','muted',[row.format||'safetensors',size(row.size_bytes)].filter(Boolean).join(' · ')));head.append(n);
   const state=row.active?'Active':!row.present?'Missing':row.generation_enabled===false?'Stored only':'Available in Generate';head.append(mk('span','status-pill '+(!row.present?'planned':row.active?'online':''),tr(state)));el.append(head);
   const actions=mk('div','hub-inline local-row-actions');const useBtn=button(cp?'Use checkpoint':'Use in Create',()=>use(row,kind),'ghost');useBtn.disabled=!row.present||row.generation_enabled===false;actions.append(useBtn);
   if(cp){
    const enabled=row.generation_enabled!==false;
    const toggle=button(enabled?'Disconnect from Generate':'Connect to Generate',async()=>{
     const d=await setCheckpointAvailability(row.id,!enabled);catalog=d.catalog;applyLiveCheckpointInventory(d.checkpoints||[]);render();
     note(!enabled?'Checkpoint connected to Generate.':'Checkpoint disconnected. The file is kept in Models.');
    },'ghost');
    if(row.active||row.inpaint_active){toggle.disabled=true;toggle.title=tr('Choose another default/inpaint checkpoint first.')}
    actions.append(toggle);
    if(row.managed&&row.present&&row.format==='safetensors'){
     const del=button('Delete file',async()=>{
      if(!confirm(tr('Delete only this checkpoint file from the Zetalvx Image Lab model folder?')))return;
      const d=await api('/api/model-hub/local/checkpoints/'+encodeURIComponent(row.id)+'/file',{method:'DELETE',headers:{'Content-Type':'application/json'},body:'{}'});
      catalog=d.catalog;applyLiveCheckpointInventory(d.checkpoints||[]);render();await window.refreshModelsHub?.();note('Checkpoint file deleted.');
     },'danger ghost');
     if(row.active||row.inpaint_active){del.disabled=true;del.title=tr('Choose another default/inpaint checkpoint first.')}
     actions.append(del);
    }
   }else{
    const enabled=row.generation_enabled!==false;
    actions.append(button(enabled?'Disconnect from Generate':'Connect to Generate',async()=>{
     const d=await setLoraAvailability(row.id,!enabled);catalog=d.catalog;render();
     note(!enabled?'LoRA connected to Generate.':'LoRA disconnected. The file is kept in Models.');
    },'ghost'));
    if(row.managed&&row.training_id&&row.present){
     const a=mk('a','button-link ghost',tr('Download'));a.href='/api/training/loras/'+row.training_id+'/download';a.setAttribute('data-safe-download','');actions.append(a);
     actions.append(button('Delete file',async()=>{
      if(!confirm(tr('Delete only this LoRA file? Training checkpoints and the original final artifact are kept. Disconnect from Generate instead to keep this file.')))return;
      await api('/api/training/loras/'+row.training_id,{method:'DELETE'});
      const live=await api('/api/loras');applyLiveLoraInventory(live.loras||[]);await refresh();note('LoRA file deleted.');
     },'danger ghost'));
    }
   }
   const details=mk('details','local-path-details');details.append(mk('summary','',tr('Path')));const code=mk('code','hub-path',row.path);code.setAttribute('data-no-i18n','');details.append(code);
   if(row.legacy)details.append(mk('p','hub-note',tr('Legacy pickle format: load only trusted files. Prefer safetensors.')));
   if(row.reference_id)details.append(button('Remove link',()=>remove(row.reference_id)));
   el.append(actions,details);host.append(el);
  }
  if(rows.length>pageSize){pager.append(button('Back',()=>{page[kind]--;draw(kind)}),mk('span','',`${page[kind]+1} / ${Math.ceil(rows.length/pageSize)}`),button('Next',()=>{page[kind]++;draw(kind)}));pager.firstChild.disabled=page[kind]===0;pager.lastChild.disabled=(page[kind]+1)*pageSize>=rows.length;}
 }
 function render(){
  draw('checkpoint');draw('lora');const box=$('#localSources');box.replaceChildren();
  for(const s of catalog.sources||[]){const row=mk('div','local-source-row');row.append(mk('small','muted',(s.kind==='checkpoint'?'Checkpoint':'LoRA')+' · '+tr(s.entry_type==='folder'?'Folder':'File')));const path=mk('code','hub-path',s.path);path.setAttribute('data-no-i18n','');row.append(path);if(!s.present)row.append(mk('small','is-error',tr('Missing')));row.append(button('Remove link',()=>remove(s.id)));box.append(row)}
 }
 function setMethod(name){
  method=name;$$('[data-local-method]').forEach(b=>b.classList.toggle('active',b.dataset.localMethod===name));$$('[data-local-pane]').forEach(p=>p.hidden=p.dataset.localPane!==name);$('#localModelError').textContent='';
  if(name==='server')setTimeout(()=>$('#localModelPath')?.focus(),0);if(name==='folder')setTimeout(()=>$('#localModelFolder')?.focus(),0);
 }
 function open(kind,initial='upload'){
  opener=document.activeElement;modalKind=kind;working=false;cancelUpload=false;activeUpload='';
  $('#localModelTitle').textContent=tr(kind==='checkpoint'?'Add checkpoint':'Add LoRA');
  $('#localModelPath').value='';$('#localModelFolder').value='';$('#localModelUploadFile').value='';$('#localModelError').textContent='';$('#localModelUploadStatus').textContent='';$('#localModelUploadProgress').hidden=true;$('#localModelUploadProgress').value=0;$('#localModelUploadCancel').hidden=true;
  $('#localModelModal').classList.remove('hidden');setMethod(initial);
 }
 function close(){if(working)return;$('#localModelModal').classList.add('hidden');opener?.focus()}
 async function addServer(entryType,path){
  if(working)return;working=true;$('#localModelError').textContent='';
  try{
   const payload={kind:modalKind,entry_type:entryType,path:path.trim()};let d=await request('','POST',payload);
   if(d.needs_confirmation){if(!confirm(tr(d.preview.note)))return;d=await request('','POST',{...payload,accept_unknown:true})}
   catalog=d.catalog;render();await window.refreshModelsHub?.();note('Link saved. The original files were not changed.');working=false;close();
  }catch(e){$('#localModelError').textContent=tr(e.message)}finally{working=false}
 }
 async function cancelActiveUpload(){cancelUpload=true;if(activeUpload){try{await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload),{method:'DELETE'})}catch(_){}}activeUpload='';working=false;$('#localModelUploadCancel').hidden=true;$('#localModelUploadStatus').textContent=tr('Upload cancelled.');}
 async function uploadOne(file,index,total,pg){
  const init=await api('/api/model-hub/uploads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:file.name,size:file.size,kind:modalKind})});activeUpload=init.upload.id;const chunkSize=Number(init.chunk_size)||8*1024**2;
  let offset=Number(init.upload.received)||0;
  while(offset<file.size){
   if(cancelUpload)throw new Error('Upload cancelled.');const end=Math.min(file.size,offset+chunkSize);const fd=new FormData();fd.append('offset',String(offset));fd.append('chunk',file.slice(offset,end),'chunk.bin');
   const r=await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload)+'/chunk',{method:'POST',body:fd});offset=Number(r.upload.received)||end;const one=file.size?offset/file.size:1;pg.value=Math.max(0,Math.min(100,((index+one)/total)*100));$('#localModelUploadStatus').textContent=`${tr('Uploading…')} ${index+1}/${total} · ${file.name} · ${Math.floor(one*100)}%`;
  }
  let done=await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload)+'/finalize',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  if(done.needs_confirmation){if(!confirm(tr(done.preview.note))){await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload),{method:'DELETE'});activeUpload='';return null}done=await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload)+'/finalize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({accept_unknown:true})});}
  activeUpload='';return done;
 }
 async function uploadFiles(){
  if(working)return;const files=[...($('#localModelUploadFile').files||[])];if(!files.length){$('#localModelError').textContent=tr('Choose one or more .safetensors files first.');return}
  working=true;cancelUpload=false;$('#localModelError').textContent='';$('#localModelUploadStatus').textContent=tr('Preparing upload…');const pg=$('#localModelUploadProgress');pg.hidden=false;pg.value=0;$('#localModelUploadCancel').hidden=false;
  let added=0;
  try{
   for(let i=0;i<files.length;i++){
    if(cancelUpload)throw new Error('Upload cancelled.');const done=await uploadOne(files[i],i,files.length,pg);if(done){added++;catalog=done.catalog||catalog;}
   }
   render();await window.refreshModelsHub?.();pg.value=100;$('#localModelUploadStatus').textContent=files.length===1?tr('Upload complete. Model added to the app folder.'):`${added}/${files.length} ${tr('files uploaded')}`;note(files.length===1?'Upload complete. Model added to the app folder.':'Upload complete. Models added to the app folder.');working=false;setTimeout(close,350);
  }catch(e){if(activeUpload&&!cancelUpload){try{await api('/api/model-hub/uploads/'+encodeURIComponent(activeUpload),{method:'DELETE'})}catch(_){}}activeUpload='';$('#localModelError').textContent=tr(e.message)}finally{working=false;$('#localModelUploadCancel').hidden=true}
 }
 $$('[data-local-add-menu]').forEach(b=>b.onclick=()=>open(b.dataset.localAddMenu,'upload'));
 // Legacy entry points remain supported for older cached markup.
 $$('[data-local-add]').forEach(b=>b.onclick=()=>open(b.dataset.localAdd,b.dataset.entryType==='folder'?'folder':'server'));
 $$('[data-local-method]').forEach(b=>b.onclick=()=>setMethod(b.dataset.localMethod));
 $('#localModelClose').onclick=close;
 $('#localModelSave').onclick=()=>addServer('file',$('#localModelPath').value);
 $('#localModelFolderSave').onclick=()=>addServer('folder',$('#localModelFolder').value);
 $('#localModelUploadStart').onclick=uploadFiles;$('#localModelUploadCancel').onclick=cancelActiveUpload;
 $('#localModelOpenLink').onclick=()=>{close();document.querySelector('[data-hub-tab="add"]')?.click();$('#hubKind').value=modalKind;$('#hubUrl').focus()};
 for(const [kind,id] of [['checkpoint','localCheckpointSearch'],['lora','localLoraSearch']])$('#'+id).oninput=()=>{page[kind]=0;draw(kind)};
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#fileBrowser').classList.contains('hidden'))close()});
 window.addEventListener('model-hub-updated',e=>{if(e.detail.local_catalog){catalog=e.detail.local_catalog;render()}else refresh()});
 window.addEventListener('lora-availability-changed',e=>{catalog=e.detail.catalog;render()});
 window.addEventListener('checkpoint-availability-changed',e=>{catalog=e.detail.catalog;render()});
 window.addEventListener('languagechange',render);
 refresh();
})();
