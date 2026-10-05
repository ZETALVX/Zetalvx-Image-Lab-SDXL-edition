/* UI-only layout and visibility. Does not change seed, model, prompt or queue. */
(()=>{
 'use strict';
 const by=id=>document.getElementById(id),t=s=>window.ZI18n?.t(s)||s;
 const key='creator_sdxl_preview_side',layout=by('imageCreatorLayout'),btn=by('imageLayoutSwapBtn');
 let side='right';try{const saved=localStorage.getItem(key);if(saved==='left'||saved==='right')side=saved;}catch(_){}
 function drawLayout(){
  layout?.classList.toggle('image-preview-right',side==='right');
  btn?.setAttribute('aria-pressed',String(side==='right'));
  if(by('imageLayoutSwapLabel'))by('imageLayoutSwapLabel').textContent=t(side==='right'?'Preview: right':'Preview: left');
  if(btn)btn.title=t('Swap preview and settings. Queue and history stay below.');
 }
 btn?.addEventListener('click',()=>{side=side==='left'?'right':'left';try{localStorage.setItem(key,side);}catch(_){}drawLayout();});
 function complexity(){
  const simple=S.imageUiMode!=='advanced';
  by('imageModeSimpleBtn')?.setAttribute('aria-pressed',String(simple));
  by('imageModeAdvancedBtn')?.setAttribute('aria-pressed',String(!simple));
  if(by('imageModeHelp'))by('imageModeHelp').textContent=t(simple?
    'Simple: everyday controls and applying presets. Switch to Advanced for saving presets, comparisons and manual parameters. Existing values are kept.':
    'Advanced: save/manage presets, recipe options, automatic/custom comparisons and manual seed, steps, CFG, batch and scheduler.');
  if(by('presetSummaryTitle'))by('presetSummaryTitle').textContent=t(simple?'Quick presets':'Presets');
  if(by('presetSummaryHelp'))by('presetSummaryHelp').textContent=t(simple?'Choose and apply; saving and management are in Advanced.':'Choose a setup, apply it, or save your own');
 }
 by('openAdvancedPresets')?.addEventListener('click',()=>{
  window.PresetEngine?.setMode('advanced');by('workflowPresetSuite').open=true;by('presetTabSave')?.click();
 });
 window.addEventListener('imageuimodechange',complexity);
 window.addEventListener('languagechange',()=>{drawLayout();complexity();});
 drawLayout();complexity();
})();
