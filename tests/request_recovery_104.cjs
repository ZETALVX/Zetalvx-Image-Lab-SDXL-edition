'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(require('path').join(__dirname,'../static/request-recovery.js'),'utf8');
let calls=[],handler;let tests=0;
const ctx={URL,AbortController,TypeError,Error,Promise,console,globalThis:null,
 document:{baseURI:'https://creator.local/'},
 setTimeout:(f,n)=>setTimeout(f,Math.min(n,15)),clearTimeout,
 fetch:(url,opt)=>{calls.push([url,opt]);return handler(url,opt)}};
ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);const api=ctx.ZetalvxRequestRecovery;
function reply(status=200,text='{}'){return {status,ok:status>=200&&status<300,text:async()=>text};}
async function check(name,fn){calls=[];await fn();tests++;console.log('PASS '+name);}
(async()=>{
 await check('GET retries a Load failed once',async()=>{handler=()=>calls.length===1?Promise.reject(new TypeError('Load failed')):Promise.resolve(reply());await api.fetchText('/api/identity/bootstrap');assert.equal(calls.length,2);});
 await check('failed POST never retried',async()=>{handler=()=>Promise.reject(new TypeError('Load failed'));await assert.rejects(api.fetchText('/api/identity/jobs',{method:'POST'}),e=>e.submissionUncertain===true);assert.equal(calls.length,1);});
 await check('POST timeout never retried and rejects',async()=>{handler=()=>new Promise(()=>{});await assert.rejects(api.fetchText('/api/jobs',{method:'POST'}),e=>e.code==='request_timeout'&&e.submissionUncertain);assert.equal(calls.length,1);});
 await check('GET header/body stalls bounded',async()=>{handler=()=>Promise.resolve({...reply(),text:()=>new Promise(()=>{})});await assert.rejects(api.fetchText('/api/identity/bootstrap'),e=>e.code==='request_timeout');assert.equal(calls.length,2);});
 await check('GET 503 retry bounded',async()=>{handler=()=>Promise.resolve(reply(503));assert.equal((await api.fetchText('/api/identity/bootstrap')).response.status,503);assert.equal(calls.length,2);});
 await check('POST 500 remains server error not network retry',async()=>{handler=()=>Promise.resolve(reply(500,'{"error":"CUDA out of memory"}'));const r=await api.fetchText('/api/identity/jobs',{method:'POST'});assert.match(r.text,/out of memory/);assert.equal(calls.length,1);});
 await check('401 not retried nor bypassed',async()=>{handler=()=>Promise.resolve(reply(401));assert.equal((await api.fetchText('/api/identity/bootstrap')).response.status,401);assert.equal(calls.length,1);});
 await check('explicit caller abort not retried',async()=>{const c=new AbortController();c.abort();await assert.rejects(api.fetchText('/api/identity/bootstrap',{signal:c.signal}),e=>e.name==='AbortError');assert.equal(calls.length,0);});
 await check('credentials/CSRF/body preserved',async()=>{handler=(_,opt)=>{assert.equal(opt.credentials,'same-origin');assert.equal(opt.body,'original');assert.equal(opt.headers['X-CSRF-Token'],'token');return Promise.resolve(reply(202));};await api.fetchText('/api/identity/jobs',{method:'POST',body:'original',headers:{'X-CSRF-Token':'token'}});});
 await check('unrelated model uploads/long validation unaffected',async()=>{for(const url of ['/api/training/loras/id/validate','/api/model-hub/uploads'])assert.equal(api.policy(url,{method:'POST'}).timeout,0);});
 await check('GET response body interruption retried',async()=>{handler=()=>Promise.resolve(calls.length===1?{...reply(),text:()=>Promise.reject(new TypeError('Load failed'))}:reply());await api.fetchText('/api/projects/test');assert.equal(calls.length,2);});
 await check('read failure cannot assert generation failed',async()=>{handler=()=>Promise.reject(new TypeError('offline'));await assert.rejects(api.fetchText('/api/projects/test'),e=>e.code==='network_error'&&!e.submissionUncertain);});
 console.log(JSON.stringify({passed:tests,failed:0}));
})().catch(e=>{console.error(e);process.exitCode=1});
