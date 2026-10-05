// Modified in Zetalvx Image Lab — SDXL Edition 0.1.0.18; see BUILD_PROVENANCE.json.
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
function formatDuration(sec){sec=Number(sec||0);if(sec<60)return `${sec.toFixed(1)}s`;const m=Math.floor(sec/60),s=Math.round(sec%60);return `${m}m ${s}s`}
function formatBytes(n){n=Number(n||0);if(n<1024)return `${n} B`;if(n<1024**2)return `${(n/1024).toFixed(1)} KB`;if(n<1024**3)return `${(n/1024**2).toFixed(1)} MB`;return `${(n/1024**3).toFixed(2)} GB`}
function pct(v){return Math.max(0,Math.min(100,Math.round(Number(v||0)*100)))}

const S={
 "boot": null,
 "project": null,
 "task": "generate",
 "activeAsset": "",
 "sourceAsset": "",
 "maskAsset": "",
 "references": [],
 "loras": [],
 "editingModel": null,
 "poll": null,
 "imageSettings": {},
 "mediaSettings": {},
 "lastPollArtifacts": "",
 "lastPollBusy": false,
 "mask": {
  "mode": "brush",
  "drawing": false,
  "history": [],
  "sourceId": null,
  "dirty": false,
  "inverted": false
 },
 "loraTarget": "image",
 "pendingReferenceAsset": "",
 "training": {
  "boot": null,
  "dataset": null,
  "poll": null,
  "logJobId": null,
  "loras": [],
  "loraValidation": {},
  "fullModels": [],
  "fullUnets": [],
  "fullValidation": {},
  "fullUnetValidation": {},
  "checkpointValidation": {},
  "checkpointOpen": {}
 },
 "identity": {
  "mode": "face_swap",
  "boot": null,
  "poll": null,
  "logJobId": null,
  "loras": []
 },
 "imageWorkflow": {
  "id": "",
  "task": "",
  "mode": "append",
  "applyParams": true,
  "promptAddon": "",
  "negativeAddon": "",
  "label": ""
 },
 "imagePreset": {
  "id": "",
  "label": ""
 }
};

const TASKS={
 generate:{title:"Generate Image",tool:"generate_image",cap:"generate",needsSource:false,needsMask:false,refs:false,action:"Generate"},
 edit:{title:"Edit Image",tool:"edit_image",cap:"edit",needsSource:true,needsMask:false,refs:false,allowRefs:true,action:"Edit image"},
 inpaint:{title:"Inpaint / Replace",tool:"inpaint",cap:"inpaint",needsSource:true,needsMask:true,refs:false,allowRefs:true,action:"Inpaint"},
 reference:{title:"Reference Image",tool:"reference",cap:"reference",needsSource:false,needsMask:false,refs:true,action:"Generate from reference"},
 multi_image:{title:"Multi-image",tool:"multi_image",cap:"multi_image",needsSource:false,needsMask:false,refs:true,action:"Generate from images"}
};

const IMAGE_PRESETS=[
 {
  "id": "generate_clean",
  "group": "Generate",
  "name": "Clean default",
  "tasks": [
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Neutral manual-friendly starting point for new generations. Best first pass before adding stronger style or LoRAs.",
  "apply": {
   "quality": "Balanced",
   "steps": 30,
   "cfg": 7
  }
 },
 {
  "id": "generate_realistic",
  "group": "Generate",
  "name": "Realistic / photo",
  "tasks": [
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Sharper realistic generation with slightly stronger adherence and cleaner detail.",
  "apply": {
   "quality": "Maximum",
   "steps": 36,
   "cfg": 7.5
  }
 },
 {
  "id": "generate_cinematic",
  "group": "Generate",
  "name": "Cinematic / premium",
  "tasks": [
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Final-render style starting point for more dramatic lighting, polish and premium photography language.",
  "apply": {
   "quality": "Maximum",
   "steps": 40,
   "cfg": 7.8
  }
 },
 {
  "id": "generate_illustration",
  "group": "Generate",
  "name": "Anime / illustration",
  "tasks": [
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Good neutral base for anime, illustration and stylised character generation without going fully abstract.",
  "apply": {
   "quality": "Maximum",
   "steps": 36,
   "cfg": 6.8
  }
 },
 {
  "id": "product_hero",
  "group": "Product / Text",
  "name": "Product hero / packshot",
  "tasks": [
   "generate",
   "edit",
   "reference"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Optimised starting point for clean product shots, catalog images and ad-ready packshots.",
  "apply": {
   "quality": "Maximum",
   "steps": 38,
   "cfg": 7.2,
   "strength": 0.3
  }
 },
 {
  "id": "logo_text_clean",
  "group": "Product / Text",
  "name": "Logo / text clarity",
  "tasks": [
   "generate",
   "edit"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Cleaner baseline for logo-like graphics, simple branding panels and short text-heavy visuals.",
  "apply": {
   "quality": "Maximum",
   "steps": 32,
   "cfg": 7,
   "strength": 0.25
  }
 },
 {
  "id": "preserve_max",
  "group": "Fidelity",
  "name": "Identity preserve · maximum",
  "tasks": [
   "edit",
   "inpaint",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Closest possible match to the source/reference. Best for faces, outfit tweaks and conservative cleanup.",
  "apply": {
   "quality": "Maximum",
   "strength": 0.2,
   "steps": 35,
   "cfg": 5.5
  }
 },
 {
  "id": "portrait_enhance",
  "group": "Fidelity",
  "name": "Portrait enhance",
  "tasks": [
   "edit",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Keeps the person very close while improving portrait quality, skin detail, lighting and camera feel.",
  "apply": {
   "quality": "Maximum",
   "strength": 0.25,
   "steps": 34,
   "cfg": 5.8
  }
 },
 {
  "id": "preserve_balanced",
  "group": "Fidelity",
  "name": "Identity preserve · balanced",
  "tasks": [
   "edit",
   "inpaint",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Safe general preset for edits. Keeps composition stable while allowing clear visible changes.",
  "apply": {
   "quality": "Balanced",
   "strength": 0.35,
   "steps": 30,
   "cfg": 6.5
  }
 },
 {
  "id": "background_change",
  "group": "Edit",
  "name": "Background change",
  "tasks": [
   "edit",
   "inpaint"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Designed for replacing or upgrading the environment while keeping the main subject believable.",
  "apply": {
   "quality": "Balanced",
   "strength": 0.42,
   "steps": 32,
   "cfg": 6.2
  }
 },
 {
  "id": "outfit_change",
  "group": "Edit",
  "name": "Outfit / styling change",
  "tasks": [
   "edit",
   "inpaint",
   "reference"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Good when the person should stay recognisable, but clothing, styling or props need to change more clearly.",
  "apply": {
   "quality": "Maximum",
   "strength": 0.45,
   "steps": 34,
   "cfg": 6.4
  }
 },
 {
  "id": "creative_balanced",
  "group": "Creative",
  "name": "Creative variation",
  "tasks": [
   "edit",
   "inpaint",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Moderate creative freedom for stronger styling, wardrobe changes and scene reinterpretation.",
  "apply": {
   "quality": "Balanced",
   "strength": 0.5,
   "steps": 34,
   "cfg": 7
  }
 },
 {
  "id": "restyle_strong",
  "group": "Creative",
  "name": "Strong restyle",
  "tasks": [
   "edit",
   "inpaint",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "description": "Use when the source is only a loose anchor and you want bigger stylistic or semantic changes.",
  "apply": {
   "quality": "Maximum",
   "strength": 0.7,
   "steps": 40,
   "cfg": 7.5
  }
 }
];


const IMAGE_WORKFLOWS=[
 {
  "id": "portrait_fidelity",
  "name": "Portrait fidelity / recovery",
  "tasks": [
   "edit",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "preserve_max",
  "description": "Best when the goal is to keep the same person as closely as possible while improving quality or moving the portrait into a slightly better render.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Preserve the same subject identity, facial structure, age, hairstyle, gaze and overall expression as closely as possible. Improve image quality carefully without changing the person's identity. Keep proportions realistic and avoid beautifying into a different person.",
  "negativeAddon": "different person, changed identity, extra people, distorted face, deformed eyes, asymmetrical face, plastic skin, over-retouched portrait",
  "apply": {
   "quality": "Maximum",
   "strength": 0.2,
   "steps": 35,
   "cfg": 5.5
  }
 },
 {
  "id": "outfit_background_swap",
  "name": "Outfit or background swap",
  "tasks": [
   "edit",
   "inpaint"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "preserve_balanced",
  "description": "Good when you want the same subject, but with a new outfit, setting or scene styling.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Keep the same subject identity and body proportions. Apply the requested outfit and/or environment change cleanly while preserving believable anatomy, skin tone, facial likeness and lighting consistency.",
  "negativeAddon": "different person, duplicate subject, mismatched body, broken hands, disconnected clothing, messy background edges",
  "apply": {
   "quality": "Balanced",
   "strength": 0.35,
   "steps": 32,
   "cfg": 6
  }
 },
 {
  "id": "cinematic_upgrade",
  "name": "Cinematic photo upgrade",
  "tasks": [
   "edit",
   "reference",
   "multi_image",
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "creative_balanced",
  "description": "Adds a more photographic / cinematic treatment while staying close to the source or reference.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Render with cinematic photography language: natural depth, polished lighting, clean skin detail, controlled contrast, realistic lens feel and premium portrait or scene quality. Keep the subject recognizable.",
  "negativeAddon": "cartoon look, low detail, waxy skin, low realism, oversharpened face, ugly lighting",
  "apply": {
   "quality": "Maximum",
   "strength": 0.45,
   "steps": 36,
   "cfg": 6.5
  }
 },
 {
  "id": "cartoon_subject",
  "name": "Cartoon subject conversion",
  "tasks": [
   "generate",
   "edit",
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "creative_balanced",
  "description": "For clean western-animation/cartoon generation or for converting a reference subject while keeping recognisable visual cues.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Create a clean high-quality cartoon illustration. If reference images are provided, preserve the subject identity, face shape, hairstyle and clothing cues as closely as possible. Use strong readable shapes, clean linework and appealing simplified forms.",
  "negativeAddon": "3d toy look, malformed face, too realistic, muddy lines, grotesque anatomy",
  "apply": {
   "quality": "Balanced",
   "strength": 0.5,
   "steps": 34,
   "cfg": 6
  }
 },
 {
  "id": "anime_serious",
  "name": "Anime serious portrait",
  "tasks": [
   "edit",
   "reference",
   "multi_image",
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "creative_balanced",
  "description": "For a cleaner anime-style result with a more serious and polished tone, rather than a simple generic cartoon.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Create a polished serious anime-style illustration. Preserve the core identity and hairstyle of the subject, with confident facial design, clean rendering, coherent lighting and a refined high-end anime aesthetic.",
  "negativeAddon": "chibi, childish proportions, cheap 3d, blurry anime face, deformed eyes, low effort cartoon",
  "apply": {
   "quality": "Maximum",
   "strength": 0.55,
   "steps": 38,
   "cfg": 6.5
  }
 },
 {
  "id": "product_cleanup",
  "name": "Product cleanup / hero shot",
  "tasks": [
   "edit",
   "generate",
   "reference"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "product_hero",
  "description": "Use for packshots, cleaner ecommerce images and simple ad-style product shots.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Create a clean premium product image with tidy composition, accurate geometry, crisp details, professional lighting and a distraction-free presentation suitable for ecommerce or advertising.",
  "negativeAddon": "crooked product, duplicate items, text artifacts, warped packaging, cluttered background",
  "apply": {
   "quality": "Maximum",
   "strength": 0.25,
   "steps": 34,
   "cfg": 6.5
  }
 },
 {
  "id": "subject_from_photos",
  "name": "Create subject from multiple photos",
  "tasks": [
   "reference",
   "multi_image"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "preserve_max",
  "description": "Best starting point when you give several photos of the same person and want one new image that still matches them closely.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Use the reference photos as the identity anchor. Combine them into one coherent new image of the same subject, preserving the face shape, hairstyle, age impression and overall recognisability as closely as possible.",
  "negativeAddon": "different identity, face drift, inconsistent hairstyle, mismatched age, multiple merged faces",
  "apply": {
   "quality": "Maximum",
   "strength": 0.2,
   "steps": 36,
   "cfg": 5.5
  }
 },
 {
  "id": "logo_text_graphic",
  "name": "Logo / text graphic",
  "tasks": [
   "generate"
  ],
  "providers": [
   "sdxl"
  ],
  "recommendedPreset": "logo_text_clean",
  "description": "For cleaner text-driven graphics, logos, simple social cards and poster-like compositions.",
  "recommendedProviders": [
   "SDXL"
  ],
  "promptAddon": "Prioritise clean text rendering, balanced layout, legibility, accurate typography placement and a polished graphic-design look. Keep the composition simple and intentional.",
  "negativeAddon": "garbled text, unreadable letters, extra icons, messy layout, cluttered poster",
  "apply": {
   "quality": "Maximum",
   "steps": 36,
   "cfg": 7
  }
 }
];

function applicableImageWorkflows(){
 const provider=providerForImageUi();
 return IMAGE_WORKFLOWS.filter(w=>w.tasks.includes(S.task)&&(!w.providers||provider==="auto"||w.providers.includes(provider)));
}
function currentImageWorkflow(){
 const list=applicableImageWorkflows();
 const value=$("#imageWorkflowSelect")?.value||"";
 if(!value)return null;
 return list.find(w=>w.id===value)||null;
}
function renderImageWorkflowOptions(){
 const select=$("#imageWorkflowSelect");if(!select)return;
 const list=applicableImageWorkflows();
 const previous=select.value||"";
 select.innerHTML='<option value="">No workflow / manual</option>' + list.map(w=>`<option value="${w.id}">${esc(w.name)}</option>`).join("");
 select.value=[...select.options].some(o=>o.value===previous)?previous:"";
 if(select.value!==previous && S.imageWorkflow?.id && !list.some(w=>w.id===S.imageWorkflow.id))S.imageWorkflow={id:"",task:"",mode:workflowPromptMode(),applyParams:workflowApplyParamsEnabled(),promptAddon:"",negativeAddon:"",label:""};
 updateImageWorkflowHelp();
}
function applyWorkflowSettings(applyObj){
 if(!applyObj)return;
 if(applyObj.quality&&$("#quality"))$("#quality").value=applyObj.quality;
 const steps=getProviderValue(applyObj.steps,null);if(steps!==null&&steps!==undefined&&$("#steps"))$("#steps").value=steps;
 const cfg=getProviderValue(applyObj.cfg,null);if(cfg!==null&&cfg!==undefined&&$("#cfg"))$("#cfg").value=cfg;
 applyStrengthIfSupported(applyObj.strength)
}
function workflowPromptMode(){return $("#imageWorkflowPromptMode")?.value||"append"}
function workflowApplyParamsEnabled(){return !!$("#imageWorkflowApplyParams")?.checked}
function setActiveWorkflowState(workflow){
 S.imageWorkflow={
   id:workflow?.id||"",
   task:S.task,
   mode:workflowPromptMode(),
   applyParams:workflowApplyParamsEnabled(),
   promptAddon:workflow?.promptAddon||"",
   negativeAddon:workflow?.negativeAddon||"",
   label:workflow?.name||""
 };
}
function clearActiveWorkflow(syncSelect=true){
 if(syncSelect&&$("#imageWorkflowSelect"))$("#imageWorkflowSelect").value="";
 S.imageWorkflow={id:"",task:"",mode:workflowPromptMode(),applyParams:workflowApplyParamsEnabled(),promptAddon:"",negativeAddon:"",label:""};
 updateImageWorkflowHelp();
 updateImageModeUi();
}
function workflowInstructionsPreview(workflow){
 if(!workflow)return "Manual mode: no workflow guidance selected. Use this when you want full prompt freedom or pure technical testing.";
 const rec=(workflow.recommendedProviders||[]).join(" · ")||"Current model";
 const cfg=getProviderValue(workflow.apply?.cfg,"");
 const steps=getProviderValue(workflow.apply?.steps,"");
 const strength=strengthLabelSuffix(workflow.apply?.strength);
 const active=S.imageWorkflow?.id===workflow.id?` Active workflow: ${workflow.name}.`:"";
 return `${workflow.description} Recommended models: ${rec}. Suggested starting point: ${workflow.apply?.quality||"Balanced"} · CFG ${cfg} · Steps ${steps}${strength}. Task: ${workflow.tasks.join(" / ")}. Changes: recipe guidance${workflow.applyParams===false?"":" + optional parameters"}.${active}`;
}
function updateImageWorkflowHelp(){
 const box=$("#imageWorkflowHelp");if(!box)return;
 const workflow=currentImageWorkflow();
 let txt=workflowInstructionsPreview(workflow);
 if(S.imageWorkflow?.id){
   const mode=S.imageWorkflow.mode||"append";
   const params=S.imageWorkflow.applyParams?" Parameters override enabled.":" Parameters unchanged.";
   txt+=` Hidden guidance is currently armed for generation (${mode}).${params}`;
 }
 box.textContent=txt;
 updateImageModeUi();
}
function applyImageWorkflow(workflowId){
 const workflow=applicableImageWorkflows().find(w=>w.id===workflowId)||currentImageWorkflow();
 if(!workflow)return;
 if(workflow.tasks?.length===1&&S.task!==workflow.tasks[0])setTask(workflow.tasks[0]);
 else if(!workflow.tasks.includes(S.task))setTask(workflow.tasks[0]);
 if($("#imageWorkflowSelect"))$("#imageWorkflowSelect").value=workflow.id;
 if(workflowApplyParamsEnabled()){
   if(workflow.recommendedPreset&&applicableImagePresets().some(p=>p.id===workflow.recommendedPreset))applyImagePreset(workflow.recommendedPreset);
   applyWorkflowSettings(workflow.apply);
 }
 setActiveWorkflowState(workflow);
 window.applyImagePresetBinding?.(workflow.id);
 captureImageSettings();
 updateImageWorkflowHelp();
 updateImageAutoTestUi();
 updateImageModeUi();
}
function composeImagePrompt(base){
 const mode=S.imageWorkflow?.mode||"append";
 const addon=String(S.imageWorkflow?.promptAddon||"").trim();
 base=String(base||"").trim();
 if(!addon||mode==="params_only")return base;
 if(mode==="replace")return addon;
 return base?`${base}

Additional workflow guidance: ${addon}`:addon;
}
function composeImageNegative(base){
 const addon=String(S.imageWorkflow?.negativeAddon||"").trim();
 base=String(base||"").trim();
 if(!addon||S.imageWorkflow?.mode==='params_only')return base;
 return base?`${base}, ${addon}`:addon;
}

function currentModelSupportsStrength(){
 const prov=providerForImageUi(),cfg=selectedModel()?.config||{};
 if(!["edit","inpaint","reference","multi_image"].includes(S.task))return false;
 if(typeof cfg.supports_strength==="boolean")return !!cfg.supports_strength;
 return prov==="sdxl";
}
function resolvedStrengthValue(raw){
 if(raw===undefined||raw===null)return null;
 const value=getProviderValue(raw,null);
 if(value===null||value===undefined)return null;
 return Number(value);
}
function strengthLabelSuffix(raw){
 const value=resolvedStrengthValue(raw);
 if(value===null)return "";
 if(!currentModelSupportsStrength())return " · strength n/a on this model";
 return ` · strength ${value.toFixed(2)}`;
}
function applyStrengthIfSupported(raw){
 const value=resolvedStrengthValue(raw);
 if(value===null||!currentModelSupportsStrength()||!$("#strength")||$("#strength").disabled)return;
 $("#strength").value=value;$("#strengthValue").textContent=value.toFixed(2);
}
function imageAutoProfilesForTask(task=S.task){
 const cfgBase=numVal("#cfg"),stepsBase=Math.max(1,Math.round(numVal("#steps")||30)),strengthBase=Math.max(0.01,Math.min(1,numVal("#strength")||0.35));
 const strengthCap=currentModelSupportsStrength();
 if(task==="generate")return [
  {id:"cfg_sweep",name:"CFG sweep",description:"Compares prompt adherence only.",build:()=>({cfg_values:uniqueNums([cfgBase-1,cfgBase,cfgBase+1],1,20),steps_values:[stepsBase]})},
  {id:"steps_sweep",name:"Steps sweep",description:"Compares render quality and convergence.",build:()=>({cfg_values:[cfgBase],steps_values:uniqueNums([stepsBase,stepsBase+8,stepsBase+16],1,120,true)})},
  {id:"balanced_matrix",name:"CFG × steps matrix",description:"Compact grid for comparing model behaviour on the same prompt.",build:()=>({cfg_values:uniqueNums([cfgBase,cfgBase+1],1,20),steps_values:uniqueNums([stepsBase,stepsBase+10],1,120,true)})}
 ];
 if(strengthCap)return [
  {id:"fidelity_sweep",name:"Strength sweep",description:"Varies denoise / change strength while the rest stays fixed.",build:()=>({strength_values:uniqueNums([Math.max(0.01,strengthBase-0.15),strengthBase,Math.min(1,strengthBase+0.15)],0.01,1),cfg_values:[cfgBase],steps_values:[stepsBase]})},
  {id:"creative_sweep",name:"Creative sweep",description:"Higher freedom sweep for stronger edits or restyles.",build:()=>({strength_values:uniqueNums([Math.max(0.01,strengthBase-0.05),strengthBase,Math.min(1,strengthBase+0.20)],0.01,1),cfg_values:uniqueNums([cfgBase,cfgBase+1],1,20),steps_values:[stepsBase]})},
  {id:"cfg_strength_matrix",name:"Strength × CFG matrix",description:"Useful for comparing fidelity versus stylisation on the same source.",build:()=>({strength_values:uniqueNums([Math.max(0.01,strengthBase-0.15),strengthBase,Math.min(1,strengthBase+0.15)],0.01,1),cfg_values:uniqueNums([cfgBase-1,cfgBase,cfgBase+1],1,20),steps_values:[stepsBase]})}
 ];
 return [
  {id:"cfg_focus",name:"CFG sweep",description:"This model currently relies on prompt, ordered inputs and LoRAs more than a direct strength slider, so Auto Test varies CFG only.",build:()=>({cfg_values:uniqueNums([cfgBase-1,cfgBase,cfgBase+1],1,20),steps_values:[stepsBase]})},
  {id:"steps_focus",name:"Steps sweep",description:"Useful when you want to compare detail/convergence without fake strength changes.",build:()=>({cfg_values:[cfgBase],steps_values:uniqueNums([Math.max(1,stepsBase-8),stepsBase,stepsBase+8],1,120,true)})},
  {id:"cfg_steps_matrix",name:"CFG × steps matrix",description:"Model-aware comparison for pipelines without a reliable strength control in this studio.",build:()=>({cfg_values:uniqueNums([cfgBase,cfgBase+1],1,20),steps_values:uniqueNums([stepsBase,stepsBase+10],1,120,true)})}
 ];
}

const IMAGE_SETTING_IDS=["ratio","quality","width","height","seed","steps","cfg","batch","negativePrompt","strength","prompt","checkpointSelect","inpaintCheckpointSelect","scheduler","imageWorkflowSelect","imageWorkflowPromptMode","imageWorkflowApplyParams"];
function captureImageSettings(task=S.task){
 if(!task||!$("#modelSelect"))return;
 const controls={};
 for(const id of IMAGE_SETTING_IDS){
   const el=$("#"+id);if(!el)continue;
   controls[id]=el.type==="checkbox"?!!el.checked:el.value;
 }
 S.imageSettings[task]={
   model_id:$("#modelSelect").value||"auto",
   controls,
   loras:(S.loras||[]).map(x=>({...x}))
 };
 saveUiSession();
 window.dispatchEvent(new Event('image-form-changed'));
}
function restoreImageSettings(task){
 const st=S.imageSettings[task];if(!st)return false;
 const model=$("#modelSelect");
 if(model&&[...model.options].some(o=>o.value===st.model_id))model.value=st.model_id;
 for(const [id,value] of Object.entries(st.controls||{})){
   const el=$("#"+id);if(!el)continue;
   if(el.type==="checkbox")el.checked=!!value;else el.value=value;
 }
 S.loras=(st.loras||[]).map(x=>({...x}));
 if($("#strengthValue")&&$("#strength"))$("#strengthValue").textContent=(+$("#strength").value).toFixed(2);
 renderLoraStack();
 updateModelPickerButton();updateCapabilityNote();updateCheckpointControls();updateInputPolicy();updateStrengthHelp();
 return true;
}
function providerForImageUi(){return 'sdxl'}
function uniqueNums(values,min,max,roundInt=false){
 const out=[];
 for(let v of values){
   v=Number(v);if(Number.isNaN(v))continue;
   if(min!==undefined)v=Math.max(min,v);if(max!==undefined)v=Math.min(max,v);
   if(roundInt)v=Math.round(v);else v=Math.round(v*100)/100;
   if(!out.includes(v))out.push(v);
 }
 return out;
}
function numVal(sel){const el=typeof sel==="string"?$(sel):sel;return Number(el?.value||0)}
function getProviderValue(map,fallback){
 if(map===undefined||map===null)return fallback;
 if(typeof map!=="object")return map;
 const provider=providerForImageUi();
 if(provider in map)return map[provider];
 return map.default!==undefined?map.default:fallback;
}
function presetDisplayName(p){return p?.group?`${p.group} · ${p.name}`:(p?.name||"Preset")}
function applicableImagePresets(){
 const provider=providerForImageUi();
 return IMAGE_PRESETS.filter(p=>p.tasks.includes(S.task)&&(!p.providers||provider==="auto"||p.providers.includes(provider)));
}
function selectedImagePreset(){
 const value=$("#imagePresetSelect")?.value||"";
 if(!value)return null;
 return applicableImagePresets().find(p=>p.id===value)||null;
}
function renderImagePresetOptions(){
 const select=$("#imagePresetSelect");if(!select)return;
 const list=applicableImagePresets();
 const previous=select.value||"";
 select.innerHTML='<option value="">No preset / manual</option>' + list.map(p=>`<option value="${p.id}">${esc(presetDisplayName(p))}</option>`).join("");
 select.value=[...select.options].some(o=>o.value===previous)?previous:"";
 if(select.value!==previous && S.imagePreset?.id && !list.some(p=>p.id===S.imagePreset.id))S.imagePreset={id:"",label:""};
 renderImagePresetCatalog();
 updateImagePresetHelp();
}
function renderImagePresetCatalog(){
 const box=$("#imagePresetCatalog");if(!box)return;
 const list=applicableImagePresets();
 if(!list.length){box.innerHTML='<div class="empty-mini">No presets available for the current task/model.</div>';return}
 box.innerHTML=list.map(p=>`<button class="preset-card ${S.imagePreset?.id===p.id?"active":""}" type="button" data-preset-id="${esc(p.id)}"><small>${esc(p.group||"Preset")}</small><b>${esc(p.name)}</b><span>${esc(p.description)}</span></button>`).join("");
 $$("#imagePresetCatalog .preset-card").forEach(btn=>btn.onclick=()=>applyImagePreset(btn.dataset.presetId));
}
function setActiveImagePreset(preset){
 S.imagePreset={id:preset?.id||"",label:presetDisplayName(preset)};
}
function clearActiveImagePreset(syncSelect=true){
 if(syncSelect&&$("#imagePresetSelect"))$("#imagePresetSelect").value="";
 S.imagePreset={id:"",label:""};
 updateImagePresetHelp();
 updateImageModeUi();
}
function updateImagePresetHelp(){
 const box=$("#imagePresetHelp");if(!box)return;
 const preset=selectedImagePreset();
 if(!preset){box.textContent="Manual mode: no technical preset selected. Use this when you want to tune CFG, steps and any supported strength controls yourself.";renderImagePresetCatalog();updateImageModeUi();return}
 const cfg=getProviderValue(preset.apply.cfg,"");
 const steps=getProviderValue(preset.apply.steps,"");
 box.textContent=`${preset.description} Recommended starting point: ${preset.apply.quality||"Balanced"} · CFG ${cfg} · Steps ${steps}${strengthLabelSuffix(preset.apply.strength)}. Prompt, seed, resolution and LoRAs stay untouched.`;
 renderImagePresetCatalog();
 updateImageModeUi();
}
function applyImagePreset(presetId){
 const preset=applicableImagePresets().find(p=>p.id===presetId)||selectedImagePreset();
 if(!preset)return;
 if($("#imagePresetSelect"))$("#imagePresetSelect").value=preset.id;
 const a=preset.apply||{};
 if(a.quality&&$("#quality"))$("#quality").value=a.quality;
 const steps=getProviderValue(a.steps,null); if(steps!==null&&steps!==undefined&&$("#steps"))$("#steps").value=steps;
 const cfg=getProviderValue(a.cfg,null); if(cfg!==null&&cfg!==undefined&&$("#cfg"))$("#cfg").value=cfg;
 applyStrengthIfSupported(a.strength);
 setActiveImagePreset(preset);
 window.applyImagePresetBinding?.(preset.id);
 captureImageSettings();
 renderImagePresetCatalog();
 updateImagePresetHelp();
 updateImageAutoTestUi();
 updateImageModeUi();
}
function resetImagePresetToModelDefaults(){
 applyModelDefaults();
 const dv=TASK_STRENGTH[S.task];
 if($("#quality"))$("#quality").value="Balanced";
 if(currentModelSupportsStrength()&&$("#strength")&&!$("#strength").disabled&&TASK_STRENGTH[S.task]!==undefined){$("#strength").value=TASK_STRENGTH[S.task];$("#strengthValue").textContent=Number(TASK_STRENGTH[S.task]).toFixed(2)}
 clearActiveImagePreset(true);
 captureImageSettings();
 updateImageAutoTestUi();
 updateImageModeUi();
}
function currentImageMode(){
 if(S.imageWorkflow?.id)return "workflow";
 if(S.imagePreset?.id)return "preset";
 return "manual";
}
function scrollToPanel(id){
 const el=$("#"+id);if(!el)return;
 for(let p=el;p;p=p.parentElement)if(p.tagName==="DETAILS")p.open=true;
 el.scrollIntoView({behavior:"smooth",block:"start"});
}
function updateImageModeUi(){
 const mode=currentImageMode();
 $("#setManualImageMode")?.classList.toggle("active",mode==="manual");
 $("#focusWorkflowMode")?.classList.toggle("active",mode==="workflow");
 $("#focusPresetMode")?.classList.toggle("active",mode==="preset");
 const workflowLabel=S.imageWorkflow?.id?(S.imageWorkflow.label||S.imageWorkflow.id):"None";
 const presetLabel=S.imagePreset?.id?(S.imagePreset.label||S.imagePreset.id):"None";
 const modeLabel=mode==="workflow"?"Guided Workflow":mode==="preset"?"Quick Preset":"Manual / Clean";
 if($("#imageModeBadge"))$("#imageModeBadge").textContent=`Mode · ${modeLabel}`;
 if($("#imageWorkflowBadge"))$("#imageWorkflowBadge").textContent=`Workflow · ${workflowLabel}`;
 if($("#imagePresetBadge"))$("#imagePresetBadge").textContent=`Preset · ${presetLabel}`;
 const bits=[];
 if(mode==="manual")bits.push("You are in clean/manual mode. No workflow guidance is armed and no preset is active.");
 if(mode==="workflow")bits.push(`Workflow mode is active: ${workflowLabel}. This can add hidden recipe guidance${S.imageWorkflow.applyParams?" and recommended parameters":""}.`);
 if(mode==="preset")bits.push(`Preset mode is active: ${presetLabel}. This changes only the technical starting point.`);
 if(S.imageWorkflow?.id&&mode!=="workflow")bits.push(`Workflow still armed: ${workflowLabel}.`);
 if(S.imagePreset?.id&&mode!=="preset")bits.push(`Preset still active: ${presetLabel}.`);
 bits.push(`Current task: ${TASKS[S.task]?.title||S.task}.`);
 const summary=$("#imageModeSummary");if(summary)summary.textContent=bits.join(" ");
 window.dispatchEvent(new Event("image-form-changed"));
}
function activateCleanImageMode(){
 clearActiveWorkflow(true);
 clearActiveImagePreset(true);
 if($("#imageWorkflowPromptMode"))$("#imageWorkflowPromptMode").value="append";
 if($("#imageWorkflowApplyParams"))$("#imageWorkflowApplyParams").checked=true;
 updateImageWorkflowHelp();
 updateImagePresetHelp();
 updateImageModeUi();
}
function autoProfilesForTask(){return imageAutoProfilesForTask(S.task)||[]}
function currentImageAutoProfile(){
 const list=autoProfilesForTask();
 return list.find(p=>p.id===$("#imageAutoTestProfile")?.value)||list[0]||null;
}
function renderImageAutoProfiles(){
 const select=$("#imageAutoTestProfile");if(!select)return;
 const list=autoProfilesForTask();
 select.innerHTML=list.map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join("")||'<option value="">No profile</option>';
 if(list.length&&![...select.options].some(o=>o.value===select.value))select.value=list[0].id;
 updateImageAutoTestUi();
}
function summarizeSweep(sweep){
 const parts=[];
 if(sweep.strength_values)parts.push(`strength [${sweep.strength_values.join(", ")}]`);
 if(sweep.cfg_values)parts.push(`CFG [${sweep.cfg_values.join(", ")}]`);
 if(sweep.steps_values)parts.push(`steps [${sweep.steps_values.join(", ")}]`);
 return parts.join(" · ");
}
function autoTestJobCount(sweep){
 let n=1;
 if(sweep.strength_values)n*=sweep.strength_values.length;
 if(sweep.cfg_values)n*=sweep.cfg_values.length;
 if(sweep.steps_values)n*=sweep.steps_values.length;
 return n;
}
function updateImageAutoTestUi(){
 if(window.CreatorLab)return window.CreatorLab.updateTestUi();
 const p=currentImageAutoProfile(),summary=$("#imageAutoTestSummary"),count=$("#imageAutoTestCount");
 if(!p){if(summary)summary.textContent="No auto-test profile available for this task.";if(count)count.textContent="0 jobs";return}
 const sweep=p.build();const jobs=autoTestJobCount(sweep);
 if(summary)summary.textContent=`${p.description} ${summarizeSweep(sweep)}. Prompt, resolution, checkpoint override, LoRAs and input assets stay fixed.`;
 if(count)count.textContent=`${jobs} job${jobs===1?"":"s"}`;
}

function bindImageSettingsMemory(){
 const ids=new Set(IMAGE_SETTING_IDS.concat(["modelSelect"]));
 document.addEventListener("input",e=>{if(e.target?.id&&ids.has(e.target.id)){captureImageSettings();updateImageAutoTestUi()}});
 document.addEventListener("change",e=>{if(e.target?.id&&ids.has(e.target.id)){captureImageSettings();updateImageAutoTestUi()}});
}

const CREATOR_SESSION_KEY='creator_sdxl_session_v1';
function saveUiSession(){
 try{sessionStorage.setItem(CREATOR_SESSION_KEY,JSON.stringify({imageSettings:S.imageSettings||{},mediaSettings:S.mediaSettings||{}}))}catch(e){}
}
function loadUiSession(){
 try{
   const d=JSON.parse(sessionStorage.getItem(CREATOR_SESSION_KEY)||"{}");
   S.imageSettings=d.imageSettings||{};S.mediaSettings=d.mediaSettings||{};
 }catch(e){}
}
function projectSessionKey(){return S.project?.id||"_global"}

const MODEL_FIELDS={
 "sdxl": [
  "runtime_python",
  "checkpoint",
  "inpaint_checkpoint",
  "vae",
  "checkpoint_roots",
  "lora_root"
 ]
};

let sdxlTokens=null, sdxlTokenFetch=null;
async function sessionTokens(force=false){
 if(force)sdxlTokens=null;
 if(sdxlTokens)return sdxlTokens;
 if(!sdxlTokenFetch)sdxlTokenFetch=ZetalvxRequestRecovery.fetchText('/api/session/tokens',{cache:'no-store',credentials:'same-origin'}).then(({response:r,text})=>{
  const d=JSON.parse(text);if(!r.ok)throw Error(d.error||'Sign in again');return sdxlTokens=d.tokens;
 }).finally(()=>sdxlTokenFetch=null);
 return sdxlTokenFetch;
}
function csrfScope(url,opt){
 if(!['POST','PUT','PATCH','DELETE'].includes((opt.method||'GET').toUpperCase()))return '';
 const p=new URL(url,document.baseURI).pathname;
 if(p.startsWith('/api/model-hub/')||p.startsWith('/api/download-manager/'))return 'model-hub';
 if(p.startsWith('/api/training/datasets')||p.startsWith('/api/vision/')||p.startsWith('/api/training/vision/')||p.endsWith('/vision-caption')||p==='/api/setup'||p.startsWith('/api/setup/identity-')||p.startsWith('/api/setup/link-face-pack/'))return 'vision';
 return '';
}
async function api(url,opt={}){
 const scope=csrfScope(url,opt);
 for(let attempt=0;attempt<2;attempt++){
  const headers=new Headers(opt.headers||{});
  if(scope){const tokens=await sessionTokens(attempt===1);headers.set('X-CSRF-Token',tokens[scope]);}
  const body=scope&&opt.body===undefined?'{}':opt.body;
  if(scope&&!(body instanceof FormData)&&!headers.has('Content-Type'))headers.set('Content-Type','application/json');
  const {response:r,text}=await ZetalvxRequestRecovery.fetchText(url,{...opt,headers,body});let d={};
  if(text){try{d=JSON.parse(text)}catch(e){if(/^\/api\/identity\/(jobs|auto-test)$/.test(new URL(url,document.baseURI).pathname))throw ZetalvxIdentitySubmit.nonJsonError(r.status);throw new Error(`Invalid JSON from ${url} (HTTP ${r.status}): ${text.slice(0,220)}`)}}
  if(r.status===401&&d?.auth_required){window.location.href=`/login?next=${encodeURIComponent(location.pathname+location.search)}`;throw new Error('Authentication required')}
  // Retry ONLY a request rejected by the CSRF guard, before it performed any action.
  if(scope&&attempt===0&&r.status===403&&d.code==='csrf_failed')continue;
  if(!r.ok){const e=new Error(d.error||`HTTP ${r.status}`);e.code=d.code;e.data=d;e.status=r.status;throw e;}return d;
 }
}

const creatorViewKey='creator_sdxl_last_view';
const creatorInitialQuery=new URLSearchParams(window.location.search);
function validCreatorView(name){return typeof name==='string'&&/^[a-z][a-z0-9-]*$/.test(name)&&!!document.getElementById('view-'+name);}
function rememberedCreatorView(){try{const v=sessionStorage.getItem(creatorViewKey);return validCreatorView(v)?v:'home'}catch(_){return 'home'}}
function rememberCreatorView(name){try{sessionStorage.setItem(creatorViewKey,name)}catch(_){}}
function consumeCreatorOnboarding(){
 try{const u=new URL(window.location.href);u.searchParams.delete('onboarding');u.searchParams.delete('network_restart');history.replaceState(history.state,'',u.pathname+u.search+u.hash)}catch(_){}
}
function showView(name){if(!validCreatorView(name))return;rememberCreatorView(name);if(name==='image'&&S.boot)api('/api/loras').then(d=>applyLiveLoraInventory(d.loras||[])).catch(e=>console.warn('[LORA INVENTORY]',e));window.dispatchEvent(new CustomEvent("creator-view-change",{detail:{view:name}}));$$(".view").forEach(v=>v.classList.toggle("active",v.id===`view-${name}`));$$(".nav").forEach(b=>b.classList.toggle("active",b.dataset.view===name));if(name==="library")renderLibraryAssets();if(name==="training"){loadTraining();if(!S.training.profileInitialized){applyTrainingProfile();S.training.profileInitialized=true;}startTrainingPoll()}if(name==="identity"){loadIdentity();startIdentityPoll()}}
$$(".nav").forEach(b=>b.onclick=()=>showView(b.dataset.view));
$$("[data-goto]").forEach(b=>{if(!b.classList.contains("home-launch-card"))b.onclick=()=>showView(b.dataset.goto)});
async function handleHomeLaunch(btn){
 const task=btn.dataset.task,view=btn.dataset.goto||'image';
 if(task)setTask(task);
 if(btn.dataset.clean==='1')activateCleanImageMode();
 showView(view);
 if(btn.dataset.identityMode){await loadIdentity();setIdentityMode(btn.dataset.identityMode)}
 window.scrollTo({top:0,behavior:'smooth'});
}
$$(".home-launch-card").forEach(b=>b.onclick=()=>handleHomeLaunch(b));

async function bootstrap(){
 // Capture before setTask/openProject initialize Create and change the view.
 const startupView=rememberedCreatorView();
 S.boot=await api('/api/bootstrap');
 if($('#runtimeState'))$('#runtimeState').textContent=S.boot.runtime?.ok?'SDXL runtime · Online':'SDXL runtime · Offline';
 renderProjects();renderModels();renderMediaTools();setTask('generate');
 renderImageWorkflowOptions();renderImagePresetOptions();renderImageAutoProfiles();updateImageModeUi();
 window.renderUserImagePresetOptions?.();window.renderImageEffectiveState?.();
 let savedProject='';try{savedProject=localStorage.getItem('creator_sdxl_project_id')||''}catch(_){};const alive=(S.boot.projects||[]).filter(p=>!Number(p.trashed||0));const firstAlive=alive.find(p=>p.id===savedProject)||alive[0];if(firstAlive)await openProject(firstAlive.id);
 const onboarding=creatorInitialQuery.get('onboarding')==='1';
 showView(onboarding?'models':startupView);
 if(onboarding)consumeCreatorOnboarding();
 if(onboarding){
   const note=creatorInitialQuery.get('network_restart')==='1';
   if(note)setTimeout(()=>alert('Account creato. Hai scelto accesso LAN: salva i modelli e poi riavvia Zetalvx Image Lab — SDXL Edition per applicare l’ascolto sulla rete locale.'),250);
 }
}

// 0.1.0.26: selection and refresh generations prevent stale asynchronous responses.
let projectSelectionEpoch=0, projectRefreshEpoch=0, pendingProjectId='', projectLoadController=null;
function projectSelectionUi(message=''){
 const active=S.project?.id||'';
 $$('[data-open-project]').forEach(el=>{
  const id=el.dataset.openProject,card=el.closest('.project-card');
  el.setAttribute('aria-pressed',String(id===active));el.setAttribute('aria-busy',String(id===pendingProjectId));
  card?.classList.toggle('active',id===active);card?.classList.toggle('pending',id===pendingProjectId);
 });
 const select=$('#libraryProjectSelect');if(select)select.value=pendingProjectId||active;
 const msg=$('#projectSwitchStatus');if(msg)msg.textContent=window.ZI18n?.t(message)||message;
 $('#libraryGrid')?.setAttribute('aria-busy',String(!!pendingProjectId));
}
async function openProject(pid){
 const epoch=++projectSelectionEpoch;projectRefreshEpoch++;
 projectLoadController?.abort();const controller=new AbortController();projectLoadController=controller;
 clearInterval(S.poll);pendingProjectId=pid;projectSelectionUi('Apertura progetto…');
 try{
  const d=await api(`/api/projects/${pid}`,{signal:controller.signal});
  if(epoch!==projectSelectionEpoch)return false;
  if(!d.project||d.project.id!==pid)throw Error('Risposta progetto non valida');
  const changed=S.project?.id!==pid;
  S.project=d.project;S.activeAsset=S.project.state?.active_artifact_id||'';
  if(changed){S.sourceAsset='';S.maskAsset='';S.references=[];S.mask.sourceId=null;S.mask.dirty=false;S.mask.history=[];}
  pendingProjectId='';
  try{localStorage.setItem('creator_sdxl_project_id',pid)}catch(_){}
  $('#topProjectName').textContent=S.project.name;
  renderAssets();renderJobs();renderProjects();renderActivePreview();renderMediaTools();
  if(changed){renderInputs();window.dispatchEvent(new CustomEvent('studio-project-changed',{detail:{id:pid}}));}
  projectSelectionUi();startPolling();return true;
 }catch(e){
  if(epoch!==projectSelectionEpoch||e.name==='AbortError')return false;
  pendingProjectId='';projectSelectionUi(e.message);startPolling();throw e;
 }
}
async function selectLibraryProject(pid){
 try{if(await openProject(pid)){showView('library');const w=$('.workspace');if(w)w.scrollTop=0;if(matchMedia('(max-width:900px)').matches)window.scrollTo({top:0,behavior:'auto'});}}
 catch(e){alert(e.message)}
}
$('#libraryProjectSelect')?.addEventListener('change',e=>selectLibraryProject(e.target.value));
function artifactSignature(project){return (project?.artifacts||[]).map(a=>a.id).join("|")}
let projectPollInFlight=false, projectRecoveryUntil=0;
function generationFeedback(kind,message,bad=false){
 const button=$(kind==='identity'?'#identityGenerate':'#runImageBtn');if(!button)return;
 let node=$('#'+kind+'RequestStatus');
 if(!node){node=document.createElement('div');node.id=kind+'RequestStatus';node.className='training-phase-detail';node.setAttribute('role','status');node.setAttribute('aria-live','polite');button.after(node);}
 node.dataset.sourceMessage=message;node.textContent=window.ZI18n?.t(message)||message;node.hidden=!message;
 node.classList.toggle('training-error',bad);
}
function generationStatusRecovered(kind){
 const node=$('#'+kind+'RequestStatus');
 if(node?.classList.contains('training-error')&&(/reconnect|not confirmed|Connection interrupted/i).test(node.dataset.sourceMessage||''))
  generationFeedback(kind,'Queue updated. Check the latest job status below.');
}
function startPolling(){
 clearInterval(S.poll);
 S.lastPollArtifacts=artifactSignature(S.project);
 S.lastPollBusy=(S.project?.jobs||[]).some(j=>["queued","running"].includes(j.status));
 S.poll=setInterval(async()=>{
   if(!S.project||pendingProjectId||projectPollInFlight||document.hidden)return;
   const busy=(S.project.jobs||[]).some(j=>["queued","running"].includes(j.status));
   if(!busy&&!S.lastPollBusy&&Date.now()>projectRecoveryUntil)return;
   projectPollInFlight=true;
   try{await pollProjectStatus(S.project.id)}catch(e){generationFeedback('image',e.message,true);console.warn("[POLL]",e)}finally{projectPollInFlight=false}
 },2500)
}
async function pollProjectStatus(pid){
 if(S.project?.id!==pid||pendingProjectId)return;
 const epoch=projectSelectionEpoch,refresh=++projectRefreshEpoch;
 const d=await api(`/api/projects/${pid}`);
 if(epoch!==projectSelectionEpoch||refresh!==projectRefreshEpoch||S.project?.id!==pid||pendingProjectId)return;
 const oldArtifacts=S.lastPollArtifacts;
 const oldActive=S.activeAsset;
 S.project=d.project;
 generationStatusRecovered('image');
 S.activeAsset=S.project.state?.active_artifact_id||S.activeAsset;
 const newArtifacts=artifactSignature(S.project);
 const busy=(S.project.jobs||[]).some(j=>["queued","running"].includes(j.status));

 // Only the queue is redrawn continuously. This avoids image/video reloads,
 // scroll jumps and form disruption while a generation is running.
 renderJobs();

 // Refresh media UI one time when an output actually appears.
 if(newArtifacts!==oldArtifacts||S.activeAsset!==oldActive){
   renderStudioResults();renderActivePreview();updateActiveAssetCardStyles();
   
 }
 S.lastPollArtifacts=newArtifacts;
 S.lastPollBusy=busy;
}
async function openProjectNoPoll(pid){
 if(S.project?.id!==pid||pendingProjectId)return false;
 const epoch=projectSelectionEpoch,refresh=++projectRefreshEpoch;
 const d=await api(`/api/projects/${pid}`);
 if(epoch!==projectSelectionEpoch||refresh!==projectRefreshEpoch||S.project?.id!==pid||pendingProjectId)return false;
 S.project=d.project;S.activeAsset=S.project.state?.active_artifact_id||S.activeAsset;
 S.lastPollArtifacts=artifactSignature(S.project);
 S.lastPollBusy=(S.project.jobs||[]).some(j=>["queued","running"].includes(j.status));
 renderAssets();renderJobs();renderActivePreview();renderMediaTools();
 
}

function renderProjects(){
  const box=$("#projectsList") || $("#projectGrid");
  if(!box) return;
  const projects=(S.boot?.projects||[]);
  const active=S.project?.id||"";
  const alive=projects.filter(p=>!Number(p.trashed||0)).sort((a,b)=>(Number(a.sort_order||0)-Number(b.sort_order||0))||String(a.created_at||'').localeCompare(String(b.created_at||'')));
  const trashed=projects.filter(p=>Number(p.trashed||0));
  box.innerHTML=`
    <div class="project-section">
      <div class="section-title">Projects <span class="project-count">${alive.length}</span></div>
      ${alive.map((p,i)=>`
        <div class="project-card ${p.id===active?"active":""}">
          <button type="button" class="project-main" data-open-project="${p.id}" aria-pressed="${p.id===active}">
            <b>${esc(p.name)}</b>
            <small>${esc(p.description||"")}</small>
          </button>
          <div class="project-actions">
            <button class="ghost small project-icon" data-move-project="${p.id}" data-direction="up" ${i===0?'disabled':''} title="Move up" aria-label="Move up">↑</button>
            <button class="ghost small project-icon" data-move-project="${p.id}" data-direction="down" ${i===alive.length-1?'disabled':''} title="Move down" aria-label="Move down">↓</button>
            <button class="ghost small project-icon" data-rename-project="${p.id}" title="Rename" aria-label="Rename">✎</button>
            <button class="danger ghost small project-icon" data-trash-project="${p.id}" title="Move to Trash" aria-label="Move to Trash">×</button>
          </div>
        </div>`).join("") || '<div class="empty-mini">No active projects.</div>'}
    </div>
    <div class="project-section">
      <div class="section-title">Trash <span class="project-count">${trashed.length}</span></div>
      ${trashed.map(p=>`
        <div class="project-card trashed">
          <div class="project-main">
            <b>${esc(p.name)}</b>
            <small>${p.trashed_at?`Trashed · ${esc(p.trashed_at)}`:"Trashed"}</small>
          </div>
          <div class="project-actions">
            <button class="ghost small" data-restore-project="${p.id}">Restore</button>
            <button class="danger ghost small" data-delete-project="${p.id}">Delete forever</button>
          </div>
        </div>`).join("") || '<div class="empty-mini">Trash is empty.</div>'}
    </div>`;
  const select=$('#libraryProjectSelect');if(select){select.replaceChildren(...alive.map(p=>new Option(p.name,p.id)));select.value=active;select.disabled=!alive.length;}
  $$('[data-open-project]').forEach(el=>el.onclick=()=>selectLibraryProject(el.dataset.openProject));
  $$('.project-card').forEach(card=>{const opener=card.querySelector('[data-open-project]');if(!opener)return;card.onclick=e=>{if(e.target.closest('.project-actions'))return;if(e.target.closest('[data-open-project]'))return;opener.click();};});
  projectSelectionUi();
  $$('[data-trash-project]').forEach(el=>el.onclick=()=>trashProject(el.dataset.trashProject));
  $$('[data-restore-project]').forEach(el=>el.onclick=()=>restoreProject(el.dataset.restoreProject));
  $$('[data-delete-project]').forEach(el=>el.onclick=()=>deleteProjectForever(el.dataset.deleteProject));
  $$('[data-rename-project]').forEach(el=>el.onclick=()=>openProjectRename(el.dataset.renameProject));
  $$('[data-move-project]').forEach(el=>el.onclick=()=>moveProject(el.dataset.moveProject,el.dataset.direction));
}
function mediaPreview(a,cls=""){return '<img src="'+esc(a.url)+'" class="'+esc(cls)+'" alt="Image output" loading="lazy" decoding="async">'}
function actualSeed(a){
 const m=a?.metadata||{},p=m.params||{},r=m.runtime_result||{};
 const s=r.seed!==undefined&&r.seed!==null?r.seed:p.seed;
 return s!==undefined&&s!==null&&Number(s)>=0?Number(s):null;
}
function artifactOrdinal(a){
 const arts=[...(S.project?.artifacts||[])].sort((x,y)=>String(x.created_at||'').localeCompare(String(y.created_at||''))||String(x.id).localeCompare(String(y.id)));
 const i=arts.findIndex(x=>x.id===a.id);return i>=0?i+1:0;
}
function artifactKind(a){
 const m=a?.metadata||{},tool=m.tool||'',source=m.source||'';
 if(source==='upload')return m.original_name||'Imported image';
 if(source==='identity_studio')return m.identity_mode==='face_swap'?'Face Swap':'InstantID';
 if(source==='media_tools')return ({extract_frame:'Video frame',resize_image:'Resize',convert_image:'Convert',crop_image:'Crop',rotate_image:'Rotate',flip_image:'Flip'})[m.operation]||'Image tool';
 return ({generate_image:'Text to image',edit_image:'Edit',img2img:'Img2Img',inpaint:'Inpaint',reference:'Reference',multi_image:'Multi image'})[tool]||m.original_name||'Image';
}
function artifactDisplayTitle(a){const n=artifactOrdinal(a),label=window.ZI18n?.t(artifactKind(a))||artifactKind(a);return `${n?String(n).padStart(3,'0')+' · ':''}${label}`}
function artifactCard(a){
 const seed=actualSeed(a);
 return '<div class="asset-card '+(S.activeAsset===a.id?'active':'')+'" data-aid="'+esc(a.id)+'">'+mediaPreview(a)+'<div class="asset-info"><b data-no-i18n>'+esc(artifactDisplayTitle(a))+'</b><small>'+esc(a.created_at)+(seed!==null?' · seed '+seed:'')+'</small><div class="asset-actions"><button data-aact="edit" data-id="'+a.id+'">Edit</button><button data-aact="inpaint" data-id="'+a.id+'">Inpaint</button><button data-aact="reference" data-id="'+a.id+'">Reference</button><button data-adetails="'+a.id+'">Details</button><button data-areuse="'+a.id+'">Reuse</button><button data-amediatools="'+a.id+'">Image tools</button><a data-safe-download href="'+a.url+'?download=1" download>Save</a><button class="danger" data-adelete="'+a.id+'">Delete</button></div></div></div>';
}
function bindAssetCards(){
 $$('.asset-card').forEach(x=>x.onclick=e=>{if(e.target.closest('.asset-actions,video,audio'))return;selectActive(x.dataset.aid)});
 $$('[data-aact]').forEach(b=>b.onclick=e=>{e.stopPropagation();artifactAction(b.dataset.aact,b.dataset.id)});
 for(const [attr,fn] of [['adelete',deleteArtifact],['adetails',showArtifactDetails],['areuse',reuseArtifact],['amediatools',sendArtifactToMediaTools]])$$('[data-'+attr+']').forEach(b=>b.onclick=e=>{e.stopPropagation();fn(b.dataset[attr])});
}
function artifactIsImageResult(a){const m=a?.metadata||{};return a?.type==="image"&&!!m.model_id&&m.tool!=="identity"&&m.tool!=="identity_face_swap"}

function renderImageStudioResults(){
 const arts=(S.project?.artifacts||[]).filter(artifactIsImageResult);
 const latest=$("#imageLatestResult"),hist=$("#imageHistoryGrid");
 if(latest)latest.innerHTML=arts.length?artifactCard(arts[0]):'<div class="empty-state">No image generations yet.</div>';
 if(hist)hist.innerHTML=arts.length?arts.slice(0,12).map(artifactCard).join(""):'<div class="empty-state">No image generations yet.</div>';
}


function renderLibraryAssets(){
 const arts=S.project?.artifacts||[];
 if($("#libraryGrid"))$("#libraryGrid").innerHTML=arts.map(artifactCard).join("")||'<div class="empty-state">No assets in this project.</div>';
 if($("#homeRecent"))$("#homeRecent").innerHTML=arts.slice(0,10).map(artifactCard).join("")||'<div class="empty-state">No assets yet.</div>';
 bindAssetCards();
}
function renderStudioResults(){renderImageStudioResults();bindAssetCards()}
function renderAssets(){renderLibraryAssets();renderStudioResults()}
function updateActiveAssetCardStyles(){$$(".asset-card").forEach(x=>x.classList.toggle("active",x.dataset.aid===S.activeAsset))}
async function selectActive(aid){S.activeAsset=aid;await api(`/api/projects/${S.project.id}/active-artifact`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({artifact_id:aid})});renderActivePreview();updateActiveAssetCardStyles()}
function useAssetAsImageReference(aid){S.references=[aid];setTask("reference");showView("image");renderInputs()}
function sendArtifactToMediaTools(aid){
 const a=artifactById(aid);
 if(!a||!["image"].includes(a.type)){alert("Choose an image asset.");return}
 S.activeAsset=aid;
 if(!S.mediaTools)S.mediaTools={};
 if(!Array.isArray(S.mediaTools.selectedIds))S.mediaTools.selectedIds=[];
 S.mediaTools.selectedIds=[aid];
 S.mediaTools.primaryId=aid;
 S.mediaTools.lastAction=S.mediaTools.lastAction||"resize";
 saveUiSession();
 showView("media-tools");if($("#imageToolsPanel"))$("#imageToolsPanel").open=true;
 try{
   renderMediaTools?.();
 }catch(_){}
 api(`/api/projects/${S.project.id}/active-artifact`,{
   method:"PUT",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({artifact_id:aid})
 }).catch(()=>{});
}

function artifactAction(action,id){
 if(!artifactById(id))return;
 S.activeAsset=id;
 if(action==='reference'){S.references=[id];setTask('reference')}
 else {S.sourceAsset=id;S.maskAsset='';setTask(action==='inpaint'?'inpaint':'edit')}
 renderInputs();
}

function currentArtifact(){return (S.project?.artifacts||[]).find(a=>a.id===S.activeAsset)}
function renderActivePreview(){
 const box=$("#mainPreview"),a=currentArtifact();if(!box)return;
 $("#activeAssetLabel").textContent=a?`Active #${a.id.slice(0,8)}`:"No active asset";
 const key=a?(a.id+':'+a.url):'empty';if(box.dataset.previewKey===key)return;
 box.dataset.previewKey=key;
 box.innerHTML=a?mediaPreview(a,"main-image"):'<div class="preview-empty"><span>✦</span><b>No active media yet</b><small>Generate one, upload a source/reference, or pick one from Library.</small></div>';
}


function jobDetailsObject(j){
 return {id:j.id,status:j.status,phase:j.phase,model_id:j.model_id,tool:j.tool,prompt:j.prompt,
         duration_seconds:j.duration_seconds,created_at:j.created_at,started_at:j.started_at,completed_at:j.completed_at,
         params:j.params||{},error:j.error||""}
}
function progressJob(j,compact=false){
 const p=pct(j.progress),cur=Number(j.step_current||0),tot=Number(j.step_total||0);
 const elapsed=Number(j.elapsed_seconds||j.duration_seconds||0);
 return `<div class="queue-job ${esc(j.status)}">
   <div class="queue-job-head"><div><b>${esc(j.model_id)}</b><small>${esc(j.prompt||"").slice(0,100)}</small></div><span>${esc(j.phase||j.status)} · ${p}%</span></div>
   ${j.params?.auto_test?`<div class="job-test-label"><b>${esc(window.ZI18n?.t('Test {index}/{total}',{index:j.params.test_index,total:j.params.test_total})||`Test ${j.params.test_index}/${j.params.test_total}`)}</b> · ${esc(j.params.test_label||'')}</div>`:''}
   <div class="progress-track"><div class="progress-fill" style="width:${p}%"></div></div>
   <div class="queue-job-foot"><span>${tot?`${cur}/${tot} steps · `:""}${formatDuration(elapsed)}</span>
   <div><button class="mini" data-jdetails="${j.id}">Details</button>${["queued","running"].includes(j.status)?`<button class="mini danger" data-jcancel="${j.id}">Cancel</button>`:""}</div></div>
 </div>`
}
function renderLiveQueue(){
 const jobs=(S.project?.jobs||[]).filter(j=>["queued","running"].includes(j.status));
 $("#queueCount").textContent=`${jobs.length} job${jobs.length===1?"":"s"}`;
 $("#liveQueue").innerHTML=jobs.length?jobs.slice().reverse().map(j=>progressJob(j,true)).join(""):'<div class="empty-mini">Queue empty.</div>';
 bindJobButtons();
}
function renderJobs(){
 const jobs=S.project?.jobs||[];
 $("#jobsList").innerHTML=jobs.length?jobs.map(j=>progressJob(j)).join(""):'<div class="empty-state">No jobs.</div>';
 renderLiveQueue();bindJobButtons();
}
function bindJobButtons(){
 $$("[data-jcancel]").forEach(b=>b.onclick=async()=>{await api(`/api/jobs/${b.dataset.jcancel}/cancel`,{method:"POST"});await openProjectNoPoll(S.project.id)});
 $$("[data-jdetails]").forEach(b=>b.onclick=()=>{const j=(S.project?.jobs||[]).find(x=>x.id===b.dataset.jdetails);if(j)showDetails(`Job #${j.id.slice(0,8)}`,jobDetailsObject(j))});
}
$("#refreshJobs").onclick=()=>S.project&&openProjectNoPoll(S.project.id);
$('#cleanupJobs')?.addEventListener('click',async()=>{
 if(!confirm('Emergency cleanup: cancel all queued/running jobs and restart generation workers?'))return;
 const b=$('#cleanupJobs'),msg=$('#jobsActionStatus');b.disabled=true;b.textContent='Ripristino…';if(msg)msg.textContent='';
 try{const d=await api('/api/jobs/cleanup',{method:'POST'});if(S.project)await openProjectNoPoll(S.project.id);if(msg)msg.textContent=(window.ZI18n?.t('Coda ripristinata. Lavori annullati: {n}',{n:d.cancelled||0})||`Coda ripristinata. Lavori annullati: ${d.cancelled||0}`);}
 catch(e){if(msg)msg.textContent=e.message;else alert(e.message)}
 finally{b.disabled=false;b.textContent=window.ZI18n?.t('Ripristina coda')||'Ripristina coda';}
});

const TASK_STRENGTH={edit:.35,inpaint:.45,reference:.30,multi_image:.35};
function setTask(task){
 if(S.task&&S.task!==task)captureImageSettings(S.task);
 const firstVisit=!S.imageSettings[task];
 S.task=task;const t=TASKS[task];$("#taskTitle").textContent=t.title;$("#runImageBtn").textContent=t.action;
 $$("[data-task]").forEach(b=>b.classList.toggle("active",b.dataset.task===task));
 $("#sourceCard").classList.toggle("hidden",!t.needsSource);$("#maskCard").classList.toggle("hidden",!t.needsMask);$("#refsCard").classList.toggle("hidden",!(t.refs||t.allowRefs));
 $("#inputPanel")?.classList.toggle("hidden",!t.needsSource&&!t.needsMask&&!(t.refs||t.allowRefs));
 $("#strengthWrap").classList.toggle("hidden",task==="generate");
 $("#maskEditorPanel").classList.toggle("hidden",task!=="inpaint");
 if(firstVisit&&task!=="generate"){const v=TASK_STRENGTH[task]??.35;$("#strength").value=v;$("#strengthValue").textContent=v.toFixed(2)}
 populateModelSelect();
 if(!restoreImageSettings(task)){
   updateCheckpointControls();updateInputPolicy();updateStrengthHelp();captureImageSettings(task);
 }
 renderImageWorkflowOptions();renderImagePresetOptions();renderImageAutoProfiles();
 renderInputs();updateImageModeUi();showView("image");
}
$$("[data-task]").forEach(b=>{if(!b.classList.contains("home-launch-card"))b.onclick=()=>setTask(b.dataset.task)});
$("#openLibraryBtn").onclick=()=>showView("library");

function taskSupport(m){return m?.task_support?.[TASKS[S.task].cap]||{level:"unavailable",rank:0,reason:"No adapter."}}
function visibleModels(){
 const showExp=$("#showExperimental")?.checked!==false;
 let models=(S.boot.models||[]).filter(m=>m.enabled);
 models=models.filter(m=>{const s=taskSupport(m);return s.rank>0&&(showExp||s.level!=="experimental")});
 models.sort((a,b)=>{
   const rank=taskSupport(b).rank-taskSupport(a).rank;if(rank)return rank;
   if(["edit","reference","multi_image","inpaint"].includes(S.task)){
 
   }
   return a.name.localeCompare(b.name)
 });
 return models
}
function updateModelPickerButton(){
 const m=(S.boot.models||[]).find(x=>x.id===$("#modelSelect").value);
 const s=m?taskSupport(m):null;
 $("#modelPickerName").textContent=m?m.name:"SDXL";
 $("#modelPickerStatus").textContent=m?(s.level||"").toLowerCase():"checkpoint corrente";
 $("#modelPickerButton").title=[$("#modelPickerName").textContent,$("#modelPickerStatus").textContent].join(" · ");
}
function populateModelSelect(){
 const models=visibleModels(),previous=$("#modelSelect").value||"auto";
 $("#modelSelect").innerHTML=`<option value="auto">AUTO</option>`+models.map(m=>`<option value="${m.id}">${esc(m.name)}</option>`).join("");
 if([...$("#modelSelect").options].some(o=>o.value===previous))$("#modelSelect").value=previous;else $("#modelSelect").value="auto";
 $("#modelPickerMenu").innerHTML=`<button class="model-picker-item" data-model-id="auto"><span>AUTO</span><small>automatic</small></button>`+
   models.map(m=>{const s=taskSupport(m),ready=m.validation?.ready?"ready":"files missing";return `<button class="model-picker-item" data-model-id="${m.id}"><span>${esc(m.name)}</span><small>${esc(s.level.toLowerCase())} · ${ready}</small></button>`}).join("");
 $$("#modelPickerMenu [data-model-id]").forEach(b=>b.onclick=()=>{
   $("#modelSelect").value=b.dataset.modelId;$("#modelPickerMenu").classList.add("hidden");
   updateModelPickerButton();updateCapabilityNote();updateCheckpointControls();updateInputPolicy();updateStrengthHelp();renderImagePresetOptions();renderImageAutoProfiles();captureImageSettings()
 });
 updateModelPickerButton();updateCapabilityNote();updateInputPolicy();updateStrengthHelp();renderImagePresetOptions();renderImageAutoProfiles();
}
$("#modelPickerButton").onclick=e=>{e.stopPropagation();$("#modelPickerMenu").classList.toggle("hidden")};
document.addEventListener("click",e=>{if(!e.target.closest(".model-picker"))$("#modelPickerMenu").classList.add("hidden")});
$("#showExperimental").onchange=populateModelSelect;
$("#modelSelect").onchange=()=>{updateModelPickerButton();updateCapabilityNote();updateCheckpointControls();updateInputPolicy();updateStrengthHelp();renderImagePresetOptions();renderImageAutoProfiles();captureImageSettings()};
function updateCapabilityNote(){
 const m=(S.boot.models||[]).find(x=>x.id===$("#modelSelect").value);
 if(!m){$("#capabilityNote").innerHTML="<b>AUTO</b><br><span>Prefers a ready NATIVE adapter, then FALLBACK, then EXPERIMENTAL.</span>";return}
 const s=taskSupport(m),caps=m.capabilities||[];
 $("#capabilityNote").innerHTML=`<b>${esc(m.name)} · <span class="support-${s.level}">${s.level.toUpperCase()}</span></b><br><span>${esc(s.reason)}</span><br><small>Registry: ${caps.map(esc).join(" · ")}</small>`;
}
function applyModelDefaults(){
 const m=(S.boot.models||[]).find(x=>x.id===$("#modelSelect").value);if(!m)return;
 const c=m.config||{};
 if(c.default_steps!==undefined)$("#steps").value=c.default_steps;
 if(c.default_cfg!==undefined)$("#cfg").value=c.default_cfg;
}
function selectedModel(){return (S.boot?.models||[]).find(m=>m.id===$('#modelSelect')?.value)||(S.boot?.models||[])[0]||null}
function checkpointOptions(select,defaultPath,label){
 const previous=select.value;
 const list=S.boot.checkpoints||[];
 select.innerHTML=`<option value="">${esc(label)}${defaultPath?` · ${esc(defaultPath.split("/").pop())}`:""}</option>`+
   list.map(x=>`<option value="${esc(x.path)}">${esc(x.name)}</option>`).join("");
 if([...select.options].some(o=>o.value===previous))select.value=previous;
}
function updateCheckpointControls(){
 const m=selectedModel(),isSDXL=m?.provider==="sdxl";
 const cfg=m?.config||{};
 const normal=isSDXL&&["generate","edit","reference","multi_image"].includes(S.task);
 const inp=isSDXL&&S.task==="inpaint";
 $("#checkpointWrap").classList.toggle("hidden",!normal);
 $("#inpaintCheckpointWrap").classList.toggle("hidden",!inp);
 if(normal)checkpointOptions($("#checkpointSelect"),cfg.checkpoint||"","Model default");
 if(inp)checkpointOptions($("#inpaintCheckpointSelect"),cfg.inpaint_checkpoint||"","Model default inpaint");
}


function inputPolicy(){return {image:true,video:false,audio:false,max_images:S.task==='multi_image'?4:1,max_videos:0,max_audio:0}}
function updateInputPolicy(){
 const p=inputPolicy(),m=selectedModel(),parts=[];
 if(p.image)parts.push(`images${p.max_images?` ≤ ${p.max_images}`:""}`);
 if(p.video)parts.push(`videos${p.max_videos?` ≤ ${p.max_videos}`:""}`);
 if(p.audio)parts.push(`audio${p.max_audio?` ≤ ${p.max_audio}`:""}`);
 $("#referencePolicy").textContent=`${m?.name||"Auto"}: ${parts.join(" + ")||"no reference media declared"}. Files remain stored in the project even when another model cannot use them.`;
 const accept=[p.image?"image/*":"",p.video?"video/*":""].filter(Boolean).join(",");
 $("#referenceUpload").attr?.("accept",accept);
 if($("#referenceUpload"))$("#referenceUpload").setAttribute("accept",accept||"image/*,video/*");
 if($("#sourceUpload"))$("#sourceUpload").setAttribute("accept",accept||"image/*,video/*");
}
function updateStrengthHelp(){
 const enabled=S.task!=='generate';$('#strength').disabled=!enabled;
 $('#strengthHelp').textContent=enabled?'SDXL denoise: lower values preserve more of the input.':'Denoise is not used in text-to-image.';
}

const ratios={"1:1":[1024,1024],"16:9":[1344,768],"9:16":[768,1344],"4:3":[1152,864],"3:2":[1216,832],"2:3":[832,1216]};
$("#ratio").onchange=()=>{const v=$("#ratio").value;if(ratios[v]){[$("#width").value,$("#height").value]=ratios[v]}captureImageSettings()};
$("#strength").oninput=()=>{$("#strengthValue").textContent=(+$("#strength").value).toFixed(2);captureImageSettings()};
$$("[data-style]").forEach(b=>b.onclick=()=>{b.classList.toggle("active");if(b.classList.contains("active")){$("#prompt").value+=($("#prompt").value?", ":"")+b.dataset.style}});

async function uploadFile(file,role){
 if(!S.project)throw new Error("Open a project first");
 const fd=new FormData();fd.append("file",file);fd.append("role",role);
 const d=await api(`/api/projects/${S.project.id}/upload`,{method:"POST",body:fd});
 await openProjectNoPoll(S.project.id);return d.artifact;
}
function mediaAllowedForCurrentModel(art){
 const p=inputPolicy();
 if(art.type==="video")return !!p.video;
 if(art.type==="audio")return !!p.audio;
 return !!p.image
}
function enforceInputLimits(){
 const p=inputPolicy(),all=[S.sourceAsset,...S.references].filter(Boolean).map(artifactById).filter(Boolean);
 const ni=all.filter(a=>a.type==="image").length,nv=all.filter(a=>a.type==="video").length,na=all.filter(a=>a.type==="audio").length;
 if(p.max_images&&ni>p.max_images)throw new Error(`Selected model allows up to ${p.max_images} image input(s); currently ${ni}.`);
 if(p.max_videos!==undefined&&nv>p.max_videos)throw new Error(`Selected model allows up to ${p.max_videos} video input(s); currently ${nv}.`);
 if(p.max_audio!==undefined&&na>p.max_audio)throw new Error(`Selected model allows up to ${p.max_audio} audio input(s); currently ${na}.`);
 const bad=all.filter(a=>!mediaAllowedForCurrentModel(a));
 if(bad.length)throw new Error(`${selectedModel()?.name||"Selected model"} cannot use: ${bad.map(a=>a.metadata?.original_name||"#"+a.id.slice(0,8)).join(", ")}`);
}
$("#sourceUpload").onchange=async e=>{
 const files=[...e.target.files];if(!files.length)return;
 for(let i=0;i<files.length;i++){
   const useAsSource=!S.sourceAsset&&i===0;
   const a=await uploadFile(files[i],useAsSource?"source":"reference");
   if(useAsSource)S.sourceAsset=a.id;
   else if(!S.references.includes(a.id))S.references.push(a.id);
 }
 e.target.value="";renderInputs();
};
$("#maskUpload").onchange=async e=>{if(e.target.files[0]){const a=await uploadFile(e.target.files[0],"mask");S.maskAsset=a.id;e.target.value="";renderInputs()}};
$("#referenceUpload").onchange=async e=>{for(const f of e.target.files){const a=await uploadFile(f,"reference");if(!S.references.includes(a.id))S.references.push(a.id)}e.target.value="";renderInputs()};
$("#useActiveSource").onclick=()=>{if(S.activeAsset){S.sourceAsset=S.activeAsset;S.maskAsset="";renderInputs()}};
$("#clearSource").onclick=()=>{S.sourceAsset="";S.maskAsset="";S.mask.sourceId=null;renderInputs()};
$("#clearMask").onclick=()=>{S.maskAsset="";renderInputs()};
$("#addActiveReference").onclick=()=>{if(S.activeAsset&&!S.references.includes(S.activeAsset)){S.references.push(S.activeAsset);renderInputs()}};
function updateSourceResolutionNote(){
 const box=$("#sourceResolutionNote");if(!box)return;
 if(!["edit","inpaint"].includes(S.task)||!S.sourceAsset){box.classList.add("hidden");box.textContent="";return}
 const a=(S.project?.artifacts||[]).find(x=>x.id===S.sourceAsset),m=a?.metadata||{};
 const w=m.output_width||m.source_width||m.params?.width,h=m.output_height||m.source_height||m.params?.height;
 box.textContent=w&&h?`Source resolution ${w}×${h} · output will preserve the original source size.`:"Output will preserve the original source image size.";
 box.classList.remove("hidden");
}

function refRow(id,i){
 const a=artifactById(id);if(!a)return "";
 const preview=a.type==="video"?`<video src="${a.url}" muted playsinline preload="metadata"></video>`:`<img src="${a.url}" loading="lazy">`;
 const name=a.metadata?.original_name||`#${id.slice(0,8)}`;
 return `<div class="reference-row">${preview}<div><b>${esc(name)}</b><small>${esc(a.type||"image")} · input ${i+1}</small></div><div class="ref-actions"><button data-ref-up="${i}" ${i===0?"disabled":""}>↑</button><button data-ref-down="${i}" ${i===S.references.length-1?"disabled":""}>↓</button><button data-ref-remove="${i}">×</button></div></div>`;
}
function renderInputs(){
 const sa=artifactById(S.sourceAsset);
 $("#sourceChip").className=`asset-chip ${S.sourceAsset?"":"muted"}`;$("#sourceChip").textContent=sa?`${sa.type==="video"?"VIDEO":"IMAGE"} · ${sa.metadata?.original_name||"#"+sa.id.slice(0,8)}`:"None";
 $("#maskChip").className=`asset-chip ${S.maskAsset?"":"muted"}`;$("#maskChip").textContent=S.maskAsset?`#${S.maskAsset.slice(0,8)}`:"None";
 $("#referenceChips").innerHTML=S.references.length?S.references.map(refRow).join(""):'<span class="muted">No references.</span>';
 $$("[data-ref-remove]").forEach(b=>b.onclick=()=>{S.references.splice(+b.dataset.refRemove,1);renderInputs()});
 $$("[data-ref-up]").forEach(b=>b.onclick=()=>{const i=+b.dataset.refUp;if(i>0)[S.references[i-1],S.references[i]]=[S.references[i],S.references[i-1]];renderInputs()});
 $$("[data-ref-down]").forEach(b=>b.onclick=()=>{const i=+b.dataset.refDown;if(i<S.references.length-1)[S.references[i+1],S.references[i]]=[S.references[i],S.references[i+1]];renderInputs()});
 updateMaskEditorSource();updateSourceResolutionNote();updateInputPolicy();
}


function artifactById(id){return (S.project?.artifacts||[]).find(a=>a.id===id)}
const maskCanvas=$("#maskCanvas"),maskCtx=maskCanvas.getContext("2d"),maskImg=$("#maskSourceImage");
function maskSnapshot(){
 if(!maskCanvas.width||!maskCanvas.height)return;
 S.mask.history.push({data:maskCtx.getImageData(0,0,maskCanvas.width,maskCanvas.height),inverted:S.mask.inverted});
 if(S.mask.history.length>20)S.mask.history.shift();
}
function updateMaskStatus(){
 $("#maskPaintStatus").textContent=S.mask.dirty?"Mask modified":"No mask painted";
}
function updateMaskEditorSource(){
 if(S.task!=="inpaint")return;
 const a=artifactById(S.sourceAsset);
 $("#maskEditorEmpty").classList.toggle("hidden",!!a);
 maskImg.classList.toggle("hidden",!a);
 maskCanvas.classList.toggle("hidden",!a);
 if(!a)return;
 if(S.mask.sourceId===a.id)return;
 S.mask.sourceId=a.id;S.mask.history=[];S.mask.dirty=false;S.mask.inverted=false;S.maskAsset="";
 maskImg.onload=()=>{
   maskCanvas.width=maskImg.naturalWidth;maskCanvas.height=maskImg.naturalHeight;
   maskCtx.clearRect(0,0,maskCanvas.width,maskCanvas.height);
   updateMaskStatus();
 };
 maskImg.src=a.url+`?v=${Date.now()}`;
}
function maskPoint(ev){
 const r=maskCanvas.getBoundingClientRect(),t=ev.touches?.[0]||ev;
 return {x:(t.clientX-r.left)*(maskCanvas.width/r.width),y:(t.clientY-r.top)*(maskCanvas.height/r.height),
         scale:maskCanvas.width/r.width};
}
function drawMaskPoint(pt,last){
 const size=Number($("#maskBrushSize").value||55)*pt.scale;
 maskCtx.save();
 const remove=S.mask.inverted?(S.mask.mode==="brush"):(S.mask.mode==="erase");
 if(remove){
   maskCtx.globalCompositeOperation="destination-out";
   maskCtx.strokeStyle="rgba(0,0,0,1)";
 }else{
   maskCtx.globalCompositeOperation="source-over";
   maskCtx.strokeStyle="rgba(255,70,90,.60)";
 }
 maskCtx.lineWidth=size;maskCtx.lineCap="round";maskCtx.lineJoin="round";
 maskCtx.beginPath();maskCtx.moveTo(last?.x??pt.x,last?.y??pt.y);maskCtx.lineTo(pt.x,pt.y);maskCtx.stroke();maskCtx.restore();
 S.mask.dirty=true;updateMaskStatus();
}
let maskLast=null;
function maskStart(ev){if(!S.sourceAsset)return;ev.preventDefault();maskSnapshot();S.mask.drawing=true;maskLast=maskPoint(ev);drawMaskPoint(maskLast)}
function maskMove(ev){if(!S.mask.drawing)return;ev.preventDefault();const p=maskPoint(ev);drawMaskPoint(p,maskLast);maskLast=p}
function maskEnd(){S.mask.drawing=false;maskLast=null}
["mousedown","touchstart"].forEach(e=>maskCanvas.addEventListener(e,maskStart,{passive:false}));
["mousemove","touchmove"].forEach(e=>maskCanvas.addEventListener(e,maskMove,{passive:false}));
["mouseup","mouseleave","touchend","touchcancel"].forEach(e=>maskCanvas.addEventListener(e,maskEnd));
$("#maskBrushBtn").onclick=()=>{S.mask.mode="brush";$("#maskBrushBtn").classList.add("active");$("#maskEraseBtn").classList.remove("active")};
$("#maskEraseBtn").onclick=()=>{S.mask.mode="erase";$("#maskEraseBtn").classList.add("active");$("#maskBrushBtn").classList.remove("active")};
$("#maskUndoBtn").onclick=()=>{const snap=S.mask.history.pop();if(snap){maskCtx.putImageData(snap.data,0,0);S.mask.inverted=!!snap.inverted;S.mask.dirty=true;updateMaskStatus();updateMaskSemanticHelp()}};
$("#maskClearBtn").onclick=()=>{maskSnapshot();maskCtx.clearRect(0,0,maskCanvas.width,maskCanvas.height);S.mask.inverted=false;S.mask.dirty=true;S.maskAsset="";updateMaskStatus();updateMaskSemanticHelp();renderInputs()};
function updateMaskSemanticHelp(){
 $("#maskSemanticHelp").textContent=S.mask.inverted
   ?"INVERTED: Brush now UNMASKS; Eraser MASKS. Paint the face/body you want to preserve."
   :"Painted area = replaced area. Brush masks; Eraser unmasks. Invert swaps both the mask and tool semantics.";
 $("#maskPaintStatus").textContent=S.mask.inverted?"Mask inverted":(S.mask.dirty?"Mask modified":"No mask painted");
}
$("#maskInvertBtn").onclick=()=>{
 if(!maskCanvas.width)return;maskSnapshot();
 const d=maskCtx.getImageData(0,0,maskCanvas.width,maskCanvas.height);
 for(let i=0;i<d.data.length;i+=4){
   if(d.data[i+3]>10){d.data[i+3]=0}
   else{d.data[i]=255;d.data[i+1]=70;d.data[i+2]=90;d.data[i+3]=150}
 }
 maskCtx.putImageData(d,0,0);S.mask.inverted=!S.mask.inverted;S.mask.dirty=true;S.maskAsset="";updateMaskStatus();updateMaskSemanticHelp();
};
function maskHasPaint(){
 if(!maskCanvas.width)return false;
 const d=maskCtx.getImageData(0,0,maskCanvas.width,maskCanvas.height).data;
 for(let i=3;i<d.length;i+=4)if(d[i]>10)return true;
 return false;
}
async function savePaintedMask(){
 if(!maskHasPaint())throw new Error("Paint an area on the source image first.");
 const out=document.createElement("canvas");out.width=maskCanvas.width;out.height=maskCanvas.height;
 const o=out.getContext("2d"),src=maskCtx.getImageData(0,0,maskCanvas.width,maskCanvas.height),dst=o.createImageData(out.width,out.height);
 for(let i=0;i<src.data.length;i+=4){
   const v=src.data[i+3]>10?255:0;dst.data[i]=v;dst.data[i+1]=v;dst.data[i+2]=v;dst.data[i+3]=255;
 }
 o.putImageData(dst,0,0);
 const blob=await new Promise(res=>out.toBlob(res,"image/png"));
 const file=new File([blob],`mask_${Date.now()}.png`,{type:"image/png"});
 const art=await uploadFile(file,"mask");S.maskAsset=art.id;S.mask.dirty=false;updateMaskStatus();renderInputs();return art.id;
}
$("#maskSaveBtn").onclick=()=>savePaintedMask().catch(e=>alert(e.message));

function loraParams(){return S.loras.map(x=>({path:x.path,name:x.name,strength:+x.strength||1}))}
function renderLoraStack(){
 $("#loraStack").innerHTML=S.loras.length?S.loras.map((x,i)=>`<div class="lora-row"><span title="${esc(x.path)}">${esc(x.name)}</span><input type="number" min="-2" max="2" step=".05" value="${x.strength}" data-lora-strength="${i}"><button data-lora-remove="${i}">×</button></div>`).join(""):'<div class="empty-mini">No LoRAs selected.</div>';
 $$("[data-lora-strength]").forEach(e=>e.onchange=()=>S.loras[+e.dataset.loraStrength].strength=+e.value);$$("[data-lora-remove]").forEach(e=>e.onclick=()=>{S.loras.splice(+e.dataset.loraRemove,1);renderLoraStack()});
}
$("#addLoraBtn").onclick=async()=>{S.loraTarget="image";$("#loraModalTitle").textContent="Select image LoRA";try{const d=await api("/api/loras");applyLiveLoraInventory(d.loras||[])}catch(e){alert(e.message);return}$("#loraModal").classList.remove("hidden");renderLoraBrowser()};$("#closeLora").onclick=()=>$("#loraModal").classList.add("hidden");$("#loraSearch").oninput=renderLoraBrowser;
$("#imageWorkflowSelect").onchange=()=>updateImageWorkflowHelp();
$("#imageWorkflowPromptMode").onchange=()=>updateImageWorkflowHelp();
$("#imageWorkflowApplyParams").onchange=()=>updateImageWorkflowHelp();
$("#applyImageWorkflow").onclick=()=>applyImageWorkflow($("#imageWorkflowSelect").value);
$("#clearImageWorkflow").onclick=()=>clearActiveWorkflow();
$("#imagePresetSelect").onchange=()=>updateImagePresetHelp();
$("#applyImagePreset").onclick=()=>applyImagePreset($("#imagePresetSelect").value);
$("#resetImagePreset").onclick=()=>resetImagePresetToModelDefaults();
$("#setManualImageMode").onclick=()=>activateCleanImageMode();
$("#activateCleanImageMode").onclick=()=>activateCleanImageMode();
$("#focusWorkflowMode").onclick=()=>scrollToPanel("guidedWorkflowPanel");
$("#focusPresetMode").onclick=()=>scrollToPanel("quickPresetPanel");
$("#imageGoToWorkflow").onclick=()=>scrollToPanel("guidedWorkflowPanel");
$("#imageGoToPreset").onclick=()=>scrollToPanel("quickPresetPanel");
$("#imageAutoTestProfile").onchange=()=>updateImageAutoTestUi();
$("#imageAutoTestVarySeed").onchange=()=>updateImageAutoTestUi();
function attachImageUiMetadata(params,autoProfile=""){
 params.ui_task=S.task;
 params.ui_mode=S.imageUiMode||"simple";
 params.ui_quick_style=S.imageQuickStyle||"clean";
 params.ui_workflow_id=S.imageWorkflow?.id||"";
 params.ui_workflow_label=S.imageWorkflow?.label||"";
 params.ui_preset_id=S.imagePreset?.id||"";
 params.ui_preset_label=S.imagePreset?.label||"";
 if(autoProfile)params.ui_auto_test_profile=autoProfile;
 return params;
}
async function queueImageAutoTest(){
 if(window.CreatorLab)return window.CreatorLab.previewTests();
 alert("The comparison controls are still loading. Try again.");
}
$("#runImageAutoTestBtn").onclick=()=>queueImageAutoTest();
function renderLoraBrowser(){
 const q=$('#loraSearch').value.toLowerCase();
 $('#loraList').innerHTML=(S.boot?.loras||[]).filter(x=>x.name.toLowerCase().includes(q)).map((x,i)=>'<button data-lora-path="'+esc(x.path)+'">'+esc(x.name)+'</button>').join('')||'<div class="empty-mini">No SDXL LoRA found. Configure a LoRA directory in Setup.</div>';
 $$('#loraList [data-lora-path]').forEach(b=>b.onclick=()=>{const l=(S.boot.loras||[]).find(x=>x.path===b.dataset.loraPath);if(l&&!S.loras.some(x=>x.path===l.path))S.loras.push({...l,strength:1});renderLoraStack();$('#loraModal').classList.add('hidden')});
};


$("#runImageBtn").onclick=async()=>{
 try{
  if(!S.project)throw new Error("Open a project first.");
  const t=TASKS[S.task];if(!t)throw new Error(`Unknown image task: ${S.task}`);
  if(t.needsSource&&!S.sourceAsset)throw new Error("Select or upload a source image.");
  enforceInputLimits();
  if(t.needsMask&&!S.maskAsset){
    if(maskHasPaint())await savePaintedMask();
    else throw new Error("Paint the inpaint mask or upload a mask image.");
  }
  if(t.refs&&!S.references.length)throw new Error("Add at least one reference image.");

  const selected=$("#modelSelect").value;if(!selected)throw new Error("Select an image model.");
  captureImageSettings();
  const finalPrompt=composeImagePrompt($("#prompt").value);
  const finalNegative=composeImageNegative($("#negativePrompt").value);
  const params={
    width:+$("#width").value,height:+$("#height").value,seed:+$("#seed").value,
    steps:+$("#steps").value,cfg:+$("#cfg").value,batch:+$("#batch").value,
    quality:$("#quality").value.toLowerCase(),negative_prompt:finalNegative,
    strength:+$("#strength").value,source_artifact_id:S.sourceAsset||null,
    mask_artifact_id:S.maskAsset||null,reference_artifact_ids:[...S.references],
    loras:loraParams(),
    checkpoint_override:$("#checkpointWrap").classList.contains("hidden")?"":$("#checkpointSelect").value,
    inpaint_checkpoint_override:$("#inpaintCheckpointWrap").classList.contains("hidden")?"":$("#inpaintCheckpointSelect").value
  };
  attachImageUiMetadata(params);
  const btn=$("#runImageBtn"),old=btn.textContent;btn.disabled=true;btn.textContent="Adding to queue…";
  try{
    const d=await api("/api/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:S.project.id,tool:t.tool,model_id:selected,prompt:finalPrompt,params})});
    projectRecoveryUntil=Date.now()+120000;startPolling();showView("image");btn.textContent=`Queued ${d.batch||1} · add another`;
    generationFeedback('image','Job accepted. Queue and history update automatically.');
    openProjectNoPoll(S.project.id).catch(e=>{generationFeedback('image','Job accepted; reconnecting to its progress. Do not submit it again.',true);console.warn('[QUEUE REFRESH]',e)});
    setTimeout(()=>{btn.textContent=TASKS[S.task].action==="Generate"?"Add to queue":TASKS[S.task].action},1800);
  }finally{btn.disabled=false;if(btn.textContent==="Adding to queue…")btn.textContent=old}
 }catch(e){
  console.error("[IMAGE JOB]",e);generationFeedback('image',e.message,true);
  if(e.submissionUncertain){projectRecoveryUntil=Date.now()+120000;startPolling();}
 }
};

$("#newProjectBtn").onclick=()=>$("#projectModal").classList.remove("hidden");$("#cancelProject").onclick=()=>$("#projectModal").classList.add("hidden");$("#createProject").onclick=async()=>{const d=await api("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:$("#newProjectName").value,description:$("#newProjectDescription").value})});S.boot.projects.unshift(d.project);$("#projectModal").classList.add("hidden");await openProject(d.project.id)};

function artifactExists(id){return !!(S.project?.artifacts||[]).find(a=>a.id===id)}
function ratioFromSize(w,h){
 for(const [name,wh] of Object.entries(ratios)){if(Number(w)===wh[0]&&Number(h)===wh[1])return name}
 return "Custom";
}
function toolToTask(tool){return ({generate_image:"generate",edit_image:"edit",img2img:"edit",inpaint:"inpaint",reference:"reference",multi_image:"multi_image"})[tool]||"generate"}
function reuseArtifact(id){
 const a=artifactById(id);if(!a)return;
 const meta=a.metadata||{},p=meta.params||{},seed=actualSeed(a);

 const task=toolToTask(meta.tool);
 clearActiveWorkflow();
 S.sourceAsset=(p.source_artifact_id||meta.source_artifact_id||"");S.maskAsset=(p.mask_artifact_id||meta.mask_artifact_id||"");
 S.references=[...(p.reference_artifact_ids||meta.reference_artifact_ids||[])].filter(artifactExists);
 S.loras=(p.loras||[]).map(x=>({path:x.path||"",name:x.name||String(x.path||"").split("/").pop(),strength:Number(x.strength??x.weight??1)}));
 setTask(task);$("#prompt").value=meta.prompt||"";$("#negativePrompt").value=p.negative_prompt||"";
 const w=Number(p.width||meta.requested_width||meta.output_width||1024),h=Number(p.height||meta.requested_height||meta.output_height||1024);
 $("#width").value=w;$("#height").value=h;$("#ratio").value=ratioFromSize(w,h);
 if(seed!==null)$("#seed").value=seed;else if(p.seed!==undefined)$("#seed").value=p.seed;
 if(p.steps!==undefined&&p.steps!==null)$("#steps").value=p.steps;if(p.cfg!==undefined&&p.cfg!==null)$("#cfg").value=p.cfg;
 if(p.batch!==undefined&&p.batch!==null)$("#batch").value=p.batch;if(p.quality)$("#quality").value=String(p.quality).charAt(0).toUpperCase()+String(p.quality).slice(1);
 if(p.strength!==undefined&&p.strength!==null){$("#strength").value=p.strength;$("#strengthValue").textContent=Number(p.strength).toFixed(2)}
 populateModelSelect();if(meta.model_id&&[...$("#modelSelect").options].some(o=>o.value===meta.model_id))$("#modelSelect").value=meta.model_id;
 updateCapabilityNote();updateCheckpointControls();
 const cp=p.checkpoint_override||meta.checkpoint_override||"",icp=p.inpaint_checkpoint_override||meta.inpaint_checkpoint_override||"";
 if(!$("#checkpointWrap").classList.contains("hidden"))$("#checkpointSelect").value=cp;
 if(!$("#inpaintCheckpointWrap").classList.contains("hidden"))$("#inpaintCheckpointSelect").value=icp;
 renderLoraStack();renderInputs();renderActivePreview();captureImageSettings();showView("image");window.scrollTo({top:0,behavior:"smooth"});
}

async function deleteArtifact(id){
 const a=(S.project?.artifacts||[]).find(x=>x.id===id);if(!a)return;
 if(!confirm(`Delete artifact #${id.slice(0,8)} and its file?`))return;
 await api(`/api/artifacts/${id}`,{method:"DELETE"});
 if(S.activeAsset===id)S.activeAsset="";
 if(S.sourceAsset===id)S.sourceAsset="";
 if(S.maskAsset===id)S.maskAsset="";
 S.references=S.references.filter(x=>x!==id);
 await openProjectNoPoll(S.project.id);renderInputs();
}
function showDetails(title,obj){
 $("#detailsTitle").textContent=title;
 $("#detailsBody").textContent=JSON.stringify(obj,null,2);
 $("#detailsModal").classList.remove("hidden");
}
function showArtifactDetails(id){
 const a=artifactById(id);if(!a)return;
 showDetails(`Artifact #${id.slice(0,8)}`,{id:a.id,type:a.type,created_at:a.created_at,path:a.path,actual_seed:actualSeed(a),requested_seed:a.metadata?.params?.seed??null,metadata:a.metadata||{}});
}
$("#closeDetails").onclick=()=>$("#detailsModal").classList.add("hidden");

function renderValidationInto(box,v){box.className=`validation-box ${v?.ready?"ready":"bad"}`;box.innerHTML=v?`<b>${v.ready?"READY":"MISSING FILES"}</b>${(v.fields||[]).map(f=>`<div class="path-row"><code>${esc(f.field)}</code><span>${esc(f.value||"—")}</span><span class="${f.exists?"path-ok":"path-bad"}">${f.exists?"OK":(f.required?"MISS":"—")}</span></div>`).join("")}`:"Not validated"}

function renderModels(){
 $("#modelsGrid").innerHTML=(S.boot.models||[]).map(m=>`<div class="model-card"><div class="row"><b>${esc(m.name)}</b><span class="status-pill">${esc(m.validation?.status||m.status)}</span></div><small>${esc(m.group)}</small><div class="capability-list">${(m.capabilities||[]).map(c=>`<span>${esc(c)}</span>`).join("")}</div><button class="ghost" data-model="${m.id}">Configure</button></div>`).join("");$$("[data-model]").forEach(b=>b.onclick=()=>openModel(b.dataset.model));
}
async function openModel(id){const d=await api(`/api/models/${id}`);S.editingModel=d.model;const c=d.model.config||{};$("#modelModalTitle").textContent=d.model.name;$("#mc_runtime").value=c.runtime||"native_worker";$("#mc_device").value=c.device||"cuda";$("#mc_dtype").value=c.dtype||"float16";$("#mc_memory").value=c.memory_mode||"full_gpu";$("#mc_enabled").value=d.model.enabled?"1":"0";$("#mc_steps").value=c.default_steps??"";$("#mc_cfg").value=c.default_cfg??"";$("#modelCapabilities").innerHTML=(d.model.capabilities||[]).map(x=>`<span>${esc(x)}</span>`).join("");$("#modelPathFields").innerHTML=(MODEL_FIELDS[d.model.provider]||[]).map(f=>`<label>${esc(f)}<input data-mpath="${esc(f)}" value="${esc(c[f]||"")}"></label>`).join("");renderValidation(d.validation);$("#modelModal").classList.remove("hidden")}
function renderValidation(v){const box=$("#modelValidation");box.className=`validation-box ${v?.ready?"ready":"bad"}`;box.innerHTML=v?`<b>${v.ready?"READY":"MISSING FILES"}</b>${(v.fields||[]).map(f=>`<div class="path-row"><code>${esc(f.field)}</code><span>${esc(f.value||"—")}</span><span class="${f.exists?"path-ok":"path-bad"}">${f.exists?"OK":(f.required?"MISS":"—")}</span></div>`).join("")}`:"Not validated"}
$("#closeModel").onclick=()=>$("#modelModal").classList.add("hidden");$("#validateModel").onclick=async()=>renderValidation((await api(`/api/models/${S.editingModel.id}/validate`,{method:"POST"})).validation);$("#probeModel").onclick=async()=>{const p=(await api(`/api/models/${S.editingModel.id}/probe`,{method:"POST"})).probe;$("#modelValidation").className="validation-box";$("#modelValidation").innerHTML=`<b>RUNTIME PROBE</b><pre>${esc(JSON.stringify(p,null,2))}</pre>`};$("#saveModel").onclick=async()=>{const c={runtime:$("#mc_runtime").value,device:$("#mc_device").value,dtype:$("#mc_dtype").value,memory_mode:$("#mc_memory").value};$$("[data-mpath]").forEach(e=>c[e.dataset.mpath]=e.value.trim());if($("#mc_steps").value)c.default_steps=+$("#mc_steps").value;if($("#mc_cfg").value)c.default_cfg=+$("#mc_cfg").value;const d=await api(`/api/models/${S.editingModel.id}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:$("#mc_enabled").value==="1",config:c})});renderValidation(d.validation);const i=S.boot.models.findIndex(x=>x.id===d.model.id);if(i>=0)S.boot.models[i]={...d.model,validation:d.validation};renderModels();populateModelSelect()};

$("#unloadBtn").onclick=async()=>{await api("/api/runtime/image/unload",{method:"POST"});$("#runtimeState").textContent="Image runtime · GPU unloaded"};
loadUiSession();
bindImageSettingsMemory();


bootstrap().catch(e=>alert(e.message));

function applyLiveCheckpointInventory(checkpoints,defaultCheckpoint=''){
 if(S.boot)S.boot.checkpoints=checkpoints||[];
 if(S.boot&&defaultCheckpoint){const m=(S.boot.models||[]).find(x=>x.id==='sdxl');if(m){m.config=m.config||{};m.config.checkpoint=defaultCheckpoint}}
 updateCheckpointControls();
 if(S.identity?.boot){S.identity.boot.checkpoints=checkpoints||[];if(defaultCheckpoint)S.identity.boot.default_base_model=defaultCheckpoint;renderIdentityModelChoices(S.identity.boot)}
}
async function setCheckpointAvailability(id,enabled){
 const d=await api(`/api/model-hub/local/checkpoints/${encodeURIComponent(id)}/availability`,{
  method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});
 applyLiveCheckpointInventory(d.checkpoints||[]);
 window.dispatchEvent(new CustomEvent('checkpoint-availability-changed',{detail:d}));
 return d;
}

function applyLiveLoraInventory(loras){
 if(S.boot)S.boot.loras=loras||[];
 const paths=new Set((loras||[]).map(x=>x.path));
 // Disconnected/deleted LoRAs must not remain invisibly selected in this browser.
 S.loras=(S.loras||[]).filter(x=>paths.has(x.path));renderLoraStack();
 if(S.identity){S.identity.loras=(S.identity.loras||[]).filter(x=>paths.has(x.path));if(S.identity.boot)S.identity.boot.loras=loras||[];renderIdentityLoraStack();}
 if(!$("#loraModal")?.classList.contains("hidden"))renderLoraBrowser();
}
async function setLoraAvailability(id,enabled){
 const d=await api(`/api/model-hub/local/loras/${encodeURIComponent(id)}/availability`,{
  method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled})});
 applyLiveLoraInventory(d.loras||[]);
 window.dispatchEvent(new CustomEvent('lora-availability-changed',{detail:d}));
 return d;
}
let trainingRefreshPromise=null;
const deletedTrainingJobs=new Set();
function loadTraining(){
 if(!trainingRefreshPromise)trainingRefreshPromise=refreshTraining().finally(()=>{trainingRefreshPromise=null});
 return trainingRefreshPromise;
}
async function refreshTraining(){
 try{
  const d=await api("/api/training/bootstrap");d.jobs=(d.jobs||[]).filter(j=>!deletedTrainingJobs.has(j.id));S.training.boot=d;
  try{const live=await api("/api/loras");applyLiveLoraInventory(live.loras||[])}catch(e){console.warn("[LORA REFRESH]",e)}
  const rt=d.runtime||{};
  const rtState=!rt.ok?"OFFLINE":rt.compatibility_ok===false?"INCOMPATIBLE":rt.busy?"BUSY":"ONLINE";
  $("#trainingRuntimeState").textContent=`Training runtime · ${rtState}`;
  const rv=[];
  if(rt.pid)rv.push(`PID ${rt.pid}`);
  if(rt.gpu)rv.push(rt.gpu);
  if(rt.torch)rv.push(`torch ${rt.torch}`);
  if(rt.cuda)rv.push(`CUDA ${rt.cuda}`);
  if(rt.diffusers)rv.push(`diffusers ${rt.diffusers}`);
  if(rt.transformers)rv.push(`transformers ${rt.transformers}`);
  if(rt.busy&&rt.job_id)rv.push(`active ${rt.job_id}`);
  if(rt.last_event)rv.push(`last: ${rt.last_event}`);
  $("#trainingRuntimeDetails").innerHTML=`<b>${rt.ok?"Worker online":"Worker offline"}</b><small>${esc(rv.join(" · ")||rt.error||"No runtime details")}</small>${rt.compatibility_ok===false?`<small class="training-runtime-warning">${esc(rt.compatibility_reason||"Runtime incompatibility detected")}</small>`:""}`;
  $("#trainingRuntimeState").className=`status-pill ${(rt.ok&&rt.compatibility_ok!==false)?"":"bad"}`;
  if(d.default_sdxl&&!$("#trainingBaseModel").value)$("#trainingBaseModel").value=d.default_sdxl;
  const ds=d.datasets||[];
  if(window.ZetalvxDatasetWorkspace)await window.ZetalvxDatasetWorkspace.onBootstrap(d);
  renderTrainingDatasetLibrary(ds);
  renderTrainingLoras(d.loras||[]);
  renderTrainingFullUnets(d.full_unets||[]);
  renderTrainingFullModels(d.full_models||[]);
  renderTrainingJobs(d.jobs||[]);
  if(S.training.logJobId)loadTrainingLog(S.training.logJobId,true);
 }catch(e){
  $("#trainingRuntimeState").textContent="Training data error";
  $("#trainingRuntimeState").className="status-pill bad";
  if($("#trainingRuntimeDetails"))$("#trainingRuntimeDetails").innerHTML=`<b>Training bootstrap error</b><small class="training-runtime-warning">${esc(e.message)}</small>`;
  console.warn("[TRAINING]",e);
 }
}
async function loadTrainingDataset(id){
 if(window.ZetalvxDatasetWorkspace){await window.ZetalvxDatasetWorkspace.open(id);window.ZetalvxDatasetWorkspace.selectPage('dataset');return;}
 const r=await api(`/api/training/datasets/${id}`);S.training.dataset=r.dataset;
}
function renderTrainingDatasetLibrary(datasets){
 const box=$("#trainingDatasetLibrary");if(!box)return;
 box.innerHTML=(datasets||[]).length?(datasets||[]).map(d=>`<div class="training-library-item">
   <div class="training-library-main"><b>${esc(d.name||d.id)}</b><small>${d.item_count||0} images · trigger ${esc(d.trigger||"—")} · ${d.job_count||0} training job(s)</small><code>${esc(d.id)}</code></div>
   <div class="asset-actions"><button class="ghost small" data-dataset-open="${d.id}">Open</button><button class="danger ghost small" data-dataset-delete="${d.id}" data-dataset-name="${esc(d.name||d.id)}">Delete</button></div>
 </div>`).join(""):'<div class="empty-mini">No saved datasets.</div>';
 $$('[data-dataset-open]').forEach(b=>b.onclick=async()=>{$("#trainingDatasetSelect").value=b.dataset.datasetOpen;await loadTrainingDataset(b.dataset.datasetOpen);$("#trainingDatasetSelect").scrollIntoView({behavior:"smooth",block:"center"})});
 $$('[data-dataset-delete]').forEach(b=>b.onclick=async()=>{
   const id=b.dataset.datasetDelete,name=b.dataset.datasetName||id;
   if(!confirm(`Delete dataset "${name}" and all of its images/captions?\n\nTraining job history and already exported LoRAs are kept.`))return;
   try{await api(`/api/training/datasets/${id}`,{method:"DELETE"});if(S.training.dataset?.id===id)S.training.dataset=null;await loadTraining()}catch(e){alert(e.message)}
 });
}
function renderTrainingLoras(loras){
 S.training.loras=loras||[];const box=$("#trainingLoraLibrary");if(!box)return;
 box.innerHTML=S.training.loras.length?S.training.loras.map(l=>{
   const v=S.training.loraValidation[l.id],j=l.job||{};
   const vhtml=v?.checking?'<div class="validation-box">Checking tensors…</div>':v?`<div class="validation-box ${v.valid?"ready":"bad"}"><b>${v.valid?"VALID · finite weights":"INVALID · non-finite weights"}</b><small>${v.tensors||0} tensors · ${v.parameters||0} parameters · NaN ${v.nan_values||0} · Inf ${v.inf_values||0}</small>${v.error?`<small>${esc(v.error)}</small>`:""}</div>`:"";
   const sourceLabel=l.source==="training"?"registered Creator LoRA":l.source==="checkpoint_promoted"?"promoted training checkpoint":l.source==="job_output"?"historical final output":"library file";
   const recover=l.recoverable?`<button class="ghost small" data-lora-recover="${l.id}">Recover to Library</button>`:"";
   return `<div class="training-library-item training-lora-item">
     <div class="training-library-main"><b>${esc(l.name)}</b><small>${formatBytes(l.size_bytes)} · ${sourceLabel}${j.id?` · job ${esc(j.id)} · ${esc(j.status||"")}`:""}</small><code>${esc(l.path)}</code>${j.dataset_id?`<small>dataset ${esc(j.dataset_id)} · ${j.resolution||"?"}px · rank ${j.rank||"?"} · step ${j.step||0}/${j.max_steps||0}</small>`:""}${l.recoverable?`<small class="training-caption-warning">Registered library copy is missing. This final job artifact can be validated or recovered.</small>`:""}${j.historical_nonfinite_loss?`<small class="training-caption-warning">Previous training log contains NaN/Inf. Validate this LoRA before use.</small>`:""}</div>
     ${vhtml}
     ${l.catalog_id?`<label class="check-row"><input type="checkbox" data-lora-availability="${l.catalog_id}" ${l.generation_enabled?'checked':''}> <span>Available in Generate</span></label>`:''}
     <div class="asset-actions"><button class="ghost small" data-lora-validate="${l.id}">Validate weights</button>${recover}<a class="button-link ghost small" data-safe-download href="/api/training/loras/${l.id}/download">Download</a><button class="ghost small" data-lora-path="${l.id}">Copy path</button><button class="danger ghost small" data-lora-delete="${l.id}" data-lora-original="${l.recoverable?'1':'0'}" data-lora-name="${esc(l.name)}">Delete</button></div>
   </div>`
 }).join(""):'<div class="empty-mini">No SDXL LoRA .safetensors files found.</div>';
 $$('[data-lora-availability]').forEach(b=>b.onchange=async()=>{const enabled=b.checked;b.disabled=true;try{await setLoraAvailability(b.dataset.loraAvailability,enabled);await loadTraining()}catch(e){b.checked=!enabled;alert(e.message)}finally{b.disabled=false}});
 $$('[data-lora-validate]').forEach(b=>b.onclick=async()=>{
   const id=b.dataset.loraValidate;S.training.loraValidation[id]={checking:true};renderTrainingLoras(S.training.loras);
   try{const r=await api(`/api/training/loras/${id}/validate`,{method:"POST"});S.training.loraValidation[id]=r.validation||{valid:false,error:"No validation result"}}catch(e){S.training.loraValidation[id]={valid:false,error:e.message}}
   renderTrainingLoras(S.training.loras);
 });
 $$('#trainingLoraLibrary [data-lora-path]').forEach(b=>b.onclick=async()=>{const l=S.training.loras.find(x=>x.id===b.dataset.loraPath);if(!l)return;try{await navigator.clipboard.writeText(l.path);b.textContent="Copied"}catch(_){alert(l.path)}});
 $$('[data-lora-recover]').forEach(b=>b.onclick=async()=>{
   const id=b.dataset.loraRecover;
   try{await api(`/api/training/loras/${id}/recover`,{method:"POST"});delete S.training.loraValidation[id];await loadTraining()}catch(e){alert(e.message)}
 });
 $$('[data-lora-delete]').forEach(b=>b.onclick=async()=>{
   const id=b.dataset.loraDelete,name=b.dataset.loraName||id;
   const consequence=b.dataset.loraOriginal==='1'?'This is the original final output of the training job. Only this file is deleted; checkpoints, existing library copies and training history are kept.':'Only this library file is deleted. Training history, checkpoints and the original final artifact are kept. To keep this file, turn off Available in Generate instead.';
   if(!confirm(`Delete LoRA output "${name}"?\n\n${consequence}`))return;
   try{await api(`/api/training/loras/${id}`,{method:"DELETE"});delete S.training.loraValidation[id];await loadTraining()}catch(e){alert(e.message)}
 });
}
function trainingValidationHtml(v,label="weights"){
 if(!v)return "";
 if(v.checking)return '<div class="validation-box">Checking tensors…</div>';
 return `<div class="validation-box ${v.valid?"ready":"bad"}"><b>${v.valid?`VALID · finite ${label}`:`INVALID · non-finite ${label}`}</b><small>${v.files||1} file(s) · ${v.tensors||0} tensors · ${v.parameters||0} parameters · NaN ${v.nan_values||0} · Inf ${v.inf_values||0}</small>${v.error?`<small>${esc(v.error)}</small>`:""}</div>`;
}
function renderTrainingFullUnets(unets){
 S.training.fullUnets=unets||[];const box=$("#trainingFullUnetLibrary");if(!box)return;
 box.innerHTML=S.training.fullUnets.length?S.training.fullUnets.map(u=>{
  const v=S.training.fullUnetValidation[u.id],j=u.job||{};
  return `<div class="training-library-item">
   <div class="training-library-main"><b>${esc(u.name)}</b><small>${formatBytes(u.size_bytes)} · job ${esc(j.id||"—")} · ${j.resolution||"?"}px · step ${j.step||0}/${j.max_steps||0}</small><code>${esc(u.path)}</code></div>
   ${trainingValidationHtml(v,"UNet weights")}
   <div class="asset-actions"><button class="ghost small" data-unet-validate="${u.id}">Validate</button><a class="button-link ghost small" data-safe-download href="/api/training/full-unets/${u.id}/download">Download ZIP</a><button class="ghost small" data-unet-path="${u.id}">Copy path</button><button class="danger ghost small" data-unet-delete="${u.id}" data-unet-name="${esc(u.name)}">Delete</button></div>
  </div>`
 }).join(""):'<div class="empty-mini">No full UNet outputs.</div>';
 $$('[data-unet-validate]').forEach(b=>b.onclick=async()=>{const id=b.dataset.unetValidate;S.training.fullUnetValidation[id]={checking:true};renderTrainingFullUnets(S.training.fullUnets);try{const r=await api(`/api/training/full-unets/${id}/validate`,{method:"POST"});S.training.fullUnetValidation[id]=r.validation}catch(e){S.training.fullUnetValidation[id]={valid:false,error:e.message}}renderTrainingFullUnets(S.training.fullUnets)});
 $$('[data-unet-path]').forEach(b=>b.onclick=async()=>{const x=S.training.fullUnets.find(v=>v.id===b.dataset.unetPath);if(!x)return;try{await navigator.clipboard.writeText(x.path);b.textContent="Copied"}catch(_){alert(x.path)}});
 $$('[data-unet-delete]').forEach(b=>b.onclick=async()=>{const id=b.dataset.unetDelete;if(!confirm(`Delete Full UNet output "${b.dataset.unetName||id}"?\n\nComplete SDXL model and training history are kept.`))return;try{await api(`/api/training/full-unets/${id}`,{method:"DELETE"});delete S.training.fullUnetValidation[id];await loadTraining()}catch(e){alert(e.message)}});
}
function renderTrainingFullModels(models){
 S.training.fullModels=models||[];const box=$("#trainingFullModelLibrary");if(!box)return;
 box.innerHTML=S.training.fullModels.length?S.training.fullModels.map(m=>{
  const v=S.training.fullValidation[m.id],j=m.job||{},mf=m.manifest||{};
  return `<div class="training-library-item">
   <div class="training-library-main"><b>${esc(m.name)}</b><small>${formatBytes(m.size_bytes)} · complete Diffusers SDXL${j.id?` · job ${esc(j.id)}`:""}</small><code>${esc(m.path)}</code><small>base ${esc(mf.base_model||j.base_model||"—")} · dataset ${esc(mf.dataset_id||j.dataset_id||"—")} · ${mf.resolution||j.resolution||"?"}px · step ${mf.step||j.step||0}</small></div>
   ${trainingValidationHtml(v,"model weights")}
   <div class="asset-actions"><button class="ghost small" data-full-validate="${m.id}">Validate model</button><a class="button-link ghost small" data-safe-download href="/api/training/full-models/${m.id}/download">Download ZIP</a><button class="ghost small" data-full-path="${m.id}">Copy path</button><button class="danger ghost small" data-full-delete="${m.id}" data-full-name="${esc(m.name)}">Delete</button></div>
  </div>`
 }).join(""):'<div class="empty-mini">No complete SDXL models.</div>';
 $$('[data-full-validate]').forEach(b=>b.onclick=async()=>{const id=b.dataset.fullValidate;S.training.fullValidation[id]={checking:true};renderTrainingFullModels(S.training.fullModels);try{const r=await api(`/api/training/full-models/${id}/validate`,{method:"POST"});S.training.fullValidation[id]=r.validation}catch(e){S.training.fullValidation[id]={valid:false,error:e.message}}renderTrainingFullModels(S.training.fullModels)});
 $$('[data-full-path]').forEach(b=>b.onclick=async()=>{const x=S.training.fullModels.find(v=>v.id===b.dataset.fullPath);if(!x)return;try{await navigator.clipboard.writeText(x.path);b.textContent="Copied"}catch(_){alert(x.path)}});
 $$('[data-full-delete]').forEach(b=>b.onclick=async()=>{const id=b.dataset.fullDelete;if(!confirm(`Delete complete SDXL model "${b.dataset.fullName||id}"?\n\nTraining history, checkpoints and final UNet are kept.`))return;try{await api(`/api/training/full-models/${id}`,{method:"DELETE"});delete S.training.fullValidation[id];await loadTraining()}catch(e){alert(e.message)}});
}
function applyTrainingProfile(){
 const mode=$("#trainingMode").value,profile=$("#trainingProfile").value;
 $("#trainingRankWrap").classList.toggle("hidden",mode!=="lora");$("#trainingAlphaWrap").classList.toggle("hidden",mode!=="lora");
 if(profile==="local"){
   $("#trainingResolution").value=mode==="lora"?"768":"512";$("#trainingSteps").value=mode==="lora"?"300":"100";
   $("#trainingSaveEvery").value="100";$("#trainingRank").value="16";$("#trainingAlpha").value="16";$("#trainingLR").value=mode==="lora"?"0.0001":"0.00001";
 }else if(profile==="server"){
   $("#trainingResolution").value="1024";$("#trainingSteps").value="1000";$("#trainingSaveEvery").value=mode==="full"?"250":"100";
   $("#trainingRank").value="32";$("#trainingAlpha").value="32";$("#trainingLR").value=mode==="lora"?"0.0001":"0.00001";
 }
 $("#trainingModeHelp").innerHTML=mode==="lora"
   ?"<b>LoRA</b><br>Recommended first test on the RTX 3090. Only adapter weights are trained and the final .safetensors is automatically registered under models/loras/SDXL."
   :"<b>Full SDXL · Server / Advanced</b><br>Fine-tunes the complete SDXL UNet with FP32 master weights, then automatically exports both the trained UNet and a complete Diffusers SDXL model under models/SDXL/trained. Text encoders and VAE stay frozen. Intended for high-VRAM servers; Local 24 GB is smoke-test only. Full exact-resume checkpoints are large, so the Server preset saves every 250 steps.";
}
$("#trainingMode")?.addEventListener("change",applyTrainingProfile);$("#trainingProfile")?.addEventListener("change",applyTrainingProfile);
$("#trainingStart")?.addEventListener("click",async()=>{
 try{
  const did=window.ZetalvxDatasetWorkspace?await window.ZetalvxDatasetWorkspace.prepareTraining():$("#trainingDatasetSelect").value;
  if(!did)throw new Error("Select a training dataset.");
  const mode=$("#trainingMode").value;
  if(mode==="full"&&!confirm("Full SDXL fine-tuning trains every UNet parameter and then exports a complete model. It requires much more VRAM/storage than LoRA. Continue?"))return;
  const payload={name:`sdxl_${mode}_${Date.now()}`,dataset_id:did,base_model:$("#trainingBaseModel").value,mode,
   resolution:+$("#trainingResolution").value,max_steps:+$("#trainingSteps").value,save_every:+$("#trainingSaveEvery").value,
   learning_rate:+$("#trainingLR").value,rank:+$("#trainingRank").value,alpha:+$("#trainingAlpha").value,
   gradient_accumulation:+$("#trainingGradAccum").value,gradient_checkpointing:$("#trainingGradCheckpoint").checked,
   optimizer:mode==="full"?"adamw8bit":"adamw",seed:+$("#trainingSeed").value};
  const b=$("#trainingStart");b.disabled=true;b.textContent="Starting training…";
  const result=await api("/api/training/jobs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  await loadTraining();startTrainingPoll();window.ZetalvxDatasetWorkspace?.selectPage('results',true);
  if(result.job?.status==='worker_offline')throw new Error(result.job.error||'Training worker offline; see the job log.');
 }catch(e){alert(e.message)}
 finally{$("#trainingStart").disabled=false;$("#trainingStart").textContent="Start SDXL training"}
});
function trainingPhaseLabel(j){
 const phase=String(j.phase||j.status||"");
 const map={queued:"Queued",starting:"Starting",loading_model:"Loading SDXL model",caching_prompts:"Encoding captions",caching_latents:"Caching image latents",preparing_optimizer:"Preparing optimizer",training:"Training",saving_final:"Saving final weights",exporting_full_model:"Exporting complete SDXL model",completed:"Completed",stopped:"Stopped",failed:"Failed",interrupted:"Interrupted",worker_offline:"Worker offline"};
 let x=map[phase]||phase||"Unknown";
 if(["caching_prompts","caching_latents"].includes(phase)&&j.cache_total)x+=` · ${j.cache_current||0}/${j.cache_total}`;
 return x;
}
function trainingAgo(ts){
 if(!ts)return "—";const sec=Math.max(0,Date.now()/1000-Number(ts));
 if(sec<5)return "now";if(sec<60)return `${Math.round(sec)}s ago`;if(sec<3600)return `${Math.round(sec/60)}m ago`;return new Date(Number(ts)*1000).toLocaleString();
}
async function loadTrainingLog(jid,silent=false){
 if(!jid)return;
 S.training.logJobId=jid;
 const panel=$("#trainingLogPanel"),pre=$("#trainingLogText"),title=$("#trainingLogTitle"),meta=$("#trainingLogMeta");
 panel?.classList.remove("hidden");if(title)title.textContent=`Training log · ${jid}`;
 try{
   const r=await api(`/api/training/jobs/${jid}/log?lines=240`),l=r.log||{};
   if(meta)meta.textContent=l.exists?`${l.path} · live tail`:`No per-job log yet · global ${l.global_log_path||""}`;
   if(pre)pre.textContent=l.text||l.global_tail||"No log lines available yet.";
   if(pre)pre.scrollTop=pre.scrollHeight;
 }catch(e){if(!silent&&pre)pre.textContent=e.message}
}
function renderTrainingJobs(jobs){
 const box=$("#trainingJobs");if(!box)return;
 // Preserve expanded checkpoint drawers across the 3-second live refresh.
 // The whole job list is re-rendered on every poll, so native <details> state would otherwise be lost.
 [...box.querySelectorAll("details.training-checkpoints[data-job-id]")].forEach(d=>{S.training.checkpointOpen[d.dataset.jobId]=d.open});
 const datasetIndex=Object.fromEntries((S.training.boot?.datasets||[]).map(d=>[d.id,d]));
 box.innerHTML=jobs.length?jobs.map(j=>{
  const p=Math.round(Number(j.progress||0)*100),cps=j.checkpoints||[],last=cps[cps.length-1],phase=trainingPhaseLabel(j);
  const canResume=["stopped","failed","worker_offline","interrupted"].includes(j.status)&&last;
  const canContinue=!["running","queued","starting"].includes(j.status)&&last;
  const ds=datasetIndex[j.dataset_id]||{};
  const openAttr=S.training.checkpointOpen[j.id]?" open":"";
  const checkpointHtml=cps.length?`<details class="training-checkpoints" data-job-id="${j.id}"${openAttr}><summary>${cps.length} checkpoint${cps.length===1?"":"s"} · inspect / resume / continue</summary>${cps.map(cp=>{
    const key=`${j.id}:${cp.step}`,v=S.training.checkpointValidation[key];
    const promoted=!!cp.promoted_lora_path;
    return `<div class="training-checkpoint-row"><div><b>Step ${cp.step}</b><small>${formatBytes(cp.size_bytes||0)} · ${j.mode==="lora"?"LoRA snapshot + resume with optimizer state state":"exact full-training resume snapshot"}</small><code>${esc(cp.path)}</code></div>${trainingValidationHtml(v,"checkpoint weights")}<div class="asset-actions"><button class="ghost small" data-cp-validate="${j.id}" data-cp-step="${cp.step}">Validate</button>${j.mode==="lora"?(promoted?`<button class="ghost small" disabled>Already in Library</button>`:`<button class="ghost small" data-cp-promote="${j.id}" data-cp-step="${cp.step}">Add to My LoRA</button>`):""}<a class="button-link ghost small" data-safe-download href="/api/training/jobs/${j.id}/checkpoints/${cp.step}/download">Download</a>${canResume?`<button class="ghost small" data-cp-resume="${j.id}" data-cp-step="${cp.step}" data-cp-path="${esc(cp.path)}">Resume exact here</button>`:""}${canContinue?`<button class="ghost small" data-cp-continue="${j.id}" data-cp-step="${cp.step}" data-cp-path="${esc(cp.path)}">Continue from here…</button>`:""}<button class="danger ghost small" data-cp-delete="${j.id}" data-cp-step="${cp.step}">Delete</button></div></div>`
  }).join("")}</details>`:"";
  return `<div class="training-job training-status-${esc(j.status||"unknown")}">
    <div class="training-job-head"><div><b>${esc(j.name||j.id)} · ${esc(j.mode==="full"?"FULL SDXL":String(j.mode||"").toUpperCase())}</b><small>${esc(j.status||"")} · ${esc(phase)}</small></div><span>${p}%</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${p}%"></div></div>
    <div class="training-live-grid">
      <span><b>Step</b>${j.step||0}/${j.max_steps||0}</span>
      <span><b>Loss</b>${Number.isFinite(Number(j.loss))&&j.loss!==null?Number(j.loss).toFixed(6):"—"}</span>
      <span><b>LR</b>${j.learning_rate!==undefined?Number(j.learning_rate).toExponential(2):"—"}</span>
      <span><b>Elapsed</b>${j.elapsed_seconds?formatDuration(j.elapsed_seconds):"0s"}</span>
      <span><b>ETA</b>${j.eta_seconds?formatDuration(j.eta_seconds):"—"}</span>
      <span><b>Heartbeat</b>${trainingAgo(j.heartbeat_at||j.updated_at)}</span>
    </div>
    ${j.phase_detail?`<div class="training-phase-detail">${esc(j.phase_detail)}</div>`:""}
    <div class="training-job-meta"><span>job ${esc(j.id)}${j.worker_pid?` · worker PID ${esc(j.worker_pid)}`:""}</span><span>${last?`checkpoint ${last.step}`:"no checkpoint yet"}</span></div>
    <div class="training-job-meta"><span>dataset ${esc(ds.name||j.dataset_id||"—")} · ${Number(ds.item_count||0)} images</span><span>trigger ${esc(ds.trigger||"—")}</span></div>
    ${j.continuation_of?`<div class="training-phase-detail">Continuation of job ${esc(j.continuation_of)}${j.continuation_from_step?` · source step ${esc(j.continuation_from_step)}`:""}</div>`:""}
    ${j.caption_adjusted?`<div class="training-caption-warning">CLIP caption fit: ${j.caption_adjusted} caption(s) were shortened only for the training encoder to stay within ${j.caption_limit||77} tokens. Saved caption text and the selected trigger placement are preserved.</div>`:""}${j.caption_over_limit?`<div class="training-caption-warning">CLIP caption warning: ${j.caption_over_limit} caption(s) still exceed ${j.caption_limit||77} tokens.</div>`:""}
    ${j.error?`<pre class="training-error">${esc(j.error)}</pre>`:""}
    ${j.nonfinite_loss_detected||j.nonfinite_gradient_detected?`<div class="validation-box bad"><b>Numerical failure</b><small>Training stopped before exporting invalid weights.</small></div>`:""}
    ${j.historical_nonfinite_loss?`<div class="validation-box bad"><b>Legacy numerical warning</b><small>${esc(j.training_health_warning||"Training log contains NaN/Inf. Validate the exported LoRA before use.")}</small></div>`:""}
    ${j.registered_lora?`<div class="validation-box ${j.registered_lora_exists===false?"bad":"ready"}"><b>${j.registered_lora_exists===false?"LoRA file removed / missing":"LoRA registered"}</b><code>${esc(j.registered_lora)}</code></div>`:""}
    ${j.final_unet?`<div class="validation-box ${j.final_unet_exists===false?"bad":"ready"}"><b>${j.final_unet_exists===false?"Final UNet removed / missing":"Final UNet exported"}</b><code>${esc(j.final_unet)}</code></div>`:""}
    ${j.registered_full_model?`<div class="validation-box ${j.registered_full_model_exists===false?"bad":"ready"}"><b>${j.registered_full_model_exists===false?"Complete SDXL model removed / missing":"Complete SDXL model registered"}</b><code>${esc(j.registered_full_model)}</code></div>`:""}
    ${checkpointHtml}
    <div class="asset-actions">
      <button data-train-log="${j.id}" class="ghost">View log</button>
      ${["completed","failed","stopped","cancelled","interrupted","worker_offline"].includes(j.status)?`<button data-train-delete="${j.id}" data-train-name="${esc(j.name||j.id)}" class="danger">Delete training</button>`:""}
      ${j.status==="running"?`<button data-train-stop="${j.id}" class="danger">Stop & Save</button>`:""}
      ${canResume?`<button data-train-resume="${j.id}">Resume exact latest</button>`:""}
      ${canContinue?`<button data-train-continue="${j.id}">Continue latest…</button>`:""}
      ${last?`<button data-train-path="${esc(last.path)}">Latest checkpoint path</button>`:""}
    </div>
  </div>`
 }).join(""):'<div class="empty-state">No training jobs yet.</div>';
 $$('[data-train-delete]').forEach(b=>b.onclick=async()=>{
  const jid=b.dataset.trainDelete;
  const tr=s=>window.ZI18n?.t(s)||s;
  if(!confirm(`${tr('Delete training permanently?')}\n${b.dataset.trainName||jid}\n\n${tr('This removes its history card, logs, remaining checkpoints/resume state and local outputs inside the job folder. You cannot resume this job afterward.')}\n\n${tr('The dataset and LoRAs/models already exported separately in the model library are kept.')}`))return;
  b.disabled=true;
  try{
   await api(`/api/training/jobs/${encodeURIComponent(jid)}`,{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})});
   deletedTrainingJobs.add(jid);delete S.training.checkpointOpen[jid];
   for(const k of Object.keys(S.training.checkpointValidation))if(k.startsWith(jid+':'))delete S.training.checkpointValidation[k];
   if(S.training.logJobId===jid){S.training.logJobId=null;$('#trainingLogPanel')?.classList.add('hidden');}
   if(S.training.boot)S.training.boot.jobs=(S.training.boot.jobs||[]).filter(j=>j.id!==jid);
   renderTrainingJobs(S.training.boot?.jobs||[]);await loadTraining();
  }catch(e){alert(e.message)}finally{b.disabled=false}
 });
 $$('[data-train-log]').forEach(b=>b.onclick=()=>loadTrainingLog(b.dataset.trainLog));
 $$('[data-train-stop]').forEach(b=>b.onclick=async()=>{await api(`/api/training/jobs/${b.dataset.trainStop}/stop`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});await loadTraining()});
 $$('[data-train-resume]').forEach(b=>b.onclick=async()=>{if(!confirm("Resume this interrupted/stopped job from its latest checkpoint? Optimizer and scheduler state are restored, and the job continues toward its original max steps."))return;await api(`/api/training/jobs/${b.dataset.trainResume}/resume`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});await loadTraining();startTrainingPoll()});
 $$('[data-train-continue]').forEach(b=>b.onclick=async()=>{const n=Number(prompt("Additional training steps for the new continuation job:","200"));if(!Number.isFinite(n)||n<1)return;await api(`/api/training/jobs/${b.dataset.trainContinue}/continue`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({additional_steps:Math.floor(n)})});await loadTraining();startTrainingPoll()});
 $$('[data-train-path]').forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(b.dataset.trainPath);b.textContent="Copied"}catch(_){alert(b.dataset.trainPath)}});
 $$('details.training-checkpoints[data-job-id]').forEach(d=>d.addEventListener("toggle",()=>{S.training.checkpointOpen[d.dataset.jobId]=d.open}));
 $$('[data-cp-validate]').forEach(b=>b.onclick=async()=>{const jid=b.dataset.cpValidate,step=+b.dataset.cpStep,key=`${jid}:${step}`;S.training.checkpointValidation[key]={checking:true};renderTrainingJobs(S.training.boot?.jobs||jobs);try{const r=await api(`/api/training/jobs/${jid}/checkpoints/${step}/validate`,{method:"POST"});S.training.checkpointValidation[key]=r.validation}catch(e){S.training.checkpointValidation[key]={valid:false,error:e.message}}renderTrainingJobs(S.training.boot?.jobs||jobs)});
 $$('[data-cp-resume]').forEach(b=>b.onclick=async()=>{const jid=b.dataset.cpResume,step=+b.dataset.cpStep,path=b.dataset.cpPath;if(!confirm(`Resume the SAME job exactly from step ${step}?\n\nOptimizer + scheduler state are restored. Any later checkpoints/final output belonging to this job may be overwritten as training re-runs toward the original max steps.`))return;try{await api(`/api/training/jobs/${jid}/resume`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({checkpoint_path:path})});await loadTraining();startTrainingPoll()}catch(e){alert(e.message)}});
 $$('[data-cp-continue]').forEach(b=>b.onclick=async()=>{const jid=b.dataset.cpContinue,step=+b.dataset.cpStep,path=b.dataset.cpPath;const n=Number(prompt(`Continue from checkpoint step ${step}. Additional steps for the NEW branch job:`,`200`));if(!Number.isFinite(n)||n<1)return;try{await api(`/api/training/jobs/${jid}/continue`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({additional_steps:Math.floor(n),checkpoint_path:path})});await loadTraining();startTrainingPoll()}catch(e){alert(e.message)}});
 $$('[data-cp-promote]').forEach(b=>b.onclick=async()=>{try{await api(`/api/training/jobs/${b.dataset.cpPromote}/checkpoints/${+b.dataset.cpStep}/promote`,{method:"POST"});await loadTraining()}catch(e){alert(e.message)}});
 $$('[data-cp-delete]').forEach(b=>b.onclick=async()=>{const jid=b.dataset.cpDelete,step=+b.dataset.cpStep;if(!confirm(`Delete checkpoint step ${step}?\n\nThis removes its weights and resume state. Resuming from this step will no longer be possible. LoRAs already copied to My LoRA, the final output and job history are kept.`))return;try{await api(`/api/training/jobs/${jid}/checkpoints/${step}`,{method:"DELETE"});delete S.training.checkpointValidation[`${jid}:${step}`];await loadTraining()}catch(e){alert(e.message)}});
}
$("#trainingLogRefresh")?.addEventListener("click",()=>S.training.logJobId&&loadTrainingLog(S.training.logJobId));
$("#trainingLogClose")?.addEventListener("click",()=>{S.training.logJobId=null;$("#trainingLogPanel")?.classList.add("hidden")});
function startTrainingPoll(){clearInterval(S.training.poll);S.training.poll=setInterval(async()=>{if(!$("#view-training")?.classList.contains("active"))return;await loadTraining()},3000)}
$("#trainingRefresh")?.addEventListener("click",loadTraining);


function identityMode(){return S.identity.mode||"face_swap"}
function placeIdentitySdxlPanel(){
 const panel=$('#identitySdxlModelPanel');if(!panel)return;
 const instant=identityMode()==='instantid';
 const target=instant?$('#identityInstantidModelSlot'):$('#identitySwapRefineModelSlot');
 if(target&&panel.parentElement!==target)target.appendChild(panel);
 const title=$('#identitySdxlPanelTitle'),help=$('#identitySdxlPanelHelp');
 if(title)title.textContent=instant?'SDXL generation model':'SDXL refinement model';
 if(help)help.textContent=instant?'InstantID generates through the selected SDXL checkpoint.':'This checkpoint is used only for the optional Img2Img refinement after the face swap.';
}
function updateIdentitySwapRefine(){
 const swap=identityMode()==='face_swap',on=!!$('#identitySwapRefine')?.checked;
 placeIdentitySdxlPanel();
 $('#identitySwapRefineControls')?.classList.toggle('hidden',!(swap&&on));
 $('#identitySdxlModelPanel')?.classList.toggle('hidden',!(identityMode()==='instantid'||(swap&&on)));
}
function setIdentityMode(mode){
 S.identity.mode=mode==="instantid"?"instantid":"face_swap";
 $$('[data-identity-mode]').forEach(b=>b.classList.toggle('active',b.dataset.identityMode===S.identity.mode));
 const swap=S.identity.mode==="face_swap";
 $("#identityBaseWrap")?.classList.remove("hidden");
 $("#identityPoseWrap")?.classList.toggle("hidden",swap);
 $("#identityGenerativeControls")?.classList.toggle("hidden",swap);
 $("#identitySwapInfo")?.classList.toggle("hidden",!swap);
 if($("#identityInputTitle"))$("#identityInputTitle").textContent=swap?"Target image + source face":"Primary face + optional pose";
 // Labels and ordering are updated without replacing selected file inputs.
 if($("#identityParamTitle"))$("#identityParamTitle").textContent=swap?"True Face Swap":"InstantID generation";
 if($("#identityModeHelp"))$("#identityModeHelp").textContent=swap?"True Face Swap uses the first face reference as source identity and replaces the selected detected face in the base image. Optional SDXL Refine runs only after the deterministic swap.":"The first reference is the primary identity. Base is the Img2Img starting image when Img2Img is selected; Pose controls landmarks when supplied.";
 updateIdentitySubmitButtons();
 updateIdentityGenerationMode();updateIdentitySwapRefine();updateIdentitySweepCount();
}
function updateIdentityGenerationMode(){
 const gm=$("#identityGenerationMode")?.value||"txt2img";
 updateIdentityInputHelp();
 $("#identityImg2ImgNote")?.classList.toggle("hidden",identityMode()!=="instantid"||gm!=="img2img");
 if($("#identityDenoise"))$("#identityDenoise").disabled=identityMode()!=="instantid"||gm!=="img2img";
 updateIdentitySweepCount();
}
function identityFilePreview(input,box,multiple=false){
 const el=$(box);if(!el)return;const files=[...(input?.files||[])];
 const emptyText=el.dataset.emptyText||'No image selected.';
 el.classList.toggle('identity-preview-filled',files.length>0);
 if(!files.length){el.innerHTML=`<span class="muted">${esc(emptyText)}</span>`;return}
 const list=multiple?files:files.slice(0,1);
 el.innerHTML=list.map((f,i)=>`<div class="identity-thumb-wrap ${multiple?'multi':'single'}"><img src="${URL.createObjectURL(f)}"><small>${esc(f.name)}</small><button type="button" class="mini identity-file-remove" data-identity-file-remove="${i}" aria-label="Remove ${esc(f.name)}">Remove</button></div>`).join("")+(multiple&&files.length>1?'<button type="button" class="ghost small identity-files-clear">Clear all</button>':'');
 el.querySelectorAll('[data-identity-file-remove]').forEach(b=>b.onclick=()=>{const index=+b.dataset.identityFileRemove;if(!multiple){input.value='';identityFilePreview(input,box,multiple);return}try{const dt=new DataTransfer();files.forEach((f,i)=>{if(i!==index)dt.items.add(f)});input.files=dt.files}catch(_){input.value=''}identityFilePreview(input,box,multiple)});
 el.querySelector('.identity-files-clear')?.addEventListener('click',()=>{input.value='';identityFilePreview(input,box,multiple)});
}
function updateIdentityInputHelp(){
 const tr=s=>window.ZI18n?.t(s)||s;
 const swap=identityMode()==='face_swap',img2img=$('#identityGenerationMode')?.value==='img2img';
 const slots=$('#identityInputSlots'),ref=$('#identityReferenceWrap'),base=$('#identityBaseWrap');
 // Move the existing nodes only: FileList, previews and listeners stay intact.
 const first=swap?base:ref;
 if(slots&&first&&slots.firstElementChild!==first)slots.insertBefore(first,slots.firstElementChild);
 const put=(id,value)=>{const e=$(id);if(e){const text=tr(value);if(e.textContent!==text)e.textContent=text;}};
 put('#identityBaseLabel',swap?'Target image · required':img2img?'Starting image · required for Img2Img':'Fallback face pose · optional');
 put('#identityBaseHelp',swap?'The image whose face will be replaced. The rest of the picture is kept.':img2img?'Starting image for Img2Img; Denoise controls how much it changes. Also supplies face landmarks if no separate pose is provided.':'Used only for face landmarks when the separate pose is empty. Its background and details are not copied in text-to-image mode.');
 put('#identityReferenceHelp',swap?'Use a clear face photo. Only the first reference supplies the identity for Face Swap.':'Use a clear face photo. The first reference defines the identity; additional references are diagnostic only.');
 put('#identityPoseHelp','Face landmarks only, not identity or full-body pose. Overrides the base image; without either, landmarks come from the primary face reference.');
 const empty=swap?'No base image selected.':img2img?'Add a starting image for Img2Img.':'Optional: fallback face landmarks.';
 const preview=$('#identityBasePreview');
 if(preview){preview.dataset.emptyText=empty;if(!$('#identityBaseImage')?.files?.length){const note=preview.querySelector(':scope > .muted');if(note)note.textContent=tr(empty);}}
 const posePreview=$('#identityPosePreview'),poseEmpty='Optional: separate face landmarks take priority over the base image.';
 if(posePreview){posePreview.dataset.emptyText=poseEmpty;if(!$('#identityPoseImage')?.files?.length){const note=posePreview.querySelector(':scope > .muted');if(note)note.textContent=tr(poseEmpty);}}
}
function updateIdentityCheckpointPath(){
 const sel=$('#identityBaseModel'),note=$('#identityCheckpointPath');
 if(note){const value=sel?.value||'';if(note.textContent!==value)note.textContent=value;note.hidden=!value;note.title=value;}
}
function renderIdentityModelChoices(d){
 const sel=$("#identityBaseModel");if(sel){
   const tr=s=>window.ZI18n?.t(s)||s;
   const filename=p=>String(p).replace(/\\/g,'/').replace(/\/+$/,'').split('/').pop()||String(p);
   const current=sel.value||d.default_base_model||"",defaultPath=d.default_base_model||"";
   const cps=d.checkpoints||[],seen=new Set(),opts=[];
   const add=c=>{if(!c.path||seen.has(c.path))return;seen.add(c.path);opts.push({path:c.path,name:c.name||filename(c.path),configured:c.path===defaultPath});};
   // Use the same inventory as Create. A configured default is a real path, not "SDXL Base".
   if(defaultPath)add(cps.find(c=>c.path===defaultPath)||{path:defaultPath});
   for(const c of cps)add(c);
   // Do not silently switch a per-job selection if the catalog changes during polling.
   if(current&&!seen.has(current))opts.push({path:current,name:filename(current),unlisted:true});
   const rows=opts.map(c=>({path:c.path,label:c.name+(c.configured?' · '+tr('Configured default'):'')+(c.unlisted?' · '+tr('Not in the current catalog'):'' )}));
   const signature=JSON.stringify(rows.length?rows:[{path:'',label:tr('No SDXL checkpoints found')}]);
   // Stable option nodes keep the native dropdown usable while status is polled.
   if(sel.dataset.identityOptions!==signature){
     sel.replaceChildren();
     for(const row of rows.length?rows:[{path:'',label:tr('No SDXL checkpoints found')}] ){
       const option=new Option(row.label,row.path);option.title=row.path;sel.add(option);
     }
     sel.dataset.identityOptions=signature;
   }
   if([...sel.options].some(o=>o.value===current))sel.value=current;
   updateIdentityCheckpointPath();
 }
 const ls=$("#identityLoraSelect");if(ls){
   const current=ls.value;const all=d.loras||[];
   ls.innerHTML='<option value="">No LoRA</option>'+all.map(l=>`<option value="${esc(l.path)}">${esc(l.name)}</option>`).join("");
   if([...ls.options].some(o=>o.value===current))ls.value=current;
 }
 renderIdentityLoraStack();
}
function renderIdentityLoraStack(){
 const box=$("#identityLoraStack");if(!box)return;const xs=S.identity.loras||[];
 box.innerHTML=xs.length?xs.map((x,i)=>`<div class="lora-row"><span title="${esc(x.path)}">${esc(x.name)}</span><input type="number" min="-2" max="2" step="0.05" value="${Number(x.strength??1)}" data-identity-lora-strength="${i}"><button type="button" data-identity-lora-remove="${i}">×</button></div>`).join(""):'<div class="empty-mini">No Identity LoRAs selected.</div>';
 $$('[data-identity-lora-strength]').forEach(e=>e.onchange=()=>S.identity.loras[+e.dataset.identityLoraStrength].strength=Number(e.value));
 $$('[data-identity-lora-remove]').forEach(e=>e.onclick=()=>{S.identity.loras.splice(+e.dataset.identityLoraRemove,1);renderIdentityLoraStack()});
}
function addIdentityLora(){
 const sel=$("#identityLoraSelect");if(!sel?.value)return;const path=sel.value;
 if((S.identity.loras||[]).some(x=>x.path===path))return;
 if((S.identity.loras||[]).length>=4){alert('Identity Studio supports up to 4 stacked LoRAs.');return}
 const found=(S.identity.boot?.loras||[]).find(x=>x.path===path);const strength=Number($("#identityLoraStrength")?.value||0.8);
 S.identity.loras.push({path,name:found?.name||path.split('/').pop(),strength});renderIdentityLoraStack();
}
function renderIdentityQueue(d){
 const box=$('#identityQueue');if(!box)return;const q=d.queue||{},items=[];
 if(q.active)items.push({...q.active,_active:true});
 (q.queued||[]).forEach((j,i)=>items.push({...j,queue_position:i+1}));
 const html=items.length?items.map(j=>`<div data-identity-queue-id="${esc(j.id)}" class="identity-queue-row ${j._active?'active':''}"><div><b>${j._active?'RUNNING / DISPATCHING':`#${j.queue_position} QUEUED`} · ${j.mode==='face_swap'?'Face Swap':'InstantID'}</b><small>${esc(j.test_label||j.prompt||j.id).slice(0,160)}</small></div><div><span>${j.batch_id?`batch ${esc(j.batch_id)}`:''}</span>${!j._active?`<button class="mini danger" data-identity-cancel="${j.id}">Cancel</button>`:''}</div></div>`).join(''):'<div class="empty-mini">Queue empty. New Identity jobs can be submitted while another one is running.</div>';
 window.ZetalvxIdentityDOM.rows(box,html,'data-identity-queue-id');
 $$('[data-identity-cancel]').forEach(b=>b.onclick=async()=>{try{await api(`/api/identity/jobs/${b.dataset.identityCancel}/cancel`,{method:'POST'});await loadIdentity()}catch(e){alert(e.message)}});
}
function renderIdentityBatches(batches){
 const box=$('#identityBatches');if(!box)return;
 const html=(batches||[]).length?`<div class="identity-batch-grid">${batches.slice(0,8).map(b=>`<div class="identity-batch-card"><b>${esc(b.name||b.id)}</b><small>${b.completed||0}/${b.total||0} completed · ${b.running||0} running · ${b.queued||0} queued${b.failed?` · ${b.failed} failed`:''}</small><div class="progress-track"><div class="progress-fill" style="width:${b.total?Math.round((b.completed||0)/(b.total||1)*100):0}%"></div></div></div>`).join('')}</div>`:'';
 window.ZetalvxIdentityDOM.html(box,html);
}
let identityReadPromise=null,identityPollInFlight=false;
function identitySnapshot(){
 if(!identityReadPromise)identityReadPromise=api('/api/identity/bootstrap').finally(()=>{identityReadPromise=null});
 return identityReadPromise;
}
async function loadIdentity(){
 try{
   const d=await identitySnapshot();S.identity.boot=d;generationStatusRecovered('identity');renderIdentityModelChoices(d);renderIdentityQueue(d);renderIdentityBatches(d.batches||[]);
   const rt=d.runtime||{},models=rt.models||{},runtime=rt.runtime||{};
   window.ZetalvxIdentityDOM.text($("#identityRuntimeState"),`Identity runtime · ${rt.online?(rt.ready?"READY":"ONLINE / SETUP"):'OFFLINE'}`);
   const missing=[];
   if(!models.base_sdxl_exists)missing.push('SDXL base');
   if(!models.controlnet_ready)missing.push('InstantID ControlNet');
   if(!models.adapter_ready)missing.push('IP adapter');
   if(!models.instantid_face_pack_ready)missing.push(`InstantID face pack ${models.instantid_face_pack||'antelopev2'}`);
   if(!models.txt2img_pipeline_ready)missing.push('InstantID pipeline code');
   if(!models.swap_face_pack_ready)missing.push(`Swap face pack ${models.swap_face_pack||'buffalo_l'}`);
   if(!models.swapper_ready)missing.push('True swap model');
   const caps=`InstantID ${rt.instantid_ready?'READY':'NOT READY'} · True Swap ${rt.swap_ready?'READY':'MODEL NEEDED'}`;
   const qn=Number(d.queue?.count||0);
   window.ZetalvxIdentityDOM.html($("#identityRuntimeDetails"),`<b>Identity worker ${rt.busy?`· BUSY · job ${esc(rt.job_id||'')}`:(rt.ready?'· Ready':'· Setup required')}</b><small>${esc(runtime.gpu||'')} ${runtime.torch?`· torch ${esc(runtime.torch)}`:''}${runtime.cuda?` · CUDA ${esc(runtime.cuda)}`:''}</small><small>${caps} · queue ${qn}</small>${missing.length?`<small>Missing: ${esc(missing.join(', '))}</small>`:''}${models.swapper_model?`<small>Swap model: ${esc(models.swapper_model)}</small>`:''}${rt.last_error?`<small class="training-runtime-warning">${esc(rt.last_error)}</small>`:''}`);
   renderIdentityJobs(d.jobs||[]);
 }catch(e){
   window.ZetalvxIdentityDOM.text($("#identityRuntimeState"),'Identity status unavailable · reconnecting');
   generationFeedback('identity',e.message,true);console.warn('[IDENTITY STATUS]',e);
 }
}
function renderIdentityJobs(jobs){
 const box=$("#identityJobs");if(!box)return;
 const html=jobs.length?jobs.map(j=>{
   const p=Math.round(Number(j.progress||0)*100),done=j.status==='completed'&&j.output_exists;
   const queued=j.status==='queued',active=['running','dispatching'].includes(j.status);
   const batch=j.batch_id?`<div class="identity-test-label"><b>${esc(j.test_label||`Test ${j.test_index}/${j.test_total}`)}</b><small>${esc(j.batch_name||j.batch_id)} · ${j.test_index||'?'} / ${j.test_total||'?'}</small></div>`:'';
   return `<div data-identity-job-id="${esc(j.id)}" class="identity-job identity-status-${esc(j.status||'unknown')}">
     <div class="training-job-head"><div><b>${j.mode==='face_swap'?'True Face Swap':'InstantID'} · ${esc(j.id)}</b><small>${esc(j.status||'')} · ${esc(j.phase||'')}${queued&&j.queue_position?` · queue #${j.queue_position}`:''}</small></div><span>${p}%</span></div>
     <div class="progress-track"><div class="progress-fill" style="width:${p}%"></div></div>${batch}
     ${done?`<div class="identity-output"><img src="/api/identity/jobs/${j.id}/file" loading="lazy"></div>`:''}
     <div class="training-job-meta"><span>${j.mode==='face_swap'?`swap · ${esc(j.target_face||'largest')}${j.swap_all?' · ALL':''}${j.refine_with_sdxl?` · SDXL refine ${Number(j.swap_refine_denoise||0).toFixed(2)}`:''}`:`${esc(j.instantid_generation_mode||'txt2img')} · identity ${Number(j.identity_strength||0).toFixed(2)} · pose ${Number(j.pose_strength||0).toFixed(2)} · CFG ${Number(j.guidance||0).toFixed(2)}${j.instantid_generation_mode==='img2img'?` · denoise ${Number(j.denoise_strength||0).toFixed(2)}`:''}`}</span><span>${j.seed!==undefined&&j.seed!==null?`seed ${esc(j.seed)}`:''}</span></div>
     ${(j.mode==='instantid'||j.refine_with_sdxl)?`<div class="training-job-meta"><span>checkpoint ${esc((j.base_model||'').split('/').pop()||'default')}</span><span>${(j.loras||[]).length?`${(j.loras||[]).length} LoRA(s)`:'no LoRA'}</span></div>`:''}
     ${j.prompt?`<div class="training-phase-detail">${esc(j.prompt)}</div>`:''}
     ${j.library_artifact_id?`<div class="validation-box ready"><b>Saved to project Library</b><small>Artifact ${esc(j.library_artifact_id)}</small></div>`:''}
     ${j.error?`<pre class="training-error">${esc(j.error)}</pre>`:''}
     <div class="asset-actions">
       ${done?`<a class="button-link ghost small" data-safe-download href="/api/identity/jobs/${j.id}/download">Download</a><button class="ghost small" data-identity-library="${j.id}">${j.library_artifact_id?'Library saved':'Save to Library'}</button>`:''}
       <button class="ghost small" data-identity-use="${j.id}">Use settings</button>
       <button class="ghost small" data-identity-log="${j.id}">View log</button>
       ${queued?`<button class="danger ghost small" data-identity-cancel="${j.id}">Cancel queued</button>`:''}
       ${!active?`<button class="danger ghost small" data-identity-delete="${j.id}">Delete</button>`:''}
     </div>
   </div>`
 }).join(''):'<div class="empty-state">No Identity jobs yet.</div>';
 window.ZetalvxIdentityDOM.rows(box,html,'data-identity-job-id');
 $$('[data-identity-log]').forEach(b=>b.onclick=async()=>{try{const d=await api(`/api/identity/jobs/${b.dataset.identityLog}/log`);S.identity.logJobId=b.dataset.identityLog;$("#identityLogTitle").textContent=`Identity log · ${b.dataset.identityLog}`;$("#identityLogText").textContent=d.log||'No log yet.';$("#identityLogPanel").classList.remove('hidden')}catch(e){alert(e.message)}});
 $$('[data-identity-library]').forEach(b=>b.onclick=async()=>{try{await api(`/api/identity/jobs/${b.dataset.identityLibrary}/library`,{method:'POST'});await openProject(S.project.id);await loadIdentity()}catch(e){alert(e.message)}});
 $$('[data-identity-delete]').forEach(b=>b.onclick=async()=>{if(!confirm('Delete this Identity job and its saved input/output files?'))return;try{await api(`/api/identity/jobs/${b.dataset.identityDelete}`,{method:'DELETE'});await loadIdentity()}catch(e){alert(e.message)}});
 $$('[data-identity-cancel]').forEach(b=>b.onclick=async()=>{try{await api(`/api/identity/jobs/${b.dataset.identityCancel}/cancel`,{method:'POST'});await loadIdentity()}catch(e){alert(e.message)}});
 $$('[data-identity-use]').forEach(b=>b.onclick=()=>{const j=(S.identity.boot?.jobs||[]).find(x=>x.id===b.dataset.identityUse);if(j)applyIdentityJobSettings(j)});
}
function applyIdentityJobSettings(j){
 setIdentityMode(j.mode||'instantid');
 const set=(id,v)=>{const e=$(id);if(e&&v!==undefined&&v!==null)e.value=v};
 set('#identityPrompt',j.prompt||'');set('#identityNegative',j.negative_prompt||'');set('#identityBaseModel',j.base_model||'');
 set('#identityStrength',j.identity_strength);set('#identityPoseStrength',j.pose_strength);set('#identityDenoise',j.denoise_strength);
 set('#identityControlStart',j.control_guidance_start);set('#identityControlEnd',j.control_guidance_end);set('#identitySteps',j.steps);set('#identityGuidance',j.guidance);
 set('#identityScheduler',j.scheduler);set('#identityEta',j.eta);set('#identityClipSkip',j.clip_skip);set('#identitySeed',j.seed);set('#identityWidth',j.width);set('#identityHeight',j.height);
 set('#identityGenerationMode',j.instantid_generation_mode);set('#identityFaceMaskPadding',j.face_mask_padding);set('#identityDetectionSize',j.detection_size);set('#identityTargetFace',j.target_face);set('#identitySourceFace',j.source_face);
 if($('#identityGuessMode'))$('#identityGuessMode').checked=!!j.guess_mode;if($('#identityEnhanceFaceRegion'))$('#identityEnhanceFaceRegion').checked=!!j.enhance_face_region;if($('#identitySwapAll'))$('#identitySwapAll').checked=!!j.swap_all;
 if($('#identitySwapRefine'))$('#identitySwapRefine').checked=!!j.refine_with_sdxl;set('#identitySwapRefineDenoise',j.swap_refine_denoise);set('#identitySwapRefineSteps',j.swap_refine_steps);set('#identitySwapRefineGuidance',j.swap_refine_guidance);set('#identitySwapRefineScheduler',j.swap_refine_scheduler);set('#identitySwapRefineSeed',j.swap_refine_seed);
 S.identity.loras=(j.loras||[]).map(x=>({...x}));renderIdentityLoraStack();updateIdentityCheckpointPath();updateIdentityGenerationMode();updateIdentitySwapRefine();
 alert('Settings restored. Browser file inputs cannot be restored automatically; existing selected files are left unchanged.');
}
function buildIdentityFormData(){
 const refs=$("#identityReferences")?.files||[];const fd=new FormData();fd.append('project_id',S.project.id);fd.append('mode',identityMode());
 if($("#identityBaseImage")?.files?.[0])fd.append('base_image',$("#identityBaseImage").files[0]);
 if($("#identityPoseImage")?.files?.[0])fd.append('pose_image',$("#identityPoseImage").files[0]);
 [...refs].slice(0,4).forEach(f=>fd.append('references',f));
 const map={prompt:'identityPrompt',negative_prompt:'identityNegative',base_model:'identityBaseModel',identity_strength:'identityStrength',pose_strength:'identityPoseStrength',denoise_strength:'identityDenoise',face_mask_padding:'identityFaceMaskPadding',steps:'identitySteps',guidance:'identityGuidance',seed:'identitySeed',width:'identityWidth',height:'identityHeight',instantid_generation_mode:'identityGenerationMode',control_guidance_start:'identityControlStart',control_guidance_end:'identityControlEnd',scheduler:'identityScheduler',eta:'identityEta',clip_skip:'identityClipSkip',detection_size:'identityDetectionSize',target_face:'identityTargetFace',source_face:'identitySourceFace',swap_refine_denoise:'identitySwapRefineDenoise',swap_refine_steps:'identitySwapRefineSteps',swap_refine_guidance:'identitySwapRefineGuidance',swap_refine_scheduler:'identitySwapRefineScheduler',swap_refine_seed:'identitySwapRefineSeed'};
 for(const [k,id] of Object.entries(map))fd.append(k,$(`#${id}`)?.value??'');
 fd.append('guess_mode',$('#identityGuessMode')?.checked?'true':'false');fd.append('enhance_face_region',$('#identityEnhanceFaceRegion')?.checked?'true':'false');fd.append('swap_all',$('#identitySwapAll')?.checked?'true':'false');fd.append('refine_with_sdxl',$('#identitySwapRefine')?.checked?'true':'false');fd.append('loras',JSON.stringify(S.identity.loras||[]));
 return fd;
}
function validateIdentityInputs(forAuto=false){
 if(!S.project?.id){alert('Open a project first.');return false}
 const refs=$("#identityReferences")?.files||[];if(!refs.length){alert('Add at least one face reference.');return false}
 if(identityMode()==='face_swap'&&!$("#identityBaseImage")?.files?.length){alert('Face Swap requires a base image.');return false}
 if(identityMode()==='instantid'&&($("#identityGenerationMode")?.value||'txt2img')==='img2img'&&!$('#identityBaseImage')?.files?.length){alert('InstantID Img2Img requires a Base image.');return false}
 if(forAuto&&identityMode()!=='instantid'){alert('Auto Test is currently for InstantID / Face Consistency.');return false}
 return true;
}
// One upload per page at a time. GPU jobs may still queue consecutively.
let identitySubmissionInFlight=false,identitySubmissionKind='';
function updateIdentitySubmitButtons(){
 const single=$('#identityGenerate'),sweep=$('#identityAutoTestRun');
 const set=(b,label)=>{if(!b)return;b.disabled=identitySubmissionInFlight;b.setAttribute('aria-busy',String(identitySubmissionInFlight));b.textContent=label;};
 set(single,identitySubmissionInFlight&&identitySubmissionKind==='single'?'Adding to queue…':(identityMode()==='face_swap'?'Add Face Swap to Queue':'Add InstantID to Queue'));
 set(sweep,identitySubmissionInFlight&&identitySubmissionKind==='sweep'?'Queuing sweep…':'Queue Auto Test');
}
function refreshIdentityAfterSubmission(){
 try{startIdentityPoll();Promise.resolve(pollIdentityLive()).catch(e=>console.warn('[IDENTITY STATUS]',e));}catch(e){console.warn('[IDENTITY STATUS]',e)}
}
async function sendIdentityForm(kind,extra=null){
 if(identitySubmissionInFlight)return;
 identitySubmissionInFlight=true;identitySubmissionKind=kind;updateIdentitySubmitButtons();
 let refresh=false;
 try{
  const form=buildIdentityFormData();if(extra)form.append('sweep_config',JSON.stringify(extra));
  const body=await ZetalvxIdentitySubmit.prepare(form);
  const d=await api(kind==='sweep'?'/api/identity/auto-test':'/api/identity/jobs',{method:'POST',body});
  if(d.ok!==true||!(kind==='sweep'?d.batch_id:d.job_id))throw ZetalvxIdentitySubmit.nonJsonError(202);
  refresh=true;
  generationFeedback('identity',kind==='sweep'?`Queued ${d.count} variants in batch ${d.batch_name}.`:'Job accepted. Queue and history update automatically.');
 }catch(e){
  generationFeedback('identity',e.message,true);console.warn('[IDENTITY SUBMISSION]',e.code||e.name,e.status||'',e.data?.diagnostic_id||'');
  refresh=!!e.submissionUncertain;
 }finally{
  // Never invoke setIdentityMode/render/history inside this unlock boundary.
  identitySubmissionInFlight=false;identitySubmissionKind='';updateIdentitySubmitButtons();
 }
 if(refresh)refreshIdentityAfterSubmission();
}
async function runIdentity(){
 if(identitySubmissionInFlight||!validateIdentityInputs(false))return;
 return sendIdentityForm('single');
}
function sweepVals(id){return String($(id)?.value||'').split(',').map(x=>Number(x.trim())).filter(Number.isFinite)}
const IDENTITY_SINGLE_PRESETS={
 max_fidelity:{label:'Maximum Fidelity',identity_strength:0.95,pose_strength:0.75,guidance:4.0,denoise_strength:0.30,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Closest match to the source face and expression. Best starting point when you want near-clone fidelity.'},
 fidelity_soft:{label:'Fidelity Soft',identity_strength:0.85,pose_strength:0.75,guidance:4.0,denoise_strength:0.30,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Still very faithful, but slightly less rigid than Maximum Fidelity.'},
 photogenic_faithful:{label:'Photogenic Faithful',identity_strength:0.95,pose_strength:0.60,guidance:4.0,denoise_strength:0.35,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Very similar identity with a touch more polish and flattering rendering.'},
 expression_freedom:{label:'Expression Freedom',identity_strength:0.95,pose_strength:0.45,guidance:4.0,denoise_strength:0.40,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Strong identity retention while allowing more change in expression and subtle facial geometry.'},
 natural_reinterpretation:{label:'Natural Reinterpretation',identity_strength:0.95,pose_strength:0.30,guidance:4.0,denoise_strength:0.45,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Still recognizably the same person, but with clearly more reinterpretation freedom.'},
 cinematic:{label:'Cinematic',identity_strength:0.95,pose_strength:0.30,guidance:5.0,denoise_strength:0.45,control_guidance_start:0.00,control_guidance_end:1.00,steps:30,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Pushes the checkpoint/prompt more, giving a cleaner and more cinematic photographic look.'},
 cinematic_strong:{label:'Cinematic Strong',identity_strength:0.95,pose_strength:0.30,guidance:6.0,denoise_strength:0.50,control_guidance_start:0.00,control_guidance_end:1.00,steps:32,guess_mode:false,enhance_face_region:false,face_mask_padding:0.18,summary:'Most stylized/photogenic preset of this group. Excellent for beauty shots, less exact as a clone.'}
};
function setNumInput(id,v){const e=$(id);if(e&&v!==undefined&&v!==null)e.value=String(v)}
function applyIdentitySinglePreset(showToast=true){
 const key=$('#identitySinglePreset')?.value||'custom';
 const info=$('#identityPresetInfo');
 if(key==='custom'||!IDENTITY_SINGLE_PRESETS[key]){if(info)info.textContent='Custom / manual mode. Current values are not changed automatically.';return}
 const p=IDENTITY_SINGLE_PRESETS[key];
 setNumInput('#identityStrength',p.identity_strength);setNumInput('#identityPoseStrength',p.pose_strength);setNumInput('#identityGuidance',p.guidance);setNumInput('#identityDenoise',p.denoise_strength);setNumInput('#identityControlStart',p.control_guidance_start);setNumInput('#identityControlEnd',p.control_guidance_end);setNumInput('#identitySteps',p.steps);setNumInput('#identityFaceMaskPadding',p.face_mask_padding);
 if($('#identityGuessMode'))$('#identityGuessMode').checked=!!p.guess_mode; if($('#identityEnhanceFaceRegion'))$('#identityEnhanceFaceRegion').checked=!!p.enhance_face_region;
 if(info)info.textContent=`${p.label}: ${p.summary}`;
 if(showToast)alert(`Applied preset: ${p.label}`);
}
function identitySweepConfig(){return {name:$('#identitySweepName')?.value||'',identity:sweepVals('#identitySweepIdentity'),pose:sweepVals('#identitySweepPose'),cfg:sweepVals('#identitySweepCfg'),denoise:sweepVals('#identitySweepDenoise'),control_end:sweepVals('#identitySweepControlEnd'),max_jobs:Number($('#identitySweepMax')?.value||24),vary_seed:!!$('#identitySweepVarySeed')?.checked,auto_save_library:!!$('#identitySweepAutoLibrary')?.checked}}
function updateIdentitySweepCount(){
 if(!$('#identitySweepCount'))return;const c=identitySweepConfig(),gm=$('#identityGenerationMode')?.value||'txt2img';const n=Math.max(1,c.identity.length)*Math.max(1,c.pose.length)*Math.max(1,c.cfg.length)*(gm==='img2img'?Math.max(1,c.denoise.length):1)*Math.max(1,c.control_end.length);$('#identitySweepCount').textContent=`${n} variant${n===1?'':'s'}`;$('#identitySweepCount').classList.toggle('bad',n>Number(c.max_jobs||24));
}
function applyIdentitySweepPreset(){
 const p=$('#identitySweepPreset')?.value||'max_fidelity_map';
 if(p==='max_fidelity_map'){$('#identitySweepIdentity').value='0.90, 0.95, 1.00';$('#identitySweepPose').value='0.65, 0.75, 0.85';$('#identitySweepCfg').value='3.5, 4.0, 4.5';$('#identitySweepDenoise').value=$('#identityDenoise')?.value||'0.30';$('#identitySweepControlEnd').value='1.0';$('#identitySweepMax').value='27'}
 else if(p==='fidelity_vs_photogenic'){ $('#identitySweepIdentity').value='0.85, 0.95';$('#identitySweepPose').value='0.45, 0.60, 0.75, 0.85';$('#identitySweepCfg').value='4.0';$('#identitySweepDenoise').value=$('#identityDenoise')?.value||'0.35';$('#identitySweepControlEnd').value='1.0';$('#identitySweepMax').value='24'}
 else if(p==='cinematic_range'){ $('#identitySweepIdentity').value='0.95';$('#identitySweepPose').value='0.30, 0.40, 0.50';$('#identitySweepCfg').value='4.5, 5.0, 5.5';$('#identitySweepDenoise').value=$('#identityDenoise')?.value||'0.45';$('#identitySweepControlEnd').value='1.0';$('#identitySweepMax').value='18'}
 else if(p==='img2img'){ $('#identitySweepIdentity').value='0.85, 0.95';$('#identitySweepPose').value='0.45, 0.60';$('#identitySweepCfg').value=$('#identityGuidance')?.value||'4.0';$('#identitySweepDenoise').value='0.20, 0.35, 0.50';$('#identitySweepControlEnd').value='1.0';$('#identitySweepMax').value='24'}
 updateIdentitySweepCount();
}
async function runIdentityAutoTest(){
 if(identitySubmissionInFlight||!validateIdentityInputs(true))return;const cfg=identitySweepConfig(),gm=$('#identityGenerationMode')?.value||'txt2img';const n=Math.max(1,cfg.identity.length)*Math.max(1,cfg.pose.length)*Math.max(1,cfg.cfg.length)*(gm==='img2img'?Math.max(1,cfg.denoise.length):1)*Math.max(1,cfg.control_end.length);if(n>Number(cfg.max_jobs||24)){alert(`This creates ${n} jobs. Reduce the lists or increase Max jobs.`);return}if(!confirm(`Queue ${n} Identity test variants? They will run one after another on the GPU.`))return;
 return sendIdentityForm('sweep',cfg);
}
async function pollIdentityLive(){
 if(!$("#view-identity")?.classList.contains('active')||document.hidden||identityPollInFlight)return;
 identityPollInFlight=true;
 try{
   const d=await identitySnapshot();
   S.identity.boot=d;generationStatusRecovered('identity');
   const rt=d.runtime||{};
   const runtime=rt.runtime||{};
   const models=rt.models||{};
   const missing=rt.missing||[];
   const caps=(rt.capabilities||[]).join(' · ');
   const qn=Number(d.queue?.count||0);
   window.ZetalvxIdentityDOM.text($("#identityRuntimeState"),`Identity runtime · ${rt.online?(rt.ready?"READY":"ONLINE / SETUP"):'OFFLINE'}`);
   window.ZetalvxIdentityDOM.html($("#identityRuntimeDetails"),`<b>Identity worker ${rt.busy?`· BUSY · job ${esc(rt.job_id||'')}`:(rt.ready?'· Ready':'· Setup required')}</b><small>${esc(runtime.gpu||'')} ${runtime.torch?`· torch ${esc(runtime.torch)}`:''}${runtime.cuda?` · CUDA ${esc(runtime.cuda)}`:''}</small><small>${caps} · queue ${qn}</small>${missing.length?`<small>Missing: ${esc(missing.join(', '))}</small>`:''}${models.swapper_model?`<small>Swap model: ${esc(models.swapper_model)}</small>`:''}${rt.last_error?`<small class="training-runtime-warning">${esc(rt.last_error)}</small>`:''}`);
   renderIdentityQueue(d);
   renderIdentityBatches(d.batches||[]);
   renderIdentityJobs(d.jobs||[]);
 }catch(e){
   window.ZetalvxIdentityDOM.text($("#identityRuntimeState"),'Identity status unavailable · reconnecting');
   generationFeedback('identity',e.message,true);console.warn('Identity live poll:',e);
 }finally{identityPollInFlight=false}
}
function startIdentityPoll(){clearInterval(S.identity.poll);S.identity.poll=setInterval(pollIdentityLive,2500)}
function resumeGenerationStatus(){
 if(document.hidden)return;
 if($('#view-identity')?.classList.contains('active')){startIdentityPoll();pollIdentityLive();}
 if(S.project&&!pendingProjectId){projectRecoveryUntil=Date.now()+120000;startPolling();}
}
window.addEventListener('online',resumeGenerationStatus);
document.addEventListener('visibilitychange',resumeGenerationStatus);
$$('[data-identity-mode]').forEach(b=>b.onclick=()=>setIdentityMode(b.dataset.identityMode));
$('#identityBaseModel')?.addEventListener('change',updateIdentityCheckpointPath);
window.addEventListener('languagechange',()=>{updateIdentityInputHelp();if(S.identity?.boot)renderIdentityModelChoices(S.identity.boot)});
window.addEventListener('model-hub-updated',e=>{const d=e.detail;if(!S.identity?.boot||!d||!Array.isArray(d.checkpoints))return;S.identity.boot.checkpoints=d.checkpoints;const cp=(d.models||[]).find(m=>m.id==='sdxl')?.config?.checkpoint;if(cp)S.identity.boot.default_base_model=cp;renderIdentityModelChoices(S.identity.boot)});
$('#identityGenerationMode')?.addEventListener('change',updateIdentityGenerationMode);$('#identitySwapRefine')?.addEventListener('change',updateIdentitySwapRefine);$('#identityLoraAdd')?.addEventListener('click',addIdentityLora);$('#identityApplyPreset')?.addEventListener('click',()=>applyIdentitySinglePreset(true));$('#identitySinglePreset')?.addEventListener('change',()=>applyIdentitySinglePreset(false));
$("#identityBaseImage")?.addEventListener('change',e=>identityFilePreview(e.target,'#identityBasePreview'));$("#identityReferences")?.addEventListener('change',e=>identityFilePreview(e.target,'#identityReferencePreview',true));$("#identityPoseImage")?.addEventListener('change',e=>identityFilePreview(e.target,'#identityPosePreview'));
$("#identityGenerate")?.addEventListener('click',runIdentity);$('#identityAutoTestRun')?.addEventListener('click',runIdentityAutoTest);$('#identitySweepPreset')?.addEventListener('change',applyIdentitySweepPreset);['#identitySweepIdentity','#identitySweepPose','#identitySweepCfg','#identitySweepDenoise','#identitySweepControlEnd','#identitySweepMax'].forEach(id=>$(id)?.addEventListener('input',updateIdentitySweepCount));
$("#identityRefresh")?.addEventListener('click',loadIdentity);$("#identityUnload")?.addEventListener('click',async()=>{try{await api('/api/runtime/identity/unload',{method:'POST'});await loadIdentity()}catch(e){alert(e.message)}});$("#identityLogClose")?.addEventListener('click',()=>{$("#identityLogPanel")?.classList.add('hidden');S.identity.logJobId=null});
applyIdentitySweepPreset();applyIdentitySinglePreset(false);setIdentityMode('face_swap');


function mediaToolAssets(){return (S.project?.artifacts||[]).filter(a=>a.type==='image')}
function mediaToolAssetName(a){return a?.metadata?.original_name||a?.metadata?.model_name||`#${a?.id?.slice(0,8)||"asset"}`}
function mediaToolAllowedOperations(){return ['resize_image','convert_image','crop_image','rotate_image','flip_image']}
function mediaStateKey(){return projectSessionKey()}
function mediaState(){return S.mediaSettings[mediaStateKey()]||(S.mediaSettings[mediaStateKey()]={source_ids:[],operation:"",params:{}})}
function selectedMediaIds(){
 const el=$("#mtSource");if(!el)return [];
 return [...el.selectedOptions].map(o=>o.value).filter(Boolean);
}
function setSelectedMediaIds(ids){
 const wanted=new Set(ids||[]);
 if(!$("#mtSource"))return;
 [...$("#mtSource").options].forEach(o=>o.selected=wanted.has(o.value));
}
function captureMediaToolState(){
 if(!$("#mtSource"))return;const st=mediaState(),selected=selectedMediaIds();
 if(selected.length)st.source_ids=selected;
 st.operation=$("#mtOperation")?.value||st.operation||"";
 const p={...(st.params||{})};
 for(const [id,key] of [["mtWidth","width"],["mtHeight","height"],["mtFps","fps"],["mtFormat","format"],["mtTimestamp","timestamp"],["mtStart","start"],["mtEnd","end"],["mtDuration","duration"],["mtVolumeDb","volume_db"]]){
   const el=$("#"+id);if(el)p[key]=el.value;
 }
 st.params=p;saveUiSession();
}
function mediaOperationIntersection(arts){
 if(!arts.length)return [];
 let common=new Set(mediaToolAllowedOperations(arts[0]));
 for(const a of arts.slice(1))common=new Set([...common].filter(x=>mediaToolAllowedOperations(a).includes(x)));
 return [...common];
}
function renderMediaToolSourcePreview(){
 const box=$("#mtSourcePreview");if(!box)return;
 const arts=selectedMediaIds().map(artifactById).filter(Boolean);
 if(!arts.length){box.innerHTML='<div class="empty-mini">Upload files or choose one or more project assets.</div>';return}
 box.innerHTML=`<div class="media-batch-summary"><b>${arts.length} file${arts.length===1?"":"s"} selected</b><small>${arts.map(a=>esc(mediaToolAssetName(a))).join(" · ")}</small></div>`+
   arts.slice(0,6).map(a=>`<div class="media-tool-selected">${mediaPreview(a,"media-tool-selected-preview")}<div><b>${esc(mediaToolAssetName(a))}</b><small>${esc(a.type)} · #${a.id.slice(0,8)}</small></div></div>`).join("")+
   (arts.length>6?`<div class="empty-mini">+ ${arts.length-6} more</div>`:"");
}
function syncMediaToolOperations(preferred=""){
 const arts=selectedMediaIds().map(artifactById).filter(Boolean),allowed=mediaOperationIntersection(arts),sel=$("#mtOperation");if(!sel)return;
 [...sel.options].forEach(o=>o.hidden=!allowed.includes(o.value));
 const wanted=preferred||mediaState().operation||sel.value;
 sel.value=allowed.includes(wanted)?wanted:(allowed.includes(sel.value)?sel.value:(allowed[0]||""));
 mediaState().operation=sel.value;renderMediaToolFields(true);renderMediaToolSourcePreview();captureMediaToolState();
}
function renderMediaTools(preferIds=[],keepState=true){
 if(!$("#mtSource"))return;if(keepState)captureMediaToolState();
 const arts=mediaToolAssets(),st=mediaState();
 const preferred=Array.isArray(preferIds)?preferIds:(preferIds?[preferIds]:[]);
 const previous=preferred.length?preferred:(st.source_ids||[]);
 $("#mtSource").innerHTML=arts.length?arts.map(a=>`<option value="${a.id}">${esc(mediaToolAssetName(a))} · ${esc(a.type)}</option>`).join(""):'<option value="">No media in this project</option>';
 const existing=previous.filter(id=>arts.some(a=>a.id===id));
 if(existing.length)setSelectedMediaIds(existing);
 else if(arts.length)setSelectedMediaIds([arts[0].id]);
 st.source_ids=selectedMediaIds();
 $("#mtSourceHelp").textContent=arts.length?`${arts.length} media assets available. Ctrl/Cmd-click or tap selections to process multiple compatible files together.`:"No media yet. Upload one or more files.";
 syncMediaToolOperations(st.operation);
}
function renderMediaToolFields(){
 const op=$('#mtOperation')?.value;
 const size='<div class="control-grid"><label>Larghezza<input id="mtWidth" value="1024" type="number" min="1"></label><label>Altezza<input id="mtHeight" value="1024" type="number" min="1"></label></div>';
 $('#mtFields').innerHTML=op==='resize_image'?size:op==='crop_image'?size+'<label>Posizione X<input id="mtX" type="number" value="0" min="0"></label><label>Posizione Y<input id="mtY" type="number" value="0" min="0"></label>':op==='rotate_image'?'<label>Angolo<select id="mtDegrees"><option value="90">90° antiorario</option><option value="-90">90° orario</option><option value="180">180°</option></select></label>':op==='flip_image'?'<small>Specchia l’immagine in orizzontale.</small>':'<label>Formato<select id="mtFormat"><option>png</option><option>jpg</option><option>webp</option></select></label>';
}
$("#mtSource")?.addEventListener("change",()=>{captureMediaToolState();mediaState().source_ids=selectedMediaIds();syncMediaToolOperations("")});
$("#mtOperation")?.addEventListener("change",()=>{captureMediaToolState();mediaState().operation=$("#mtOperation").value;renderMediaToolFields(true);captureMediaToolState()});
$("#mtFields")?.addEventListener("input",captureMediaToolState);$("#mtFields")?.addEventListener("change",captureMediaToolState);

async function uploadMediaToolFileQuiet(file){
 if(!S.project)throw new Error("Open a project first");
 const fd=new FormData();fd.append("file",file);fd.append("role","media_tool_source");
 const d=await api(`/api/projects/${S.project.id}/upload`,{method:"POST",body:fd});
 return d.artifact;
}
$("#mtUpload")?.addEventListener("change",async e=>{
 try{
   captureMediaToolState();const files=[...e.target.files];if(!files.length)return;
   const oldOp=mediaState().operation,oldParams={...(mediaState().params||{})},newIds=[];
   $("#mtRunBtn").disabled=true;$("#mtRunBtn").textContent=`Uploading ${files.length}…`;
   for(const f of files){const a=await uploadMediaToolFileQuiet(f);newIds.push(a.id)}
   e.target.value="";await openProjectNoPoll(S.project.id);
   mediaState().source_ids=newIds;mediaState().operation=oldOp;mediaState().params=oldParams;saveUiSession();
   renderMediaTools(newIds,true);showView("media-tools");
 }catch(err){alert(err.message)}
 finally{$("#mtRunBtn").disabled=false;$("#mtRunBtn").textContent="Run media tool"}
});
$("#mtUseActive")?.addEventListener("click",()=>{
 const a=artifactById(S.activeAsset);if(!a||!["image"].includes(a.type)){alert("The active asset is not usable media.");return}
 captureMediaToolState();mediaState().source_ids=[a.id];renderMediaTools([a.id],true);showView("media-tools");
});
$("#mtRunBtn")?.addEventListener("click",async()=>{
 try{
   captureMediaToolState();const sourceIds=selectedMediaIds(),operation=$("#mtOperation")?.value||"";
   if(!sourceIds.length)throw new Error("Choose one or more source assets.");
   if(!operation)throw new Error("The selected files do not share a compatible operation.");
   const params={};
   if($("#mtWidth"))params.width=Number($("#mtWidth").value);if($("#mtHeight"))params.height=Number($("#mtHeight").value);
   for(const [id,key] of [['mtX','x'],['mtY','y'],['mtDegrees','degrees']])if($('#'+id))params[key]=Number($('#'+id).value);
   if($("#mtFps"))params.fps=Number($("#mtFps").value);if($("#mtFormat"))params.format=$("#mtFormat").value;
   if($("#mtTimestamp"))params.timestamp=$("#mtTimestamp").value;if($("#mtStart"))params.start=$("#mtStart").value;
   if($("#mtEnd"))params.end=$("#mtEnd").value;if($("#mtDuration"))params.duration=$("#mtDuration").value;
   if($("#mtVolumeDb"))params.volume_db=Number($("#mtVolumeDb").value);
   $("#mtRunBtn").disabled=true;$("#mtRunBtn").textContent=`Processing ${sourceIds.length} file${sourceIds.length===1?"":"s"}…`;
   const keepOp=operation,keepParams={...params},keepIds=[...sourceIds];
   const d=await api("/api/media-tools/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:S.project?.id,source_artifact_ids:sourceIds,operation,params})});
   await openProjectNoPoll(S.project.id);
   mediaState().source_ids=keepIds;mediaState().operation=keepOp;mediaState().params=keepParams;saveUiSession();
   renderMediaTools(keepIds,true);showView("media-tools");
   if((d.errors||[]).length)alert(`Completed ${d.artifacts?.length||0}/${sourceIds.length}. Errors:\\n${d.errors.map(x=>`${x.source_id}: ${x.error}`).join("\\n")}`);
 }catch(err){alert(err.message)}
 finally{$("#mtRunBtn").disabled=false;$("#mtRunBtn").textContent="Run media tool"}
});

async function refreshAfterProjectMutation(){
  const b=await api("/api/bootstrap");
  S.boot=b;
  const alive=(b.projects||[]).filter(p=>!Number(p.trashed||0));
  const currentAlive=S.project && alive.some(p=>p.id===S.project.id);
  if(currentAlive){
    await openProject(S.project.id);
  }else if(alive.length){
    await openProject(alive[0].id);
  }else{
    projectSelectionEpoch++;projectRefreshEpoch++;projectLoadController?.abort();pendingProjectId="";clearInterval(S.poll);S.project=null;S.activeAsset="";localStorage.removeItem("creator_sdxl_project_id");
    $("#topProjectName").textContent="—";
    renderProjects();renderAssets();renderJobs();renderActivePreview();renderMediaTools();
  }
}
let projectRenameId='';
function openProjectRename(pid){
 const p=(S.boot?.projects||[]).find(x=>x.id===pid);if(!p)return;
 projectRenameId=pid;$('#projectRenameName').value=p.name||'';$('#projectRenameDescription').value=p.description||'';$('#projectRenameModal').classList.remove('hidden');$('#projectRenameName').focus();
}
$('#cancelProjectRename').onclick=()=>{$('#projectRenameModal').classList.add('hidden');projectRenameId=''};
$('#saveProjectRename').onclick=async()=>{if(!projectRenameId)return;const name=$('#projectRenameName').value.trim();if(!name){alert('Project name cannot be empty');return}await api(`/api/projects/${projectRenameId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description:$('#projectRenameDescription').value})});$('#projectRenameModal').classList.add('hidden');projectRenameId='';await refreshAfterProjectMutation();};
async function moveProject(pid,direction){await api(`/api/projects/${pid}/move`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({direction})});await refreshAfterProjectMutation();}

async function trashProject(pid){
  if(!confirm("Move this project to Trash? Its files remain recoverable until you choose Delete forever."))return;
  await api(`/api/projects/${pid}/trash`,{method:"POST"});
  await refreshAfterProjectMutation();
}
async function restoreProject(pid){
  await api(`/api/projects/${pid}/restore`,{method:"POST"});
  await refreshAfterProjectMutation();
}
async function deleteProjectForever(pid){
  if(!confirm("DELETE FOREVER? This permanently removes the project, its generated files, uploads, jobs and conversation history. This cannot be undone."))return;
  await api(`/api/projects/${pid}/delete-forever`,{method:"POST"});
  await refreshAfterProjectMutation();
}


// v0.1.58: experimental InstantID face-region mask is opt-in.
(function(){
 const mask=$('#identityEnhanceFaceRegion'), pad=$('#identityFaceMaskPadding');
 const sync=()=>{ if(pad) pad.disabled=!(mask&&mask.checked); };
 if(mask){ mask.addEventListener('change',sync); sync(); }
})();

// v0.1.72: complete user preset profiles + persistent look bindings on top of the v0.1.71 mobile image UX.
(function(){
 const UI_MODE_KEY='creator_sdxl_flow_v1';
 S.imageUiMode=S.imageUiMode||'simple';
 S.imageQuickStyle=S.imageQuickStyle||'clean';
 
 function persistFlowUi(){
  try{sessionStorage.setItem(UI_MODE_KEY,JSON.stringify({imageUiMode:S.imageUiMode||'simple',imageQuickStyle:S.imageQuickStyle||'clean'}))}catch(e){}
 }
 function restoreFlowUi(){
  try{
   const d=JSON.parse(sessionStorage.getItem(UI_MODE_KEY)||'{}');
   if(d.imageUiMode)S.imageUiMode=d.imageUiMode;
   if(d.imageQuickStyle)S.imageQuickStyle=d.imageQuickStyle;
  }catch(e){}
 }
 function bindingFor(key){
  const all=S.boot?.image_preset_bindings||{};const v=all?.[key];return v&&typeof v==='object'&&!Array.isArray(v)?v:{};
 }
 function resolveBoundLora(spec){
  const list=S.boot?.loras||[];const path=String(spec?.path||'').trim(),name=String(spec?.name||'').trim().toLowerCase(),match=String(spec?.match||'').trim().toLowerCase();
  if(path){const exact=list.find(x=>x.path===path);if(exact)return exact}
  if(name){const exact=list.find(x=>String(x.name||'').toLowerCase()===name);if(exact)return exact}
  if(match)return list.find(x=>String(x.name||'').toLowerCase().includes(match)||String(x.path||'').toLowerCase().includes(match))||null;
  return null;
 }
 function clearBoundStyleLoras(){S.loras=(S.loras||[]).filter(x=>!x._presetBinding);S.imageBindingWarning='';renderLoraStack();}
 function applyPresetBinding(key,{clearPrevious=false}={}){
  const b=bindingFor(key);if(!Object.keys(b).length)return {applied:false,missing:[]};if(clearPrevious)clearBoundStyleLoras();
  const modelId=String(b.model_id||'').trim();if(modelId&&$('#modelSelect')&&[...$('#modelSelect').options].some(o=>o.value===modelId)){$('#modelSelect').value=modelId;$('#modelSelect').onchange?.();}
  const missing=[];for(const spec of (Array.isArray(b.loras)?b.loras:[])){if(spec?.auto_apply===false)continue;const found=resolveBoundLora(spec);if(!found){missing.push(spec?.name||spec?.path||spec?.match||'LoRA');continue}if(!(S.loras||[]).some(x=>x.path===found.path))S.loras.push({...found,strength:Number(spec?.strength??1),_presetBinding:key});}
  S.imageBindingWarning=missing.length?`Missing optional bound LoRA: ${missing.join(', ')}`:'';renderLoraStack();captureImageSettings();return {applied:true,missing};
 }
 function activeBinding(){const style=S.imageQuickStyle||'clean',workflow=S.imageWorkflow?.id||'',preset=S.imagePreset?.id||'';return Object.keys(bindingFor(style)).length?bindingFor(style):Object.keys(bindingFor(workflow)).length?bindingFor(workflow):bindingFor(preset);}
 function currentEffectiveSnapshot(){
  const model=selectedModel(),binding=activeBinding();return {task:TASKS[S.task]?.title||S.task,model:model?.name||'AUTO',provider:model?.provider||'auto',style:S.imageQuickStyle||'clean',workflow:S.imageWorkflow?.label||'',preset:S.imagePreset?.label||'',quality:$('#quality')?.value||'',steps:$('#steps')?.value||'',cfg:$('#cfg')?.value||'',strength:currentModelSupportsStrength()?($('#strength')?.value||''):'n/a',loras:(S.loras||[]).map(x=>`${x.name||String(x.path||'').split('/').pop()} @ ${Number(x.strength??1).toFixed(2)}`),effectivePrompt:composeImagePrompt($('#prompt')?.value||''),effectiveNegative:composeImageNegative($('#negativePrompt')?.value||''),binding};
 }
 function renderImageEffectiveState(){const el=$('#imageEffectiveState');if(!el)return;const s=currentEffectiveSnapshot(),hidden=s.workflow?`Workflow: ${s.workflow}`:(s.preset?`Preset: ${s.preset}`:'No hidden workflow'),lora=s.loras.length?` · LoRA ${s.loras.length}`:'';el.textContent=`${hidden} · ${s.model} · Steps ${s.steps} · CFG ${s.cfg}${s.strength!=='n/a'?` · Strength ${s.strength}`:''}${lora}${S.imageBindingWarning?` · ${S.imageBindingWarning}`:''}`;}
 function showEffectivePrompt(){
  const s=currentEffectiveSnapshot();$('#effectivePromptText').value=s.effectivePrompt;$('#effectiveNegativeText').value=s.effectiveNegative;const bind=s.binding||{},recommended=(bind.loras||[]).map(x=>x.name||x.path||x.match).filter(Boolean);
  $('#effectiveSettingsBody').innerHTML=[['Task',s.task],['Model',s.model],['Look',s.style],['Workflow',s.workflow||'None'],['Preset',s.preset||'None'],['Quality',s.quality],['Steps',s.steps],['CFG',s.cfg],['Strength',s.strength],['Active LoRAs',s.loras.join(' · ')||'None'],['Bound model',bind.model_id||'None'],['Recommended / bound LoRA',recommended.join(' · ')||'None']].map(([k,v])=>`<div><small>${esc(k)}</small><b>${esc(v)}</b></div>`).join('');$('#effectivePromptModal').classList.remove('hidden');
 }
 function presetTypeLabel(type){return type==='style'?'Style':type==='technical'?'Technical':'Complete'}
 function presetIncludes(p){
  if(p?.includes&&typeof p.includes==='object')return p.includes;
  return {model:true,loras:true,params:true,style:true,workflow:true,technical_preset:true,prompt:!!p?.include_prompt,task:true};
 }
 function defaultIncludesForType(type){
  if(type==='style')return {model:true,loras:true,params:false,style:true,prompt:false};
  if(type==='technical')return {model:true,loras:true,params:true,style:false,prompt:false};
  return {model:true,loras:true,params:true,style:true,prompt:true};
 }
 function applyPresetTypeDefaults(type){
  const d=defaultIncludesForType(type||'complete');
  if($('#userPresetSaveModel'))$('#userPresetSaveModel').checked=d.model;
  if($('#userPresetSaveLoras'))$('#userPresetSaveLoras').checked=d.loras;
  if($('#userPresetSaveParams'))$('#userPresetSaveParams').checked=d.params;
  if($('#userPresetSaveStyle'))$('#userPresetSaveStyle').checked=d.style;
  if($('#userPresetIncludePrompt'))$('#userPresetIncludePrompt').checked=d.prompt;
  renderUserPresetTypeHelp();
 }
 function renderUserPresetTypeHelp(){
  const type=$('#userPresetType')?.value||'complete',el=$('#userPresetTypeHelp');if(!el)return;
  const text=type==='style'
   ?'Style preset: keeps your current task. It can restore the look/workflow and, if selected, the preferred model and LoRA stack. Technical values and prompt can stay untouched.'
   :type==='technical'
    ?'Technical preset: keeps your current task and creative look. It can restore model/checkpoint, LoRAs and technical parameters without replacing the prompt or workflow.'
    :'Complete preset: restores the saved task plus every selected component. Use this for a full repeatable recipe.';
  el.textContent=text;
 }
 function renderUserPresetCards(){
  const box=$('#userPresetCards');if(!box)return;const list=S.boot?.user_image_presets||[],selected=$('#userImagePresetSelect')?.value||'';
  if(!list.length){box.innerHTML='<div class="empty-mini">No user presets yet.</div>';return}
  box.innerHTML=list.map(p=>{const type=p.preset_type||'complete',inc=presetIncludes(p),parts=[];if(inc.model)parts.push(p.model_id||'AUTO');if(inc.loras)parts.push(`${(p.loras||[]).length} LoRA`);if(inc.params)parts.push('params');if(inc.prompt)parts.push('prompt');return `<button type="button" class="user-preset-card ${selected===p.id?'active':''}" data-user-preset-id="${esc(p.id)}"><small>${esc(presetTypeLabel(type))} · ${esc(p.task||'image')}</small><b>${esc(p.name||p.id)}</b><span>${esc(parts.join(' · ')||'Reusable setup')}</span></button>`}).join('');
  $$('#userPresetCards [data-user-preset-id]').forEach(btn=>btn.onclick=()=>{$('#userImagePresetSelect').value=btn.dataset.userPresetId;syncUserPresetEditorFromSelected();renderUserPresetCards()});
 }
 function renderUserImagePresetOptions(){
  const sel=$('#userImagePresetSelect');if(!sel)return;const prev=sel.value,list=S.boot?.user_image_presets||[];
  sel.innerHTML='<option value="">No user preset</option>'+list.map(p=>`<option value="${esc(p.id)}">${esc(p.name||p.id)} · ${esc(presetTypeLabel(p.preset_type||'complete'))}</option>`).join('');
  if([...sel.options].some(o=>o.value===prev))sel.value=prev;renderUserPresetCards();if(!window.CreatorLab)syncUserPresetEditorFromSelected(false);
  window.dispatchEvent(new Event("image-presets-updated"));
 }
 function syncUserPresetEditorFromSelected(updateHelp=true){
  const id=$('#userImagePresetSelect')?.value,p=(S.boot?.user_image_presets||[]).find(x=>x.id===id);if(!p){if(updateHelp)$('#userImagePresetHelp').textContent='Choose a saved preset or create one from the current Image settings.';return}
  const type=p.preset_type||'complete',inc=presetIncludes(p);if($('#userPresetType'))$('#userPresetType').value=type;
  if($('#userPresetSaveModel'))$('#userPresetSaveModel').checked=!!inc.model;if($('#userPresetSaveLoras'))$('#userPresetSaveLoras').checked=!!inc.loras;if($('#userPresetSaveParams'))$('#userPresetSaveParams').checked=!!inc.params;if($('#userPresetSaveStyle'))$('#userPresetSaveStyle').checked=!!inc.style;if($('#userPresetIncludePrompt'))$('#userPresetIncludePrompt').checked=!!inc.prompt;
  renderUserPresetTypeHelp();if(updateHelp)$('#userImagePresetHelp').textContent=`Selected ${p.name} · ${presetTypeLabel(type)} · saved task ${p.task||'image'} · ${(p.loras||[]).length} LoRA.`;
 }
 function currentUserPresetPayload(){
  const type=$('#userPresetType')?.value||'complete',saveModel=!!$('#userPresetSaveModel')?.checked,saveLoras=!!$('#userPresetSaveLoras')?.checked,saveParams=!!$('#userPresetSaveParams')?.checked,saveStyle=!!$('#userPresetSaveStyle')?.checked,includePrompt=!!$('#userPresetIncludePrompt')?.checked;
  return {schema_version:2,preset_type:type,includes:{model:saveModel,loras:saveLoras,params:saveParams,style:saveStyle,workflow:saveStyle,technical_preset:saveStyle,prompt:includePrompt,task:type==='complete'},task:S.task,model_id:$('#modelSelect')?.value||'auto',quick_style:S.imageQuickStyle||'clean',workflow:{id:S.imageWorkflow?.id||'',mode:S.imageWorkflow?.mode||'append',apply_params:!!S.imageWorkflow?.applyParams},technical_preset_id:S.imagePreset?.id||'',params:{seed:Number($('#seed')?.value??-1),scheduler:$('#scheduler')?.value||'default',ratio:$('#ratio')?.value||'',quality:$('#quality')?.value||'',width:Number($('#width')?.value||0),height:Number($('#height')?.value||0),steps:Number($('#steps')?.value||0),cfg:Number($('#cfg')?.value||0),strength:Number($('#strength')?.value||0),batch:Number($('#batch')?.value||1),checkpoint_override:$('#checkpointSelect')?.value||'',inpaint_checkpoint_override:$('#inpaintCheckpointSelect')?.value||'',negative_prompt:includePrompt?($('#negativePrompt')?.value||''):''},loras:(S.loras||[]).map(x=>({name:x.name||String(x.path||'').split('/').pop(),path:x.path||'',strength:Number(x.strength??1)})),include_prompt:includePrompt,prompt:includePrompt?($('#prompt')?.value||''):'',negative_prompt:includePrompt?($('#negativePrompt')?.value||''):''};
 }
 async function saveCurrentUserPreset(){
  const name=prompt('Preset name');if(!name)return;const description=prompt('Short description (optional)')||'',payload={...currentUserPresetPayload(),name,description},d=await api('/api/image/presets/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});S.boot.user_image_presets=d.presets||[];renderUserImagePresetOptions();$('#userImagePresetSelect').value=d.preset.id;syncUserPresetEditorFromSelected();renderUserPresetCards();$('#userImagePresetHelp').textContent=`Saved: ${d.preset.name} · ${presetTypeLabel(d.preset.preset_type)}. Persistent under shared/presets/user/image.`;
 }
 async function updateSelectedUserPreset(){
  const id=$('#userImagePresetSelect')?.value,p=(S.boot?.user_image_presets||[]).find(x=>x.id===id);if(!p)throw new Error('Select a user preset first.');const payload={...currentUserPresetPayload(),id:p.id,name:p.name,description:p.description||''},d=await api('/api/image/presets/user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});S.boot.user_image_presets=d.presets||[];renderUserImagePresetOptions();$('#userImagePresetSelect').value=d.preset.id;syncUserPresetEditorFromSelected();renderUserPresetCards();$('#userImagePresetHelp').textContent=`Updated: ${d.preset.name}.`;
 }
 function applySavedParams(p){const m=p.params||{};for(const [id,key] of [['seed','seed'],['scheduler','scheduler'],['ratio','ratio'],['quality','quality'],['width','width'],['height','height'],['steps','steps'],['cfg','cfg'],['strength','strength'],['batch','batch']])if(m[key]!==undefined&&$('#'+id))$('#'+id).value=m[key];if($('#strengthValue')&&$('#strength'))$('#strengthValue').textContent=Number($('#strength').value||0).toFixed(2);}
 function loadSavedLoras(p){
  const available=new Map((S.boot?.loras||[]).map(x=>[x.path,x])),missing=[];S.loras=[];for(const l of (p.loras||[])){const found=available.get(l.path);if(found)S.loras.push({...found,strength:Number(l.strength??1)});else missing.push(l.name||l.path)}renderLoraStack();return missing;
 }
 function loadSelectedUserPreset(){
  const id=$('#userImagePresetSelect')?.value,p=(S.boot?.user_image_presets||[]).find(x=>x.id===id);if(!p)return;const type=p.preset_type||'complete',inc=presetIncludes(p),warnings=[];
  const preserved={};for(const id of ['seed','ratio','quality','width','height','steps','cfg','strength','batch','scheduler','prompt','negativePrompt','modelSelect','checkpointSelect','inpaintCheckpointSelect'])preserved[id]=$('#'+id)?.value;
  const preservedLoras=(S.loras||[]).map(l=>({...l}));
  if(inc.task&&p.task&&TASKS[p.task])setTask(p.task);
  if(inc.style||inc.workflow||inc.technical_preset)activateCleanImageMode();
  if(!inc.model&&$('#modelSelect')){$('#modelSelect').value=preserved.modelSelect;$('#modelSelect').onchange?.();for(const id of ['checkpointSelect','inpaintCheckpointSelect'])if($('#'+id)&&[...$('#'+id).options].some(o=>o.value===preserved[id]))$('#'+id).value=preserved[id];}
  if(inc.model&&p.model_id&&$('#modelSelect')){if([...$('#modelSelect').options].some(o=>o.value===p.model_id)){$('#modelSelect').value=p.model_id;$('#modelSelect').onchange?.();}else warnings.push(`model ${p.model_id} unavailable`)}
  if(inc.technical_preset){const tp=String(p.technical_preset_id||'');if(tp&&applicableImagePresets().some(x=>x.id===tp))applyImagePreset(tp);else if(tp)warnings.push(`technical preset ${tp} unavailable`)}
  if(inc.workflow){const wf=String(p.workflow?.id||'');if(wf&&applicableImageWorkflows().some(x=>x.id===wf)){if($('#imageWorkflowPromptMode'))$('#imageWorkflowPromptMode').value=p.workflow?.mode||'append';if($('#imageWorkflowApplyParams'))$('#imageWorkflowApplyParams').checked=!!p.workflow?.apply_params;applyImageWorkflow(wf)}else if(wf)warnings.push(`workflow ${wf} unavailable for current task/model`)}
  if(inc.params)applySavedParams(p);
  else for(const id of ['seed','ratio','quality','width','height','steps','cfg','strength','batch','scheduler'])if($('#'+id))$('#'+id).value=preserved[id];
  if(p.params?.seed===undefined&&$('#seed'))$('#seed').value=preserved.seed;
  if(inc.model){for(const [id,key] of [['checkpointSelect','checkpoint_override'],['inpaintCheckpointSelect','inpaint_checkpoint_override']]){
   const value=p.params?.[key];if(value===undefined)continue;
   if($('#'+id)&&[...$('#'+id).options].some(o=>o.value===value))$('#'+id).value=value;
   else if(value)warnings.push(`checkpoint ${value} unavailable`);
  }}
  if($('#strengthValue'))$('#strengthValue').textContent=Number($('#strength').value).toFixed(2);
  if(inc.style)S.imageQuickStyle=p.quick_style||inferQuickStyle();
  if(inc.loras){const missing=loadSavedLoras(p);if(missing.length)warnings.push(`missing LoRA: ${missing.join(', ')}`)}
  if(!inc.loras){S.loras=preservedLoras;renderLoraStack();}
  if(inc.prompt){$('#prompt').value=p.prompt||'';$('#negativePrompt').value=p.negative_prompt||p.params?.negative_prompt||''}
  if(!inc.prompt){$('#prompt').value=preserved.prompt;$('#negativePrompt').value=preserved.negativePrompt;}
  syncQuickStyleButtons();captureImageSettings();updateImageModeUi();renderImageEffectiveState();renderUserPresetCards();$('#userImagePresetHelp').textContent=`Loaded ${p.name} · ${presetTypeLabel(type)}.${warnings.length?` ${warnings.join(' · ')}.`:''}`;
  return {preset:p,warnings};
 }
 function renderStyleBindingHelp(){
  const key=$('#styleBindingTarget')?.value||'anime',box=$('#styleBindingHelp');if(!box)return;const b=bindingFor(key),modelId=String(b.model_id||''),model=(S.boot?.models||[]).find(x=>x.id===modelId),loras=Array.isArray(b.loras)?b.loras:[];
  if(!Object.keys(b).length){box.textContent=`${key}: no model/LoRA binding. Clicking this look uses only its normal workflow/preset logic.`;return}
  box.textContent=`${key}: ${model?.name||modelId||'current/AUTO model'} · ${loras.length?loras.map(x=>`${x.name||x.path||'LoRA'} @ ${Number(x.strength??1).toFixed(2)}`).join(' · '):'no LoRA'}.`;
 }
 async function saveCurrentStyleBinding(){
  const key=$('#styleBindingTarget')?.value||'anime',modelId=$('#modelSelect')?.value||'',loras=(S.loras||[]).map(x=>({path:x.path||'',name:x.name||String(x.path||'').split('/').pop(),strength:Number(x.strength??1),auto_apply:true}));
  const d=await api(`/api/image/preset-bindings/${encodeURIComponent(key)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:modelId==='auto'?'':modelId,loras})});S.boot.image_preset_bindings=d.bindings||{};renderStyleBindingHelp();$('#userImagePresetHelp').textContent=`Bound ${key} to ${modelId==='auto'?'AUTO/current model':modelId} with ${loras.length} LoRA(s).`;
 }
 async function clearCurrentStyleBinding(){
  const key=$('#styleBindingTarget')?.value||'anime',d=await api(`/api/image/preset-bindings/${encodeURIComponent(key)}`,{method:'DELETE'});S.boot.image_preset_bindings=d.bindings||{};renderStyleBindingHelp();
 }
 function highlightImageStart(){
  const el=$('#imageStartPanel');if(!el)return;
  el.classList.remove('image-launch-highlight');
  void el.offsetWidth;
  el.classList.add('image-launch-highlight');
 }
 function inferQuickStyle(){
  const wid=S.imageWorkflow?.id||'';
  const pid=S.imagePreset?.id||'';
  if(wid==='cinematic_upgrade')return 'cinematic';
  if(wid==='anime_serious')return 'anime';
  if(wid==='cartoon_subject')return 'cartoon';
  if(wid==='product_cleanup')return 'product';
  if(wid==='logo_text_graphic')return 'logo';
  if(wid)return 'realistic';
  if(['generate_clean','generate_realistic','portrait_enhance','preserve_balanced','preserve_max'].includes(pid))return 'realistic';
  if(['generate_cinematic','creative_balanced','restyle_strong'].includes(pid))return 'cinematic';
  if(['generate_illustration'].includes(pid))return 'anime';
  if(['product_hero'].includes(pid))return 'product';
  if(['logo_text_clean'].includes(pid))return 'logo';
  return 'clean';
 }
 function syncQuickStyleButtons(){
  const active=S.imageQuickStyle||inferQuickStyle();
  $$('#imageQuickStyleGrid [data-quick-style]').forEach(b=>b.classList.toggle('active',b.dataset.quickStyle===active));
 }
 function renderImageQuickSummary(){
  const mode=(S.imageUiMode||'simple')==='advanced'?'Advanced':'Simple';
  const lookId=S.imageQuickStyle||inferQuickStyle();
  const lookLabel={clean:'Clean',realistic:'Realistic',cinematic:'Cinematic',anime:'Anime',cartoon:'Cartoon',product:'Product',logo:'Logo / Text'}[lookId]||'Clean';
  const task=TASKS[S.task]?.title||S.task;
  const wf=S.imageWorkflow?.id?(S.imageWorkflow.label||S.imageWorkflow.id):'None';
  const pr=S.imagePreset?.id?(S.imagePreset.label||S.imagePreset.id):'None';
  let tail='Manual mode with no workflow or preset armed.';
  if(S.imageWorkflow?.id)tail=`Workflow active: ${wf}.`;
  else if(S.imagePreset?.id)tail=`Preset active: ${pr}.`;
  const model=(S.boot?.models||[]).find(x=>x.id===($('#modelSelect')?.value||''));
  const modelTxt=model?` Model: ${model.name}.`:'';
  const el=$('#imageQuickSummary'); if(el) el.textContent=`${mode} · ${lookLabel} · ${task}. ${tail}${modelTxt}`;
  renderImageEffectiveState();
 }
 function setImageUiMode(mode){
  S.imageUiMode=mode==='advanced'?'advanced':'simple';
  document.body.classList.toggle('image-simple-mode',S.imageUiMode==='simple');
  document.body.classList.toggle('image-advanced-mode',S.imageUiMode==='advanced');
  $('#imageModeSimpleBtn')?.classList.toggle('active',S.imageUiMode==='simple');
  $('#imageModeAdvancedBtn')?.classList.toggle('active',S.imageUiMode==='advanced');
  if(S.imageUiMode==='simple')$$('.advanced.advanced-only').forEach(el=>el.removeAttribute('open'));
  renderImageQuickSummary();
  persistFlowUi();
  window.dispatchEvent(new CustomEvent('imageuimodechange',{detail:{mode:S.imageUiMode}}));
 }
 function applyQuickStyle(styleId){
  const presetExists=id=>applicableImagePresets().some(p=>p.id===id);
  const workflowExists=id=>applicableImageWorkflows().some(w=>w.id===id);
  S.imageQuickStyle=styleId||'clean';
  if(styleId==='clean'){
    clearBoundStyleLoras();
    activateCleanImageMode();
    captureImageSettings();
    syncQuickStyleButtons();
    renderImageQuickSummary();
    persistFlowUi();
    return;
  }
  if(styleId==='realistic'){
    clearActiveWorkflow(true);
    if(S.task==='generate'){
      if(presetExists('generate_realistic'))applyImagePreset('generate_realistic');
      else if(presetExists('generate_clean'))applyImagePreset('generate_clean');
    }else{
      if(presetExists('portrait_enhance'))applyImagePreset('portrait_enhance');
      else if(presetExists('preserve_balanced'))applyImagePreset('preserve_balanced');
    }
  }else if(styleId==='cinematic' && workflowExists('cinematic_upgrade')) applyImageWorkflow('cinematic_upgrade');
  else if(styleId==='anime' && workflowExists('anime_serious')) applyImageWorkflow('anime_serious');
  else if(styleId==='cartoon' && workflowExists('cartoon_subject')) applyImageWorkflow('cartoon_subject');
  else if(styleId==='product' && workflowExists('product_cleanup')) applyImageWorkflow('product_cleanup');
  else if(styleId==='logo'){
    if(S.task!=='generate')setTask('generate');
    if(workflowExists('logo_text_graphic'))applyImageWorkflow('logo_text_graphic');
  }
  applyPresetBinding(styleId,{clearPrevious:true});
  syncQuickStyleButtons();
  renderImageQuickSummary();
  persistFlowUi();
 }
 
 const _updateImageModeUi=updateImageModeUi;
 updateImageModeUi=function(){
  _updateImageModeUi();
  const inferred=inferQuickStyle();
  if(!S.imageQuickStyle || (S.imageQuickStyle==='clean' && (S.imageWorkflow?.id||S.imagePreset?.id)) || inferred!==S.imageQuickStyle)S.imageQuickStyle=inferred;
  syncQuickStyleButtons();
  renderImageQuickSummary();
 };
 
 const _populateModelSelect=populateModelSelect;
 populateModelSelect=function(){ _populateModelSelect(); renderImageQuickSummary(); };
 
 handleHomeLaunch=function(btn){
  const goto=btn.dataset.goto||'';
  const task=btn.dataset.task||'';
  const workflow=btn.dataset.workflow||'';
  const preset=btn.dataset.preset||'';
  const clean=btn.dataset.clean==='1';

  const identityMode=btn.dataset.identityMode||'';
  if(task)setTask(task);
  if(goto==='image'&&clean){activateCleanImageMode();S.imageQuickStyle='clean';}
  if(workflow&&$('#imageWorkflowSelect'))$('#imageWorkflowSelect').value=workflow;
  if(preset&&$('#imagePresetSelect'))$('#imagePresetSelect').value=preset;
  if(workflow)applyImageWorkflow(workflow);
  if(preset)applyImagePreset(preset);
  if(goto)showView(goto);
  if(identityMode){loadIdentity().then(()=>setIdentityMode(identityMode)).catch(()=>setIdentityMode(identityMode));}
  if(goto==='image'){
    setImageUiMode('simple');
    highlightImageStart();
  }
  window.scrollTo({top:0,behavior:'smooth'});
 };
 $$('.home-launch-card').forEach(b=>b.onclick=()=>handleHomeLaunch(b));
 
 function bindAdvancedAccordion(){
  $$('#view-image details.advanced-group').forEach(group=>group.addEventListener('toggle',()=>{
   if(!group.open)return;
   $$('#view-image details.advanced-group').forEach(other=>{if(other!==group)other.open=false});
  }));
 }
 restoreFlowUi();
 bindAdvancedAccordion();
 $('#imageModeSimpleBtn')?.addEventListener('click',()=>setImageUiMode('simple'));
 $('#imageModeAdvancedBtn')?.addEventListener('click',()=>setImageUiMode('advanced'));
 $$('#imageQuickStyleGrid [data-quick-style]').forEach(b=>b.addEventListener('click',()=>applyQuickStyle(b.dataset.quickStyle)));
 $('#viewEffectivePromptBtn')?.addEventListener('click',showEffectivePrompt);
 $('#closeEffectivePrompt')?.addEventListener('click',()=>$('#effectivePromptModal').classList.add('hidden'));
 $('#userPresetType')?.addEventListener('change',e=>applyPresetTypeDefaults(e.target.value));
 $('#userImagePresetSelect')?.addEventListener('change',()=>{syncUserPresetEditorFromSelected();renderUserPresetCards()});
 $('#saveUserImagePreset')?.addEventListener('click',()=>saveCurrentUserPreset().catch(e=>alert(e.message)));
 $('#updateUserImagePreset')?.addEventListener('click',()=>updateSelectedUserPreset().catch(e=>alert(e.message)));
 $('#loadUserImagePreset')?.addEventListener('click',loadSelectedUserPreset);
 $('#duplicateUserImagePreset')?.addEventListener('click',async()=>{const id=$('#userImagePresetSelect')?.value;if(!id)return;try{const d=await api(`/api/image/presets/user/${encodeURIComponent(id)}/duplicate`,{method:'POST'});S.boot.user_image_presets=d.presets||[];renderUserImagePresetOptions();$('#userImagePresetSelect').value=d.preset.id;syncUserPresetEditorFromSelected();renderUserPresetCards()}catch(e){alert(e.message)}});
 $('#deleteUserImagePreset')?.addEventListener('click',async()=>{const id=$('#userImagePresetSelect')?.value;if(!id||!confirm('Delete this user preset?'))return;try{const d=await api(`/api/image/presets/user/${encodeURIComponent(id)}`,{method:'DELETE'});S.boot.user_image_presets=d.presets||[];renderUserImagePresetOptions();renderUserPresetCards()}catch(e){alert(e.message)}});
 $('#exportUserImagePreset')?.addEventListener('click',()=>{const id=$('#userImagePresetSelect')?.value;if(id)window.location.href=`/api/image/presets/user/${encodeURIComponent(id)}/download`;});
 $('#importUserImagePreset')?.addEventListener('change',async e=>{const file=e.target.files?.[0];if(!file)return;try{const fd=new FormData();fd.append('file',file);const d=await api('/api/image/presets/user/import',{method:'POST',body:fd});S.boot.user_image_presets=d.presets||[];renderUserImagePresetOptions();renderUserPresetCards();e.target.value='';$('#userImagePresetHelp').textContent=`Imported ${d.imported||0} preset(s).`;}catch(err){alert(err.message)}});
  
 
 
 
 
 
$('#styleBindingTarget')?.addEventListener('change',renderStyleBindingHelp);
 $('#saveStyleBinding')?.addEventListener('click',()=>saveCurrentStyleBinding().catch(e=>alert(e.message)));
 $('#clearStyleBinding')?.addEventListener('click',()=>clearCurrentStyleBinding().catch(e=>alert(e.message)));
 document.addEventListener('input',e=>{if(['prompt','negativePrompt','steps','cfg','strength','quality'].includes(e.target?.id))renderImageEffectiveState()});
 
 applyPresetTypeDefaults($('#userPresetType')?.value||'complete');
 renderStyleBindingHelp();
 setImageUiMode(S.imageUiMode||'simple');
 syncQuickStyleButtons();
 renderImageQuickSummary();
 window.PresetEngine={
  payload:currentUserPresetPayload, includes:presetIncludes, defaults:applyPresetTypeDefaults,
  refresh:renderUserImagePresetOptions, snapshot:currentEffectiveSnapshot, inspect:showEffectivePrompt,
  setMode:setImageUiMode,
  load(id){$('#userImagePresetSelect').value=id;return loadSelectedUserPreset();},
  clear(){activateCleanImageMode();S.imageQuickStyle='clean';syncQuickStyleButtons();captureImageSettings();renderImageEffectiveState();},
  apply(kind,id){
   const mode=$('#imageWorkflowPromptMode').value,applyParams=$('#imageWorkflowApplyParams').checked;
   activateCleanImageMode();
   if(kind==='recipe'){$('#imageWorkflowPromptMode').value=mode;$('#imageWorkflowApplyParams').checked=applyParams;}
   if(kind==='recipe')applyImageWorkflow(id);else applyImagePreset(id);
   S.imageQuickStyle=inferQuickStyle();syncQuickStyleButtons();renderImageEffectiveState();captureImageSettings();
  }
 };
 window.renderUserImagePresetOptions=renderUserImagePresetOptions;
 
 window.renderImageEffectiveState=renderImageEffectiveState;
 window.applyImagePresetBinding=(key)=>applyPresetBinding(key,{clearPrevious:false});
 // v0.1.75.1: bootstrap runs earlier in this file, so late-defined preset renderers
 // must also render themselves once they are registered on window.
 renderUserImagePresetOptions();

 renderImageEffectiveState();
})();

['width','height'].forEach(id=>document.getElementById(id)?.addEventListener('input',()=>{document.getElementById('ratio').value='Custom';captureImageSettings()}));
