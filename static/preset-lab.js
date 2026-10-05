/* Zetalvx Image Lab — SDXL Edition 0.1.0.27. Explicit preset actions; bounded test preview before enqueue.
   No runtime changes. Saved preset JSON schema and endpoints remain compatible. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id), t=(s,v)=>window.ZI18n?.t(s,v)||s;
 const engine=window.PresetEngine;
 if(!engine)return;
 let presetTab='use',busy=false,signature='',manageId='',lastApplied=null,scheduled=0;
 const flash=(id,text,error=false)=>{const el=by(id);if(!el)return;el.textContent=text;el.classList.toggle('is-error',error);};
 const jsont=(path,data,method='POST')=>api(path,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const list=()=>S.boot?.user_image_presets||[];
 const scopes=p=>{
  const i=engine.includes(p),labels=[];
  for(const [key,label] of [['task','Task'],['model','Model / checkpoint'],['loras','LoRA stack + weights'],['params','Parameters and seed'],['style','Style / recipe'],['prompt','Prompt + negative prompt']])if(i[key])labels.push(t(label));
  return labels.join(' · ')||t('Nothing selected');
 };
 function fingerprint(){
  return JSON.stringify([S.task,engine.snapshot(),['seed','width','height','batch','scheduler','checkpointSelect','inpaintCheckpointSelect'].map(id=>by(id)?.value)]);
 }
 function refreshActive(){
  const text=lastApplied? t(fingerprint()===lastApplied.signature?'Applied: {name}':'Modified after applying: {name}',{name:lastApplied.name}):t('Current form settings');
  by('presetActiveSummary').textContent=text;
 }
 function setTab(name){
  presetTab=name;
  document.querySelectorAll('[data-preset-tab]').forEach(el=>{const active=el.dataset.presetTab===name;el.classList.toggle('active',active);el.setAttribute('aria-selected',String(active));el.tabIndex=active?0:-1;});
  document.querySelectorAll('[data-preset-pane]').forEach(el=>el.hidden=el.dataset.presetPane!==name);
  if(name==='save')renderScope();if(name==='manage')renderManage();
 }
 document.querySelectorAll('[data-preset-tab]').forEach(el=>{
  el.addEventListener('click',()=>setTab(el.dataset.presetTab));
  el.addEventListener('keydown',ev=>{const tabs=[...document.querySelectorAll('[data-preset-tab]')].filter(b=>!b.hidden),idx=tabs.indexOf(el);let next;
   if(ev.key==='ArrowRight')next=(idx+1)%tabs.length;if(ev.key==='ArrowLeft')next=(idx+tabs.length-1)%tabs.length;
   if(ev.key==='Home')next=0;if(ev.key==='End')next=tabs.length-1;
   if(next!==undefined){ev.preventDefault();tabs[next].focus();setTab(tabs[next].dataset.presetTab);}
  });
 });
 function syncComplexity(){
  const simple=S.imageUiMode!=='advanced';
  document.querySelectorAll('[data-preset-tab]').forEach(b=>b.hidden=simple&&b.dataset.presetTab!=='use');
  if(simple&&presetTab!=='use')setTab('use');
 }
 window.addEventListener('imageuimodechange',syncComplexity);syncComplexity();
 function choice(){const value=by('presetChoice').value;const split=value.indexOf(':');return {kind:value.slice(0,split),id:value.slice(split+1)};}
 function selectedPreset(){const {kind,id}=choice();return {kind,id,p:kind==='user'?list().find(p=>p.id===id):kind==='recipe'?applicableImageWorkflows().find(p=>p.id===id):applicableImagePresets().find(p=>p.id===id)};}
 function renderChoice(){
  const {kind,id,p}=selectedPreset(),box=by('presetChoiceInfo');box.replaceChildren();by('recipeOptions').hidden=kind!=='recipe'||!p;
  by('presetApply').disabled=!p||busy;
  if(!p){box.textContent=t('Choose a built-in or saved preset. Nothing will change until Apply.');return;}
  const title=document.createElement('b');title.textContent=kind==='user'?p.name:t(p.name);box.append(title);
  const desc=document.createElement('p');desc.textContent=kind==='user'?(p.description||''):t(p.description||'');box.append(desc);
  const effect=document.createElement('p');
  if(kind==='user')effect.textContent=t('Restores: {scope}',{scope:scopes(p)})+(engine.includes(p).task?' · '+t('Task')+': '+t(TASKS[p.task]?.title||p.task):'');
  else if(kind==='technical'){
   const a=p.apply||{};effect.textContent=t('Changes technical settings only:')+' '+Object.entries(a).map(([key,val])=>key+' '+(typeof val==='object'?getProviderValue(val,''):val)).join(' · ')+'. '+t('Your prompt, seed and dimensions stay unchanged.');
  }else effect.textContent=t('Adds recipe guidance to the effective prompt, with optional recommended parameters.');
  box.append(effect);
  if(kind!=='user'){
   const binding=S.boot?.image_preset_bindings?.bindings?.[id];
   if(binding){const note=document.createElement('p');note.textContent=t('This preset also has a saved model / LoRA shortcut.');box.append(note);}
  }
 }
 function refreshLists(force=false){
  if(!S.boot)return;
  const key=JSON.stringify([S.task,applicableImagePresets().map(p=>p.id),applicableImageWorkflows().map(p=>p.id),list(),window.ZI18n?.language]);
  if(force||key!==signature){
   signature=key;const select=by('presetChoice'),prev=select.value;select.replaceChildren(new Option(t('Choose a preset…'),''));
   for(const [label,kind,items] of [['Built-in · technical settings','technical',applicableImagePresets()],['Built-in · guided recipes','recipe',applicableImageWorkflows()],['My presets','user',list()]]){
    if(!items.length)continue;const group=document.createElement('optgroup');group.label=t(label);
    for(const p of items)group.append(new Option(kind==='user'?p.name:t(p.name),kind+':'+p.id));select.append(group);
   }
   if([...select.options].some(o=>o.value===prev))select.value=prev;
   const m=by('presetManageChoice'),old=m.value;m.replaceChildren(new Option(t('Select your preset…'),''));list().forEach(p=>m.add(new Option(p.name,p.id)));if(list().some(p=>p.id===old))m.value=old;
   renderChoice();renderManage();
  }
  refreshActive();
 }
 by('presetChoice').addEventListener('change',renderChoice);
 function rememberApplied(kind,p){lastApplied={kind,id:p.id,name:kind==='user'?p.name:t(p.name),signature:fingerprint()};refreshActive();}
 by('presetApply').addEventListener('click',()=>{
  const {kind,id,p}=selectedPreset();if(!p)return;
  try{
   let warnings=[];
   if(kind==='user')warnings=engine.load(id)?.warnings||[];
   else engine.apply(kind,id);
   rememberApplied(kind,p);updateTestUi();
   flash('presetFeedback',t('Preset applied. Review the form before generating.')+(warnings.length?' '+warnings.join(' · '):''),warnings.length>0);
  }catch(e){flash('presetFeedback',e.message,true);}
 });
 by('presetManual').addEventListener('click',()=>{engine.clear();lastApplied=null;refreshActive();flash('presetFeedback',t('Recipe guidance removed. Existing prompt, numeric values and LoRAs are kept.'));updateTestUi();});
 by('presetInspect').addEventListener('click',()=>engine.inspect());
 function renderScope(){by('presetSaveScope').textContent=t('Will save: {scope}',{scope:scopes(engine.payload())});}
 by('userPresetType').addEventListener('change',renderScope);
 by('presetSaveIncludes').addEventListener('change',renderScope);
 function renderManage(){
  const id=by('presetManageChoice').value,p=list().find(p=>p.id===id);
  const changed=manageId!==id;manageId=id;
  by('presetManageInfo').textContent=p?t('Saved content: {scope}',{scope:scopes(p)}):t('No user preset selected. Save the current form or import a JSON preset.');
  if(changed){by('presetRename').value=p?.name||'';by('presetRedescribe').value=p?.description||'';}
  for(const id of ['presetManageApply','presetManageDuplicate','presetManageExport','presetManageDelete','presetRenameSave','presetReplace','presetRename','presetRedescribe'])by(id).disabled=!p||busy;
 }
 by('presetManageChoice').addEventListener('change',renderManage);
 async function action(fn){
  if(busy)return;busy=true;by('presetSaveNew').disabled=true;renderManage();renderChoice();
  try{await fn();}catch(e){flash('presetFeedback',e.message,true);}
  finally{busy=false;by('presetSaveNew').disabled=false;renderManage();renderChoice();}
 }
 function receive(d){S.boot.user_image_presets=d.presets||[];engine.refresh();refreshLists(true);}
 function currentSaved(){const p=list().find(p=>p.id===by('presetManageChoice').value);if(!p)throw Error(t('Select a user preset first.'));return p;}
 function nameValue(id){const name=by(id).value.trim();if(!name){by(id).focus();throw Error(t('Enter a preset name.'));}return name;}
 by('presetSaveNew').addEventListener('click',()=>action(async()=>{
  const payload={...engine.payload(),name:nameValue('presetSaveName'),description:by('presetSaveDescription').value.trim()};
  const d=await jsont('/api/image/presets/user',payload);receive(d);by('presetChoice').value='user:'+d.preset.id;by('presetManageChoice').value=d.preset.id;renderChoice();renderManage();
  flash('presetFeedback',t('Saved: {name}. The form and queue are unchanged.',{name:d.preset.name}));
 }));
 by('presetManageApply').addEventListener('click',()=>{by('presetChoice').value='user:'+by('presetManageChoice').value;setTab('use');renderChoice();by('presetApply').focus();});
 by('presetRenameSave').addEventListener('click',()=>action(async()=>{
  const p=currentSaved(),d=await jsont('/api/image/presets/user',{...p,name:nameValue('presetRename'),description:by('presetRedescribe').value.trim()});receive(d);flash('presetFeedback',t('Name and description saved. Parameters unchanged.'));
 }));
 by('presetReplace').addEventListener('click',()=>action(async()=>{
  const p=currentSaved(),payload=engine.payload();if(!confirm(t('Replace "{name}" with the current form? Includes: {scope}',{name:p.name,scope:scopes(payload)})))return;
  receive(await jsont('/api/image/presets/user',{...payload,id:p.id,name:p.name,description:p.description||''}));flash('presetFeedback',t('Preset updated. No generation started.'));
 }));
 by('presetManageDuplicate').addEventListener('click',()=>action(async()=>{const p=currentSaved(),d=await jsont('/api/image/presets/user/'+encodeURIComponent(p.id)+'/duplicate',{});receive(d);by('presetManageChoice').value=d.preset.id;renderManage();flash('presetFeedback',t('Preset duplicated.'));}));
 by('presetManageDelete').addEventListener('click',()=>action(async()=>{const p=currentSaved();if(!confirm(t('Delete "{name}"? Model files and images are not deleted.',{name:p.name})))return;receive(await api('/api/image/presets/user/'+encodeURIComponent(p.id),{method:'DELETE'}));flash('presetFeedback',t('Preset deleted.'));}));
 by('presetManageExport').addEventListener('click',()=>{const p=currentSaved(),a=document.createElement('a');a.href='/api/image/presets/user/'+encodeURIComponent(p.id)+'/download';a.download=p.id+'.json';document.body.append(a);a.click();a.remove();});
 by('presetImport').addEventListener('change',e=>action(async()=>{const file=e.target.files?.[0];if(!file)return;try{
  if(file.size>2*1024*1024)throw Error(t('Preset JSON must be smaller than 2 MiB.'));
  const fd=new FormData();fd.append('file',file);const d=await api('/api/image/presets/user/import',{method:'POST',body:fd});receive(d);flash('presetFeedback',t('Imported {n} presets.',{n:d.imported||0}));
 }finally{e.target.value='';}}));

 // Test configuration: four bounded axes, meaningful ranges for the active task.
 const axes={cfg:{label:'CFG',min:1,max:20,step:.1,from:5,to:9,count:3},steps:{label:'Steps',min:1,max:120,step:1,from:20,to:40,count:3},strength:{label:'Denoise',min:.01,max:1,step:.01,from:.2,to:.5,count:3},seed:{label:'Seed',min:0,max:2147483646,step:1,from:0,to:2,count:3}};
 let testMode='automatic',previewBusy=false,previewSerial=0,snapshot=null,submitting=false,returnFocus=null;
 function setupRows(){
  for(const [key,a] of Object.entries(axes)){
   const row=document.createElement('div');row.className='lab-range-row';row.dataset.testAxis=key;
   row.innerHTML=`<label class="check-row lab-range-title"><input type="checkbox" id="test_${key}_enabled" ${key==='cfg'?'checked':''}/><b>${esc(a.label)}</b></label><div class="lab-range-fields">${[['min','Minimum',a.from],['max','Maximum',a.to],['count','Values',a.count]].map(([field,label,value])=>`<label for="test_${key}_${field}"><span>${label}</span><input id="test_${key}_${field}" type="number" inputmode="${a.step===1||field==='count'?'numeric':'decimal'}" min="${field==='count'?1:a.min}" max="${field==='count'?24:a.max}" step="${field==='count'?1:a.step}" value="${value}"/></label>`).join('')}</div><small id="test_${key}_values" class="lab-values" data-no-i18n></small>`;
   by('testRangeRows').append(row);
  }
 }
 function range(key){
  const a=axes[key],min=Number(by(`test_${key}_min`).value),max=Number(by(`test_${key}_max`).value),count=Number(by(`test_${key}_count`).value);
  if(['min','max','count'].some(f=>!by(`test_${key}_${f}`).value.trim())||!Number.isFinite(min)||!Number.isFinite(max)||!Number.isInteger(count)||count<1||count>24||min<a.min||max>a.max||max<min||(a.step===1&&(!Number.isInteger(min)||!Number.isInteger(max))))throw Error(t('Invalid range for {name}.',{name:t(a.label)}));
  if(count>1&&(max===min||(a.step===1&&count>max-min+1)))throw Error(t('Not enough distinct values for {name}.',{name:t(a.label)}));
  const values=Array.from({length:count},(_,i)=>{const value=count===1?min:min+(max-min)*i/(count-1);return a.step===1?Math.round(value):Math.round((value+Number.EPSILON)*1e6)/1e6;});
  if(new Set(values).size!==count)throw Error(t('Not enough distinct values for {name}.',{name:t(a.label)}));
  return {spec:{min,max,count},values};
 }
 function buildSweep(){
  if(testMode==='automatic'){
   const profile=currentImageAutoProfile();if(!profile)throw Error(t('No profile available for this task.'));
   const sweep={...profile.build(),mode:'automatic',profile:profile.id,name:t(profile.name),max_jobs:24,vary_seed:by('imageAutoTestVarySeed').checked};
   return {sweep,count:autoTestJobCount(sweep),values:Object.fromEntries(Object.keys(axes).filter(k=>sweep[k+'_values']).map(k=>[k,sweep[k+'_values']]))};
  }
  const ranges={},values={};for(const key of Object.keys(axes)){
   if(key==='strength'&&!currentModelSupportsStrength())continue;
   if(by(`test_${key}_enabled`).checked){const r=range(key);ranges[key]=r.spec;values[key]=r.values;}
  }
  if(!Object.keys(ranges).length)throw Error(t('Select at least one parameter to test.'));
  const count=Object.values(values).reduce((n,v)=>n*v.length,1);
  return {sweep:{mode:'custom',profile:'custom_ranges',name:t('Custom comparison'),ranges,max_jobs:24,vary_seed:by('imageAutoTestVarySeed').checked},count,values};
 }
 function updateTestUi(){
  const strength=currentModelSupportsStrength();by('test_strength_enabled').disabled=!strength;
  const seedAxis=testMode==='custom'&&by('test_seed_enabled').checked;
  by('imageAutoTestVarySeed').disabled=seedAxis;if(seedAxis)by('imageAutoTestVarySeed').checked=false;
  for(const key of Object.keys(axes)){
   const enabled=by(`test_${key}_enabled`).checked&&(key!=='strength'||strength);
   for(const f of ['min','max','count'])by(`test_${key}_${f}`).disabled=!enabled;
   const info=by(`test_${key}_values`);
   if(key==='strength'&&!strength){info.textContent=t('Denoise is available for edits, inpaint and references, not text-to-image.');continue;}
   if(!enabled){info.textContent=t('Unchanged: uses the current form value.');continue;}
   try{info.textContent=range(key).values.join(' · ');}catch(e){info.textContent=e.message;}
  }
  let computed=null;
  try{
   const cfg=buildSweep();computed=cfg;const parts=Object.entries(cfg.values).map(([key,vals])=>`${vals.length} ${t(axes[key].label)}`);
   by('imageAutoTestCount').textContent=t('{n} images',{n:cfg.count});
   by('imageAutoTestSummary').textContent=parts.join(' × ')+' = '+cfg.count+'\n'+Object.entries(cfg.values).map(([key,v])=>t(axes[key].label)+': '+v.join(', ')).join(' · ');
   if(cfg.count>24)throw Error(t('Too many combinations ({n}). Maximum: 24. Reduce the number of values.',{n:cfg.count}));
   by('runImageAutoTestBtn').disabled=previewBusy||submitting;flash('testFeedback','');
  }catch(e){by('runImageAutoTestBtn').disabled=true;flash('testFeedback',e.message,true);if(!computed){by('imageAutoTestCount').textContent='—';by('imageAutoTestSummary').textContent=t('Correct the ranges to calculate the total.');}}
 }
 setupRows();
 document.querySelectorAll('[data-test-mode]').forEach(el=>el.addEventListener('click',()=>{
  testMode=el.dataset.testMode;document.querySelectorAll('[data-test-mode]').forEach(b=>{const on=b===el;b.classList.toggle('active',on);b.setAttribute('aria-pressed',String(on));});
  by('testCustomFields').hidden=testMode!=='custom';by('testAutomaticFields').hidden=testMode!=='automatic';updateTestUi();
 }));
 by('imageTestPanel').addEventListener('input',updateTestUi);by('imageTestPanel').addEventListener('change',updateTestUi);
 async function testPayload(){
  if(!S.project)throw Error(t('Open a project first.'));
  const projectId=S.project.id,task=TASKS[S.task];
  if(task.needsSource&&!S.sourceAsset)throw Error(t('Select or upload a source image.'));
  enforceInputLimits();
  if(task.needsMask&&(S.mask.dirty||!S.maskAsset)){
   if(maskHasPaint())await savePaintedMask();else if(!S.maskAsset)throw Error(t('Paint the inpaint mask or upload a mask image.'));
  }
  if(S.project?.id!==projectId)throw Error(t('Project changed. Open the preview again.'));
  if(task.refs&&!S.references.length)throw Error(t('Add at least one reference image.'));
  const conf=buildSweep();if(conf.count>24)throw Error(t('Too many combinations ({n}). Maximum: 24. Reduce the number of values.',{n:conf.count}));
  const params={width:+by('width').value,height:+by('height').value,seed:+by('seed').value,steps:+by('steps').value,cfg:+by('cfg').value,batch:1,quality:by('quality').value.toLowerCase(),negative_prompt:composeImageNegative(by('negativePrompt').value),scheduler:by('scheduler')?.value||'default',strength:+by('strength').value,source_artifact_id:S.sourceAsset||null,mask_artifact_id:S.maskAsset||null,reference_artifact_ids:[...S.references],loras:loraParams(),checkpoint_override:by('checkpointWrap').classList.contains('hidden')?'':by('checkpointSelect').value,inpaint_checkpoint_override:by('inpaintCheckpointWrap').classList.contains('hidden')?'':by('inpaintCheckpointSelect').value};
  // Reject empty / nonfinite values; do not let JSON null silently become a default.
  for(const [key,val] of Object.entries(params))if(typeof val==='number'&&!Number.isFinite(val))throw Error(t('Invalid value: {name}',{name:key}));
  attachImageUiMetadata(params,conf.sweep.profile);
  return {project_id:projectId,tool:task.tool,model_id:by('modelSelect').value||'auto',prompt:composeImagePrompt(by('prompt').value),params,sweep:conf.sweep};
 }
 function closePreview(){if(submitting)return;previewSerial++;snapshot=null;by('imageTestPreview').classList.add('hidden');returnFocus?.focus();}
 async function previewTests(){
  if(previewBusy||submitting)return;previewBusy=true;const serial=++previewSerial;by('runImageAutoTestBtn').disabled=true;flash('testFeedback',t('Preparing preview…'));
  try{
   const request=await testPayload();const result=await jsont('/api/image/auto-test/preview',request);
   if(serial!==previewSerial)return;
   if(S.project?.id!==request.project_id)throw Error(t('Project changed. Open the preview again.'));
   if(!result.plan||!result.request||!Array.isArray(result.plan.variants)||result.plan.count!==result.plan.variants.length)throw Error(t('Invalid preview response. Nothing was queued.'));
   snapshot=result.request;const plan=result.plan;
   by('testPreviewTotal').textContent=t('{n} images · {n} jobs · 1 image each',{n:plan.count});
   by('testPreviewContext').textContent=t('Project')+': '+S.project.name+' · '+t(TASKS[S.task]?.title||S.task)+' · '+t('Seed policy')+': '+t(plan.seed_policy);
   by('testPreviewRows').replaceChildren(...plan.variants.map(v=>{const row=document.createElement('tr');[v.index,v.cfg,v.steps,v.strength??'—',v.seed].forEach(value=>{const cell=document.createElement('td');cell.textContent=value;row.append(cell);});return row;}));
   const fixed=result.request.params;by('testPreviewFixed').textContent=[t('Model')+': '+result.request.model_id,`${fixed.width} × ${fixed.height}`,t('Scheduler')+': '+fixed.scheduler,'LoRA: '+fixed.loras.length,t('Checkpoint')+': '+(fixed.checkpoint_override||t('Model default'))].join(' · ');
   by('testPreviewPrompt').textContent=result.request.prompt+'\n\n'+t('Negative prompt')+': '+(fixed.negative_prompt||'—');
   by('testPreviewConfirm').textContent=t('Start {n} tests',{n:plan.count});by('testPreviewConfirm').disabled=false;flash('testPreviewError','');
   returnFocus=document.activeElement;by('imageTestPreview').classList.remove('hidden');by('testPreviewClose').focus();flash('testFeedback','');
  }catch(e){flash('testFeedback',e.message,true);}
  finally{previewBusy=false;by('runImageAutoTestBtn').disabled=submitting;}
 }
 by('runImageAutoTestBtn').onclick=previewTests;
 by('testPreviewClose').onclick=closePreview;by('testPreviewCancel').onclick=closePreview;
 by('testPreviewConfirm').onclick=async()=>{
  if(submitting||!snapshot)return;
  if(S.project?.id!==snapshot.project_id){flash('testPreviewError',t('Project changed. Open the preview again.'),true);return;}
  submitting=true;by('testPreviewConfirm').disabled=true;by('testPreviewCancel').disabled=true;by('testPreviewClose').disabled=true;
  let succeeded=false;
  try{
   const request=snapshot,d=await jsont('/api/image/auto-test',request);succeeded=true;snapshot=null;
   by('imageTestPreview').classList.add('hidden');flash('testFeedback',t('Queued {n} tests. Follow them in Jobs.',{n:d.count}));
   try{await openProjectNoPoll(request.project_id);startPolling();showView('jobs');}catch(e){flash('testFeedback',t('Tests queued; refresh Jobs to see their status.'));}
  }catch(e){snapshot=null;flash('testPreviewError',e.message+' '+t('Check Jobs before retrying. Reopen the preview for a new attempt.'),true);}
  finally{submitting=false;by('testPreviewCancel').disabled=false;by('testPreviewClose').disabled=false;by('runImageAutoTestBtn').disabled=false;if(succeeded)returnFocus?.focus();}
 };
 by('imageTestPreview').addEventListener('keydown',e=>{
  if(e.key==='Escape'){e.preventDefault();closePreview();return;}
  if(e.key!=='Tab')return;
  const items=[...by('imageTestPreview').querySelectorAll('button:not(:disabled),summary,[tabindex="0"]')].filter(el=>el.getClientRects().length);
  const first=items[0],last=items[items.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
 });
 function schedule(){if(!scheduled)scheduled=requestAnimationFrame(()=>{scheduled=0;refreshLists();updateTestUi();});}
 window.addEventListener('image-form-changed',schedule);window.addEventListener('image-presets-updated',schedule);
 window.addEventListener('languagechange',()=>{refreshLists(true);renderScope();updateTestUi();});
 window.addEventListener('model-hub-updated',schedule);
 window.CreatorLab={updateTestUi,previewTests,buildSweep,refresh:refreshLists,
 useSaved(id){const p=list().find(x=>x.id===id);if(!p)throw Error(t('Select a user preset first.'));const result=engine.load(id);rememberApplied('user',p);refreshLists(true);return result;}};
 setTab('use');refreshLists(true);renderScope();updateTestUi();
})();
