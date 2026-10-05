/* 1.0.11 — snapshot selected upload bytes; no resize, recompression or POST retry. */
(function(root){
 'use strict';
 const MAX_BODY=128*1024*1024, OVERHEAD=64*1024, READ_TIMEOUT=30000;
 const copies=new WeakMap();
 function failure(message,code){const e=new Error(message);e.code=code;return e;}
 function copyFile(file){
  if(copies.has(file))return copies.get(file);
  const pending=new Promise((resolve,reject)=>{
   let reader=null,settled=false;
   const finish=(err,buf)=>{if(settled)return;settled=true;clearTimeout(timer);
    if(err){copies.delete(file);reject(failure('A selected image could not be read. Reselect the images and try again.','identity_file_unreadable'));return;}
    if(buf.byteLength!==file.size||buf.byteLength===0){copies.delete(file);reject(failure('A selected image is empty or incomplete. Reselect it and try again.','identity_file_incomplete'));return;}
    resolve(new Blob([buf],{type:file.type||'application/octet-stream'}));
   };
   const timer=setTimeout(()=>{finish(new Error('timeout'));try{reader?.abort()}catch(_){}},READ_TIMEOUT);
   try{
    if(root.FileReader){reader=new root.FileReader();reader.onload=()=>finish(null,reader.result);reader.onerror=reader.onabort=()=>finish(new Error('read'));reader.readAsArrayBuffer(file);}
    else Promise.resolve(file.arrayBuffer()).then(b=>finish(null,b),e=>finish(e));
   }catch(e){finish(e)}
  });
  copies.set(file,pending);pending.catch(()=>copies.delete(file));return pending;
 }
 async function prepare(form){
  // Snapshot entries before any await: input/mode changes cannot mix requests.
  const entries=[...form.entries()];let bytes=OVERHEAD;
  for(const [,value] of entries)bytes+=typeof value==='string'?new TextEncoder().encode(value).length:value.size;
  if(bytes>MAX_BODY)throw failure('Identity upload exceeds the server limits. Use smaller images or fewer attachments.','identity_upload_too_large');
  const output=new FormData();
  for(const [name,value] of entries){
   if(typeof value==='string'){output.append(name,value);continue;}
   output.append(name,await copyFile(value),value.name||'image');
  }
  return output;
 }
 function nonJsonError(status){
  const messages={400:'Identity upload could not be read. No job was queued. Reselect the images and try again.',413:'Identity upload exceeds the server limits. Use smaller images or fewer attachments.',401:'Authentication required',403:'Identity request was refused. Check your session and try again.'};
  const e=failure(messages[status]||'Identity response was not readable. Check Queue & history before sending again.','identity_http_response');
  e.status=status;e.submissionUncertain=!(status>=400&&status<500);return e;
 }
 root.ZetalvxIdentitySubmit={prepare,nonJsonError};
})(typeof window!=='undefined'?window:globalThis);
