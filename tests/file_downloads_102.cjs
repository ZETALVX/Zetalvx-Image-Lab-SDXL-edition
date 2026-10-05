/* Actual frontend script in a DOM/fetch fixture, not native-browser transport. */
'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),crypto=require('crypto'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../static/file-downloads.js'),'utf8');
const fixture=Buffer.from('fixture LoRA '+String.fromCodePoint(232));
const head=(n=fixture.length)=>new Response(null,{headers:{'Content-Length':String(n),'Content-Disposition':"attachment; filename*=UTF-8''prova%20%C3%A8.safetensors"}});
const body=(b=fixture,n=b.length)=>new Response(b,{headers:{'Content-Length':String(n),'Content-Disposition':'attachment; filename="test.safetensors"','Content-Type':'application/octet-stream'}});
function env(handler,href='https://studio.test/api/training/loras/abc/download'){
 const saved=[],calls=[],blobs=[],timers=[];let listener,status=null;
 class FakeURL extends URL{static createObjectURL(b){blobs.push(b);return 'blob:fixture'} static revokeObjectURL(){throw Error('must not revoke immediately')}}
 const anchor={href,dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},parentElement:{querySelector(sel){return sel==='[data-file-download-status]'?status:null},append(e){if(e.tagName!=='A')status=e}}};
 anchor.closest=()=>anchor;
 const doc={body:{append(){}},createElement(tag){if(tag==='a')return {tagName:'A',setAttribute(){},click(){saved.push({href:this.href,name:this.download})},remove(){}};return {setAttribute(){},classList:{toggle(){}},textContent:''}},addEventListener(e,fn){if(e==='click')listener=fn}};
 const context={window:{},document:doc,location:new URL('https://studio.test/'),URL:FakeURL,Blob,console,setTimeout(fn,ms){timers.push(ms)},fetch:async(u,o)=>{calls.push({u,o});return handler(u,o)}};
 vm.runInNewContext(code,context);
 function click(){listener({target:anchor,button:0,preventDefault(){},defaultPrevented:false})}
 async function wait(){for(let i=0;i<100;i++){await new Promise(r=>setImmediate(r));if(!anchor.attrs['aria-busy'])return;}throw Error('download did not settle')}
 return {click,wait,saved,calls,blobs,timers,text:()=>status?.textContent||''};
}
const results=[];
async function run(name,fn){await fn();results.push({name,passed:true});console.log('PASS',name)}
(async()=>{
 await run('same-session HEAD GET exact Blob SHA',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():body());e.click();await e.wait();assert.equal(e.calls.length,2);assert.ok(e.calls.every(x=>x.o.credentials==='same-origin'&&x.o.redirect==='error'&&x.o.cache==='no-store'));assert.equal(e.saved[0].href,'blob:fixture');assert.equal(crypto.createHash('sha256').update(Buffer.from(await e.blobs[0].arrayBuffer())).digest('hex'),crypto.createHash('sha256').update(fixture).digest('hex'));assert.equal(e.timers[0],120000)});
 await run('unicode Content-Disposition filename',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():new Response(fixture,{headers:{'Content-Length':String(fixture.length),'Content-Disposition':"attachment; filename*=UTF-8''prova%20%C3%A8.safetensors"}}));e.click();await e.wait();assert.equal(e.saved[0].name,'prova è.safetensors')});
 await run('HEAD401 visible session error',async()=>{let e=env(()=>new Response(null,{status:401}));e.click();await e.wait();assert.match(e.text(),/Session expired/);assert.equal(e.calls.length,1);assert.equal(e.saved.length,0)});
 await run('HEAD404 not saved as weights',async()=>{let e=env(()=>new Response(null,{status:404}));e.click();await e.wait();assert.match(e.text(),/404/);assert.equal(e.saved.length,0)});
 await run('JSON200 without attachment rejected',async()=>{let e=env(()=>new Response('{}',{headers:{'Content-Type':'application/json'}}));e.click();await e.wait();assert.match(e.text(),/downloadable file/);assert.equal(e.saved.length,0)});
 await run('GET401 after valid HEAD rejected',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():new Response(null,{status:401}));e.click();await e.wait();assert.match(e.text(),/Session expired/);assert.equal(e.saved.length,0)});
 await run('foreign origin refused without network',async()=>{let e=env(()=>{throw Error('unexpected network')},'https://foreign.invalid/export');e.click();await e.wait();assert.match(e.text(),/same-origin/);assert.equal(e.calls.length,0)});
 await run('large file uses native URL not Blob',async()=>{let e=env(()=>head(128*1024*1024+1));e.click();await e.wait();assert.equal(e.calls.length,1);assert.equal(e.blobs.length,0);assert.match(e.saved[0].href,/^https:/);assert.match(e.text(),/handed to the browser/) });
 await run('unknown size native fallback',async()=>{let e=env(()=>new Response(null,{headers:{'Content-Disposition':'attachment; filename="file.zip"'}}));e.click();await e.wait();assert.equal(e.blobs.length,0);assert.equal(e.saved[0].name,'file.zip')});
 await run('file growth above memory limit refused',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():body(fixture,128*1024*1024+1));e.click();await e.wait();assert.match(e.text(),/size changed/);assert.equal(e.saved.length,0)});
 await run('truncated stream never saved',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():body(fixture,fixture.length+1));e.click();await e.wait();assert.match(e.text(),/Incomplete/);assert.equal(e.saved.length,0)});
 await run('oversized actual stream refused',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():body(fixture,fixture.length-1));e.click();await e.wait();assert.match(e.text(),/Unexpected download size/);assert.equal(e.saved.length,0)});
 await run('double click creates one transfer',async()=>{let e=env((u,o)=>o.method==='HEAD'?head():body());e.click();e.click();await e.wait();assert.equal(e.calls.length,2);assert.equal(e.saved.length,1)});
 await run('network error shown and state cleared',async()=>{let e=env(()=>{throw Error('Network fixture unavailable')});e.click();await e.wait();assert.match(e.text(),/Network fixture unavailable/);assert.equal(e.saved.length,0)});
 if(process.argv[2])fs.writeFileSync(process.argv[2],JSON.stringify({type:'DOM/fetch fixture, actual frontend source; not browser/TLS acceptance',checks:results},null,2));
})().catch(e=>{console.error(e);process.exitCode=1});
