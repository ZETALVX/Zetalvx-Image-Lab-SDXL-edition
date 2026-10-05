/* Dataset Studio inside Training. One dataset.json, one Vision registry, no iframe/API
 * dependency on the standalone app. Polling does not recreate forms or steal drafts. */
(()=>{'use strict';
const $=s=>document.querySelector(s),all=s=>Array.from(document.querySelectorAll(s));
const t=(s,v={})=>window.ZI18n?.t(s,v)||s.replace(/\{(\w+)\}/g,(m,k)=>v[k]??m);
const root=$('#view-training');if(!root)return;
const KEY='zetalvx.training.workspace.v1',PAGE_SIZE=12;
let current=null,report=null,selected='',pageIndex=0,view='dataset',itemsList=[],galleryKey='',reportKey='',jobsKey='';
let captionDirty=false,settingsDirty=false,baseCaption='',metaBase={},busy=false,refreshing=false,requestId=0,firstBoot=true,ackKey='';
let remembered={};try{remembered=JSON.parse(sessionStorage.getItem(KEY)||'{}')}catch(_){}
if(['dataset','train','results'].includes(remembered.view))view=remembered.view;
const json=(data={},method='POST')=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
const did=()=>current?.id||'';
const status=(message,error=false)=>{const el=$('#dsStatus');el.textContent=t(message);el.hidden=!message;el.classList.toggle('error',!!error)};
const remember=()=>{try{sessionStorage.setItem(KEY,JSON.stringify({dataset:did(),selected,view}))}catch(_){}};
function syncDirty(){window.ZetalvxTrainingCaptionDirty=captionDirty||settingsDirty;$('#dsSaveState').textContent=t(captionDirty?'Unsaved caption':'Caption saved');}
function metadata(){return {name:$('#trainingDatasetName').value,trigger:$('#trainingTrigger').value,trigger_position:$('#trainingTriggerPosition').value,common_caption:$('#trainingCommonCaption').value,vision_model_id:$('#trainingVisionModel').value};}
const getMeta=d=>({name:d?.name||'',trigger:d?.trigger||'',trigger_position:d?.trigger_position||'context',common_caption:d?.common_caption||'',vision_model_id:d?.vision_model_id||''});
function metadataChanged(){settingsDirty=JSON.stringify(metadata())!==JSON.stringify(metaBase);syncDirty();}
function modelManager(){return window.ZetalvxCreatorVisionManager;}
function fillModels(){
 const desired=settingsDirty?$('#trainingVisionModel').value:current?.vision_model_id;
 window.ZetalvxVisionUI?.fillSelect($('#trainingVisionModel'),modelManager()?.models()||[],desired);
 // Keep a missing/disabled saved choice visible rather than silently picking another.
 if(desired && !Array.from($('#trainingVisionModel').options).some(o=>o.value===desired)){
  $('#trainingVisionModel').add(new Option(t('Saved model unavailable')+' · '+desired,desired));$('#trainingVisionModel').value=desired;
 }
}
function putMetadata(d){metaBase=getMeta(d);for(const [id,key] of [['trainingDatasetName','name'],['trainingTrigger','trigger'],['trainingTriggerPosition','trigger_position'],['trainingCommonCaption','common_caption']])$('#'+id).value=metaBase[key];fillModels();}
function publish(){S.training.dataset=current;$('#trainingDatasetSelect').value=did();remember();window.dispatchEvent(new CustomEvent('training-dataset-loaded',{detail:current}));}
function activeItem(){return current?.items.find(it=>it.id===selected);}
function visibleItems(){const filter=$('#dsFilter').value;return (current?.items||[]).filter(it=>{
 const issues=report?.items.find(x=>x.id===it.id);const cap=String(it.caption||'').trim();
 return filter==='missing'?(!cap || (!!current?.trigger&&cap===current.trigger)):
  filter==='review'?!!(issues?.warnings.length||it.caption_flags?.length):true;
});}
function chooseValid(){const filtered=visibleItems();if(!filtered.some(it=>it.id===selected))selected=filtered[0]?.id||'';if(selected)pageIndex=Math.floor(filtered.findIndex(x=>x.id===selected)/PAGE_SIZE);else pageIndex=0;}
function renderCounts(){
 const el=$('#trainingDatasetSummary');el.replaceChildren();if(!current)return;
 const pieces=[t('{n} images',{n:current.items.length}),t('{n} captions ready',{n:report?.captioned??0}),t('{n} need a caption',{n:report?.needs_caption??current.items.length})];
 pieces.forEach(text=>{const span=document.createElement('span');span.textContent=text;el.append(span)});
 $('#dsTrainName').textContent=current.name;
 $('#dsTrainSummary').textContent=pieces.join(' · ')+(current.trigger?' · '+t('Trigger word')+': '+current.trigger:'');
 const inTraining=!!report?.active_training_jobs?.length;
 const blocked=inTraining||!!report?.captioning;
 $('#dsBusyNote').hidden=!blocked;$('#dsBusyNote').textContent=t(inTraining?'This dataset is in training. Editing is locked until the job ends.':'Captioning is running. You can still edit captions; image changes wait until it finishes.');
 $('#dsTrainBusy').hidden=!report?.captioning;$('#dsTrainBusy').textContent=t('Wait or stop captioning before starting training.');
 $('#trainingUploadImages').disabled=blocked;
 $('#dsDeleteDataset').disabled=blocked;
 $('#dsRemoveImage').disabled=blocked;
 $('#dsCaption').disabled=inTraining;
 for(const id of ['trainingDatasetName','trainingTrigger','trainingTriggerPosition','trainingCommonCaption','trainingVisionModel','dsApplyTrigger','dsSaveSettings','trainingSaveCaptions'])$('#'+id).disabled=inTraining;
 $('#dsUseForTraining').disabled=!current.items.length||blocked;
 $('#trainingStart').disabled=!current.items.length||blocked;
 $('#datasetZipExport').disabled=!current.items.length;
}
function renderGallery(force=false){
 const filtered=visibleItems(),pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE));pageIndex=Math.max(0,Math.min(pages-1,pageIndex));
 const slice=filtered.slice(pageIndex*PAGE_SIZE,(pageIndex+1)*PAGE_SIZE);
 const key=JSON.stringify([did(),selected,pageIndex,$('#dsFilter').value,slice.map(x=>[x.id,x.caption,x.caption_flags]),report?.items]);
 if(force||key!==galleryKey){
  galleryKey=key;const box=$('#dsGallery');box.replaceChildren();
  if(!slice.length){const msg=document.createElement('p');msg.className='ds-hint';msg.textContent=t(current?.items.length?'No images match this filter':'Add images to begin');box.append(msg)}
  for(const it of slice){
   const b=document.createElement('button');b.type='button';b.dataset.datasetImage=it.id;b.setAttribute('aria-selected',String(it.id===selected));b.setAttribute('aria-label',it.original_name||it.id);
   const img=document.createElement('img');img.src='/api/training/datasets/'+did()+'/items/'+it.id+'/thumbnail';img.alt=it.original_name||'';img.loading='lazy';img.decoding='async';
   const name=document.createElement('span');name.className='ds-thumb-name';name.textContent=it.original_name||it.id;
   const flag=document.createElement('span');const warnings=report?.items.find(x=>x.id===it.id)?.warnings||[];const needs=!String(it.caption||'').trim()||(current.trigger&&String(it.caption).trim()===current.trigger);
   flag.className='ds-marker'+(warnings.length||needs?' review':'');flag.textContent=needs?'…':warnings.length?'!':'✓';
   b.append(img,name,flag);b.onclick=()=>action(b,async()=>{await saveAll();selected=it.id;captionDirty=false;renderGallery();renderEditor();remember();if(innerWidth<=900)$('#dsEditor').scrollIntoView({block:'start',behavior:'smooth'})});box.append(b);
  }
 }
 $('#dsPageLabel').textContent=t('Page {page} of {pages}',{page:pageIndex+1,pages});$('#dsPagePrevious').disabled=pageIndex===0;$('#dsPageNext').disabled=pageIndex>=pages-1;
}
function renderEditor(force=false){
 const it=activeItem();$('#dsEditor').hidden=!it;if(!it)return;
 const src='/api/training/datasets/'+did()+'/items/'+it.id+'/file';const img=$('#dsImagePreview');if(img.getAttribute('src')!==src)img.src=src;
 $('#dsImageName').textContent=it.original_name||it.id;$('#dsImageMeta').textContent=[it.width&&it.height?`${it.width} × ${it.height}`:'',it.caption_model_name||t(it.caption_source||'manual')].filter(Boolean).join(' · ');
 if(!captionDirty&&(force||document.activeElement!==$('#dsCaption'))){$('#dsCaption').value=it.caption||'';baseCaption=it.caption||'';$('#dsReloadCaption').hidden=true;}
 const flags=report?.items.find(x=>x.id===it.id)?.warnings||[];
 $('#dsCaptionHints').textContent=flags.map(warningLabel).join(' · ');syncDirty();
}
function warningLabel(w){return t({empty_caption:'Empty caption',missing_trigger:'Missing trigger',repeated_trigger:'Repeated trigger',check_token_length:'Check token length',manual_edit_preserved:'Manual edit preserved',dataset_settings_changed:'Dataset settings changed'}[w]||w);}
function renderReport(force=false){
 const key=JSON.stringify(report);if(!force&&reportKey===key)return;reportKey=key;
 if(!report)return;
 $('#dsReportSummary').textContent=t('Caption check: {images} images · {empty} empty · {missing} missing trigger · {repeated} repeated trigger',report);
 const box=$('#dsReportItems');box.replaceChildren();
 for(const issue of report.items.filter(x=>x.warnings?.length)){
  const it=current?.items.find(x=>x.id===issue.id);if(!it)continue;
  const b=document.createElement('button');b.type='button';b.className='ghost';b.textContent=(it.original_name||it.id)+' · '+issue.warnings.map(warningLabel).join(', ');
  b.onclick=()=>action(b,async()=>{await saveAll();$('#dsFilter').value='all';selected=it.id;chooseValid();renderGallery();renderEditor(true);$('#dsEditor').scrollIntoView({block:'center',behavior:'smooth'})});box.append(b);
 }
}
function accept(r,{force=false}={}){
 const changedId=did()!==r.dataset?.id;
 if(changedId){captionDirty=false;settingsDirty=false;selected=r.dataset?.id===remembered.dataset?remembered.selected||'':'';galleryKey='';reportKey='';}
 current=r.dataset;report=r.report||report;
 if(!current)return;
 if(!settingsDirty)putMetadata(current);
 if(changedId||!visibleItems().some(x=>x.id===selected))chooseValid();publish();$('#dsEmpty').hidden=true;$('#dsWorkspace').hidden=false;
 renderCounts();renderGallery();renderEditor(force||changedId);renderReport();
}
function syncOptions(datasets){
 itemsList=datasets;const sel=$('#trainingDatasetSelect');
 const previous=did()||sel.value||remembered.dataset||'';
 const sig=JSON.stringify(datasets.map(x=>[x.id,x.name,x.item_count??x.items?.length]));
 if(sel.dataset.optionsKey!==sig && document.activeElement!==sel){
  sel.dataset.optionsKey=sig;sel.replaceChildren(new Option(t('Choose a dataset'),''));
  datasets.forEach(d=>sel.add(new Option(d.name+' · '+(d.item_count??d.items?.length??0),d.id)));
  sel.value=datasets.some(x=>x.id===previous)?previous:'';
 }
}
async function refreshList(){const r=await api('/api/training/datasets');syncOptions(r.datasets||[]);return r.datasets||[];}
async function open(id,{skipSave=false}={}){
 if(!skipSave)await saveAll();
 if(!id){current=null;report=null;selected='';S.training.dataset=null;$('#dsEmpty').hidden=false;$('#dsWorkspace').hidden=true;$('#dsTrainName').textContent=t('Choose a dataset first');$('#dsTrainSummary').textContent='';$('#trainingStart').disabled=true;$('#trainingDatasetSelect').value='';remember();return;}
 const seq=++requestId;const r=await api('/api/training/datasets/'+encodeURIComponent(id));if(seq!==requestId)return;
 accept(r,{force:true});
}
async function refresh(){
 if(!current||refreshing||busy||captionDirty||settingsDirty)return;
 if(['dsCaption','trainingDatasetName','trainingTrigger','trainingCommonCaption','trainingTriggerPosition','trainingVisionModel','trainingDatasetSelect'].includes(document.activeElement?.id))return;
 refreshing=true;const id=did(),seq=++requestId;
 try{const r=await api('/api/training/datasets/'+id);if(did()===id&&seq===requestId&&!captionDirty&&!settingsDirty&&!busy)accept(r)}finally{refreshing=false}
}
async function saveCaption(){
 if(!current||!captionDirty)return;
 const id=did(),iid=selected,value=$('#dsCaption').value,expected=baseCaption;
 const r=await api('/api/training/datasets/'+id,json({captions:{[iid]:value},expected_captions:{[iid]:expected}},'PUT'));
 if(did()!==id||selected!==iid)return;
 baseCaption=value;captionDirty=$('#dsCaption').value!==value;
 accept(r);syncDirty();
}
async function saveSettings(){
 if(!current||!settingsDirty)return;
 const id=did(),values=metadata(),expected={...metaBase};
 const r=await api('/api/training/datasets/'+id,json({...values,expected},'PUT'));
 if(did()!==id)return;
 metaBase=getMeta(r.dataset);settingsDirty=JSON.stringify(metadata())!==JSON.stringify(values);
 accept(r);syncDirty();
}
async function saveAll(){
 await saveCaption();await saveSettings();
 if(captionDirty||settingsDirty)throw Error(t('Finish editing, then retry. Your changes are kept.'));
}
async function action(button,fn){
 if(busy)return;busy=true;if(button)button.disabled=true;
 try{status('');await fn();}
 catch(e){status(e.message,true);if(e.code==='dataset_conflict'){$('#dsReloadCaption').hidden=false;$('#dsSaveState').textContent=t('Conflict: your draft has not been replaced.');}}
 finally{busy=false;if(button)button.disabled=false;if(current){renderCounts();renderCaptionJobs(lastCaptionJobs)}}
}
function selectPage(name,scroll=false){
 if(!['dataset','train','results'].includes(name))return;
 view=name;all('[data-training-page]').forEach(b=>{const active=b.dataset.trainingPage===name;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1});
 for(const [id,tab] of [['trainingPageDataset','dataset'],['trainingPageTrain','train'],['trainingPageResults','results']])$('#'+id).hidden=name!==tab;
 remember();if(scroll)root.scrollIntoView({block:'start',behavior:'smooth'});
}
async function prepareTraining(){
 if(!current)throw Error(t('Choose a dataset first'));
 await saveAll();const r=await api('/api/training/datasets/'+did()+'/use',json());accept(r);
 const warnings=(report.needs_caption||0)+(report.missing||0)+(report.repeated||0);
 const key=JSON.stringify([did(),current.trigger,current.items.map(x=>x.caption)]);
 if(warnings && ackKey!==key){
  if(!confirm(t('Some captions need review. Continue with the saved captions?'))){selectPage('dataset');$('#dsChecks').open=true;throw Error(t('Review the captions before training.'))}
  ackKey=key;
 }
 publish();return did();
}
async function onBootstrap(d){
 syncOptions(d.datasets||[]);
 if(firstBoot){firstBoot=false;const id=itemsList.some(x=>x.id===remembered.dataset)?remembered.dataset:itemsList[0]?.id||'';await open(id,{skipSave:true});selectPage(view);}
 else if(current&&!itemsList.some(x=>x.id===did())&&!captionDirty&&!settingsDirty)await open('',{skipSave:true});
 else await refresh();
}
const terminal=new Set(['completed','completed_with_warnings','completed_with_errors','failed','cancelled','interrupted']);
let lastCaptionJobs=[];
function jobText(j){return [j.model_name||'',t(j.status),`${(j.done||0)+(j.failed||0)}/${j.total||0}`,j.needs_review?t('Review')+': '+j.needs_review:'',j.failed?t('Errors')+': '+j.failed:'',j.message||''].filter(Boolean).join(' · ')}
function renderCaptionJobs(jobs){
 lastCaptionJobs=jobs;const relevant=jobs.filter(j=>j.dataset_id===did());const latest=relevant[0];const active=jobs.find(j=>!terminal.has(j.status));
 $('#dsCaptionCurrent').hidden=!latest;$('#trainingCancelCaption').hidden=!(active&&active.dataset_id===did());$('#trainingAutoCaption').disabled=!!active||!current?.items.length||!!report?.active_training_jobs?.length;
 if(latest){$('#trainingVisionJobs').textContent=jobText(latest);$('#dsCaptionProgress').max=Math.max(1,latest.total||0);$('#dsCaptionProgress').value=(latest.done||0)+(latest.failed||0)}
 const history=relevant.slice(1,6);$('#dsCaptionHistory').hidden=!history.length;
 const key=JSON.stringify(history);if(key!==jobsKey){jobsKey=key;const box=$('#dsCaptionHistoryBody');box.replaceChildren();for(const j of history){const p=document.createElement('p');p.textContent=jobText(j);box.append(p)}}
 if(active&&current){$('#dsUseForTraining').disabled=true;$('#trainingStart').disabled=true;}
}
let polling=false;
async function poll(){if(!root.classList.contains('active')||polling)return;polling=true;try{const r=await api('/api/training/vision/jobs');renderCaptionJobs(r.jobs||[]);await refresh();renderCaptionJobs(r.jobs||[])}finally{polling=false}}

$('#trainingDatasetSelect').addEventListener('change',e=>action(e.target,async()=>{const id=e.target.value;try{await open(id)}finally{e.target.value=did()}renderCaptionJobs(lastCaptionJobs)}));
function createDialog(){const d=$('#dsCreateDialog');$('#dsCreateStatus').textContent='';if(!d.open)d.showModal();$('#dsCreateName').focus();}
$('#trainingCreateDataset').onclick=()=>action(null,async()=>{await saveAll();createDialog()});$('#dsEmptyCreate').onclick=()=>createDialog();
$('#dsCancelCreate').onclick=()=>$('#dsCreateDialog').close();
$('#dsCreateForm').onsubmit=e=>{e.preventDefault();const b=e.submitter;action(b,async()=>{await saveAll();const r=await api('/api/training/datasets',json({name:$('#dsCreateName').value,trigger:$('#dsCreateTrigger').value,trigger_position:$('#dsCreatePosition').value}));$('#dsCreateDialog').close();await refreshList();accept(r,{force:true});selectPage('dataset');status('Dataset created. Add your images.');})};
$('#dsCaption').addEventListener('input',()=>{captionDirty=$('#dsCaption').value!==baseCaption;syncDirty();});
for(const id of ['trainingDatasetName','trainingTrigger','trainingCommonCaption','trainingTriggerPosition'])$('#'+id).addEventListener('input',metadataChanged);
$('#trainingVisionModel').onchange=()=>{metadataChanged();action(null,saveSettings)};
$('#dsSaveSettings').onclick=e=>action(e.currentTarget,async()=>{await saveSettings();await refreshList();status('Dataset settings saved')});
$('#trainingSaveCaptions').onclick=e=>action(e.currentTarget,async()=>{await saveCaption();status('Caption saved')});
$('#dsReloadCaption').onclick=e=>action(e.currentTarget,async()=>{if(!confirm(t('Discard this draft and load the saved caption?')))return;captionDirty=false;await open(did(),{skipSave:true});status('Saved caption loaded')});
$('#dsRefresh').onclick=e=>action(e.currentTarget,async()=>{await saveAll();await refreshList();if(current)await open(did(),{skipSave:true});status('Updated')});
$('#trainingUploadImages').onchange=e=>action(null,async()=>{const files=Array.from(e.target.files);try{
 if(!current)throw Error(t('Choose a dataset first'));if(!files.length)return;
 await saveAll();if(files.reduce((n,f)=>n+f.size,0)>120*1024**2)throw Error(t('Upload limit: 120 MiB'));
 const fd=new FormData();files.forEach(f=>fd.append('files',f));status('Adding images…');
 const r=await api('/api/training/datasets/'+did()+'/upload',{method:'POST',body:fd});accept(r);await refreshList();status(t('Added {added} images · {duplicates} duplicates skipped',{added:r.added,duplicates:r.duplicates}));
 }finally{e.target.value=''}});
$('#datasetZipImport').onchange=e=>action(null,async()=>{try{const f=e.target.files[0];if(!f)return;if(f.size>120*1024**2)throw Error(t('Upload limit: 120 MiB'));await saveAll();const fd=new FormData();fd.append('file',f);status('Importing dataset…');const r=await api('/api/training/datasets/import-zip',{method:'POST',body:fd});await refreshList();await open(r.dataset.id,{skipSave:true});selectPage('dataset');status('Dataset imported. Captions were preserved.');}finally{e.target.value=''}});
$('#datasetZipExport').onclick=e=>action(e.currentTarget,async()=>{await saveAll();if(!current?.items.length)throw Error(t('Add images to begin'));window.location.href='/api/training/datasets/'+did()+'/export';});
$('#dsDeleteDataset').onclick=e=>action(e.currentTarget,async()=>{if(!current||!confirm(t('Delete this dataset and its images?')))return;await api('/api/training/datasets/'+did(),json({},'DELETE'));captionDirty=false;settingsDirty=false;await open('',{skipSave:true});await refreshList();status('Dataset deleted');});
$('#dsRemoveImage').onclick=e=>action(e.currentTarget,async()=>{const it=activeItem();if(!it||!confirm(t('Remove this image?')))return;await saveAll();const r=await api('/api/training/datasets/'+did()+'/items/'+it.id,json({},'DELETE'));captionDirty=false;selected='';accept(r,{force:true});await refreshList();status('Image removed');});
$('#dsApplyTrigger').onclick=e=>action(e.currentTarget,async()=>{await saveAll();if(!current)throw Error(t('Choose a dataset first'));if(current.trigger_position==='context'){status('Context mode never rewrites existing captions. Vision inserts the trigger in its sentence.');return;}if(!confirm(t('Add the trigger only to captions where it is missing?')))return;const r=await api('/api/training/datasets/'+did()+'/apply-trigger',json());accept(r,{force:true});status(t('Updated {n} captions',{n:r.changed}));});
function nextImage(step,b){action(b,async()=>{await saveAll();const f=visibleItems(),i=f.findIndex(x=>x.id===selected),it=f[Math.max(0,Math.min(f.length-1,i+step))];if(it){selected=it.id;chooseValid();renderGallery();renderEditor(true);remember()}})}
$('#dsPrevious').onclick=e=>nextImage(-1,e.currentTarget);$('#dsNext').onclick=e=>nextImage(1,e.currentTarget);
$('#dsPagePrevious').onclick=()=>{pageIndex--;renderGallery()};$('#dsPageNext').onclick=()=>{pageIndex++;renderGallery()};
$('#dsFilter').onchange=e=>action(e.target,async()=>{await saveAll();chooseValid();renderGallery();renderEditor(true)});
$('#datasetCaptionCheck').onclick=e=>action(e.currentTarget,async()=>{await saveAll();if(current){await open(did(),{skipSave:true});$('#dsChecks').open=true;}});
$('#trainingManageVision').onclick=()=>action(null,async()=>{await saveAll();showView('models');document.querySelector('[data-hub-tab="vision"]')?.click();await modelManager()?.load();});
$('#trainingAutoCaption').onclick=e=>action(e.currentTarget,async()=>{await saveAll();if(!current)throw Error(t('Choose a dataset first'));const mid=$('#trainingVisionModel').value;if(!mid)throw Error(t('Choose a Vision model'));if(!confirm(t('Send dataset images to the selected Vision model?')))return;await api('/api/training/datasets/'+did()+'/vision-caption',json({model_id:mid,confirm:true}));status('Captioning started. You may close the browser.');await poll();});
$('#trainingCancelCaption').onclick=e=>action(e.currentTarget,async()=>{await api('/api/training/vision/cancel',json());status('Cancellation requested; the current request may finish first');await poll();});
$('#trainingOpenDatasetStudio').onclick=()=>{const u=new URL(location.href);u.protocol='https:';u.port='8398';u.pathname='/';u.search='';u.hash='';window.open(u.href,'_blank','noopener')};
$('#dsUseForTraining').onclick=e=>action(e.currentTarget,async()=>{await prepareTraining();selectPage('train',true);status('Dataset selected. Review settings, then start training.');});
$('#dsBackToDataset').onclick=()=>selectPage('dataset',true);
all('[data-training-page]').forEach(b=>{b.onclick=()=>action(b,async()=>{await saveAll();selectPage(b.dataset.trainingPage);});b.onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const a=all('[data-training-page]'),next=a[(a.indexOf(b)+(e.key==='ArrowRight'?1:2))%3];next.focus();next.click();}}});
window.addEventListener('vision-models-changed',fillModels);
window.addEventListener('languagechange',()=>{renderCounts();galleryKey='';reportKey='';renderGallery(true);renderEditor();renderReport(true);renderCaptionJobs(lastCaptionJobs)});
window.addEventListener('beforeunload',e=>{if(captionDirty||settingsDirty){e.preventDefault();e.returnValue=''}});
window.ZetalvxDatasetWorkspace={open,onBootstrap,saveAll,prepareTraining,selectPage,refresh,captionJobs:renderCaptionJobs,get dirty(){return captionDirty||settingsDirty;}};
selectPage(view);setInterval(()=>poll().catch(e=>status(e.message,true)),2500);
})();
