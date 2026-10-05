/* 1.0.8: Identity-only incremental rendering. No timers, navigation or job submission. */
(()=>{'use strict';
 const state=new WeakMap(),textState=new WeakMap();
 const template=html=>{const t=document.createElement('template');t.innerHTML=html;return t.content};
 function patch(live,before,after){
  // Compare source templates, not translated DOM: unchanged text, image nodes and
  // injected download controls must not be rewritten by a poll or language switch.
  if(before.isEqualNode(after))return live;
  if(before.nodeType!==after.nodeType||before.nodeName!==after.nodeName||(before.nodeType!==Node.DOCUMENT_FRAGMENT_NODE&&(live.nodeType!==before.nodeType||live.nodeName!==before.nodeName))){
   const n=after.cloneNode(true);live.replaceWith(n);return n;
  }
  if(after.nodeType===Node.TEXT_NODE||after.nodeType===Node.COMMENT_NODE){live.nodeValue=after.nodeValue;return live;}
  if(after.nodeType===Node.ELEMENT_NODE){
   for(const a of before.attributes)if(!after.hasAttribute(a.name))live.removeAttribute(a.name);
   for(const a of after.attributes)if(before.getAttribute(a.name)!==a.value)live.setAttribute(a.name,a.value);
  }
  const old=[...before.childNodes],next=[...after.childNodes],nodes=[...live.childNodes];
  if(old.length!==next.length||nodes.length!==old.length){live.replaceChildren(...next.map(n=>n.cloneNode(true)));return live;}
  for(let i=0;i<next.length;i++)patch(nodes[i],old[i],next[i]);
  return live;
 }
 function html(box,value){
  if(!box)return;const prior=state.get(box);
  if(prior?.raw===value)return;
  const next=template(value);
  if(prior?.source)patch(box,prior.source,next);else box.replaceChildren(next.cloneNode(true));
  state.set(box,{raw:value,source:next.cloneNode(true)});
 }
 function rows(box,value,attribute){
  if(!box)return;const next=template(value),incoming=[...next.children];
  if(!incoming.length||incoming.some(n=>!n.hasAttribute(attribute))){html(box,value);return;}
  const prior=state.get(box),records=prior?.rows||new Map(),updated=new Map();
  const existing=new Map([...box.children].filter(n=>n.hasAttribute(attribute)).map(n=>[n.getAttribute(attribute),n]));
  let cursor=box.firstChild;
  for(const source of incoming){
   const key=source.getAttribute(attribute);let live=existing.get(key);const previous=records.get(key);
   if(live&&previous){const wasCursor=live===cursor;live=patch(live,previous,source);if(wasCursor)cursor=live;}
   else if(live){const wasCursor=live===cursor;const replacement=source.cloneNode(true);live.replaceWith(replacement);live=replacement;if(wasCursor)cursor=live;}
   else live=source.cloneNode(true);
   if(live!==cursor)box.insertBefore(live,cursor);
   cursor=live.nextSibling;updated.set(key,source.cloneNode(true));existing.delete(key);
  }
  while(cursor){const next=cursor.nextSibling;cursor.remove();cursor=next;}
  state.set(box,{rows:updated});
 }
 function text(node,value){if(!node||textState.get(node)===value)return;textState.set(node,value);if(node.textContent!==value)node.textContent=value;}
 window.ZetalvxIdentityDOM={html,rows,text};
})();
