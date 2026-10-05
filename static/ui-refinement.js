/* Zetalvx Image Lab — SDXL Edition 0.1.0.26. Safe areas are CSS-driven, not guessed from user-agent.
   VisualViewport is only used to hide navigation during text input/keyboard overlap. */
(()=>{
 'use strict';
 const root=document.documentElement, viewport=window.visualViewport;
 const dock=document.querySelector('.mobile-dock'),more=document.querySelector('#mobileMoreMenu');
 const toggle=document.querySelector('#mobileMoreToggle');
 let frame=0;
 function editable(el){return !!el?.matches('textarea,input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=file]):not([type=button]):not([type=submit]),[contenteditable=true]');}
 function sync(){
  frame=0;
  const focused=editable(document.activeElement), mobile=matchMedia('(max-width:900px)').matches;
  const overlap=viewport?Math.max(0,window.innerHeight-viewport.height-viewport.offsetTop):0;
  const keyboard=mobile&&focused&&(!viewport||viewport.scale<1.15)&&overlap>150;
  root.classList.toggle('ui-keyboard-open',keyboard);
  if(dock){dock.inert=keyboard;dock.setAttribute('aria-hidden',String(keyboard));}
  if(keyboard&&more&&!more.classList.contains('hidden'))more.classList.add('hidden');
  toggle?.setAttribute('aria-expanded',String(!!more&&!more.classList.contains('hidden')));
 }
 function schedule(){if(!frame)frame=requestAnimationFrame(sync);}
 viewport?.addEventListener('resize',schedule);viewport?.addEventListener('scroll',schedule);
 window.addEventListener('resize',schedule);window.addEventListener('pageshow',schedule);
 document.addEventListener('focusin',schedule);document.addEventListener('focusout',()=>setTimeout(schedule,50));
 if(more)new MutationObserver(schedule).observe(more,{attributes:true,attributeFilter:['class']});
 document.addEventListener('keydown',e=>{
  if(!more||more.classList.contains('hidden'))return;
  if(e.key==='Escape'){more.classList.add('hidden');toggle?.focus();}
  if(e.key==='Tab'){
   const items=[...more.querySelectorAll('button:not(:disabled),a[href]')].filter(x=>x.offsetParent!==null);
   if(!items.length)return;const first=items[0],last=items[items.length-1];
   if(e.shiftKey&&(document.activeElement===first||!more.contains(document.activeElement))){e.preventDefault();last.focus();}
   else if(!e.shiftKey&&(document.activeElement===last||!more.contains(document.activeElement))){e.preventDefault();first.focus();}
  }
 },true);
 sync();
})();
