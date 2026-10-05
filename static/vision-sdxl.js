/* Native SDXL caption workflow; no Dataset Studio API/Agent dependency. */
(()=>{'use strict';
const $=s=>document.querySelector(s),t=s=>window.ZI18n?.t(s)||s;let csrf='',manager=null,selectedDataset='',last='',dirtyCaptions=new Set(),resolved=null;
async function req(path,opt={}){return api(path,opt)}
const json=(d={},method='POST')=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const message=s=>{$('#trainingVisionJobs').textContent=t(s)};
const safe=async f=>{try{await f()}catch(e){message(e.message)}};
manager=window.ZetalvxVisionUI.mount($('#visionHub'),req);
manager.load().then(()=>manager.resume()).catch(()=>{});
window.ZetalvxCreatorVisionManager=manager;
document.querySelector('[data-hub-tab="vision"]').addEventListener('click',()=>manager.load().catch(e=>{console.warn(e.message)}));
const reportEl=$('#identityResolvedReport');
function showReport(s){resolved=s;reportEl.replaceChildren();const add=(label,val)=>{const d=document.createElement('div'),b=document.createElement('strong'),c=document.createElement('code');b.textContent=t(label);c.textContent=val;c.dataset.noI18n='';d.append(b,c);reportEl.append(d)};
 for(const [label,key] of [['InstantID weights','instantid_root'],['InsightFace root','insightface_root'],['Face swap file','swapper_path'],['InstantID code','vendor_root']])add(label,s[key]);
 for(const f of s.required_files||[])add((f.present?'✓ ':'✕ ')+f.component,f.path);
 for(const n of s.path_notes||[])add('Note',n);
 for(const c of s.vendor_candidates||[]){if(c.complete&&c.path!==s.vendor_root){const b=document.createElement('button');b.type='button';b.className='ghost';b.textContent=t('Use discovered InstantID code')+' · '+c.path;b.onclick=async()=>{try{await req('/api/setup',json({identity_vendor:c.path},'PUT'));$('#setupIdentityVendor').value=c.path;await apply();await read()}catch(e){reportEl.textContent=e.message}};reportEl.append(b)}}
 if(s.vendor_missing?.length)add('Missing code files',s.vendor_missing.join('\n'));
}
async function read(){const root=$('#identityParentProbe').value.trim()||$('#setupIdentityRoot').value.trim();const r=await req('/api/setup/identity-resolve',json({root,derive_children:true}));showReport(r.status)}
async function apply(){const r=await req('/api/setup/identity-reload',json());const p=document.createElement('p');p.textContent=t('Worker paths updated')+' · '+(r.models?.path_signature||'');reportEl.append(p);document.getElementById('hubCheckFiles')?.click()}
$('#identityResolve').onclick=()=>read().catch(e=>reportEl.textContent=e.message);
$('#identityUseResolved').onclick=async()=>{try{if(!resolved)await read();await req('/api/setup',json({identity_root:resolved.identity_root,identity_instantid_root:resolved.instantid_root,identity_insightface_root:resolved.insightface_root,identity_swapper_model:resolved.swapper_path},'PUT'));for(const [id,key] of [['setupIdentityRoot','identity_root'],['hubInstantRoot','instantid_root'],['hubInsightRoot','insightface_root'],['hubSwapperFile','swapper_path']])$('#'+id).value=resolved[key];await apply()}catch(e){reportEl.textContent=e.message}};
$('#identityReloadWorker').onclick=()=>apply().catch(e=>reportEl.textContent=e.message);
})();
