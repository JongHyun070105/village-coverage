import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import Module, { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';
const loadModule = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function api() {
  process.env.NEXT_PUBLIC_PUBLIC_DEMO_MODE = 'true';
  const filename = path.resolve(__dirname, '../lib/api.ts');
  const mod = new Module(filename);
  mod.paths = Module._nodeModulePaths(path.dirname(filename));
  mod._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText, filename);
  return mod.exports;
}
const ok = () => Response.json({ status: 'ok' });

test('health is shared, data waits for readiness, and cheap GETs are deduplicated', async () => {
  const { apiRequest } = api();
  let release;
  const health = new Promise(resolve => { release = resolve; });
  const calls = [];
  global.fetch = async url => {
    calls.push(url);
    if (url === '/api/health') { await health; return ok(); }
    return Response.json({ regions: [] });
  };
  const a = apiRequest('/api/regions');
  const b = apiRequest('/api/regions');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls, ['/api/health']);
  release();
  await Promise.all([a,b]);
  assert.deepEqual(calls, ['/api/health','/api/regions']);
});

test('solver GET and POST are never automatically repeated', async () => {
  const { apiRequest } = api();
  const calls = [];
  global.fetch = async url => {
    calls.push(url);
    return ['/api/health','/api/regions'].includes(url) ? ok() : new Response('gateway', { status: 503 });
  };
  for (const [url, method] of [['/api/overview','GET'], ['/api/regions/x/reserve-comparison','GET'], ['/api/schedules','POST']]) {
    await assert.rejects(apiRequest(url, { method }));
    assert.equal(calls.filter(x=>x===url).length, 1);
  }
});

test('typed errors and 500 do not poll health again or repeat GET', async () => {
  for (const [status, code] of [[500, 'HTTP_500'], [503,'ROUTE_UNAVAILABLE'], [503,'DEMO_SESSION_UNAVAILABLE'], [410,'DEMO_SESSION_EXPIRED']]) {
    const { apiRequest } = api();
    let reads = 0;
    global.fetch = async url => {
      if (url === '/api/health') return ok();
      reads++;
      return Response.json({code}, {status, headers:{'Retry-After':'8'}});
    };
    await assert.rejects(apiRequest('/api/regions'), e => e.code===code && (status!==429 || e.retryAfterSeconds===8));
    assert.equal(reads,1);
  }
});

test('a cancelled waiter does not cancel another waiter or turn into a timeout', async () => {
  const { apiRequest } = api();
  let release;
  const health = new Promise(resolve => { release=resolve; });
  global.fetch = async url => { if(url==='/api/health') await health; return ok(); };
  const controller = new AbortController();
  const a = apiRequest('/api/regions', { signal:controller.signal });
  const b = apiRequest('/api/regions');
  const rejected = assert.rejects(a, e=>e.name==='AbortError');
  controller.abort();
  release();
  await rejected;
  assert.deepEqual(await b, {status:'ok'});
});

test('root env loader accepts only the three documented public configuration keys', () => {
  const filename = path.resolve(__dirname,'../next.config.ts');
  const config = ts.transpileModule(fs.readFileSync(filename,'utf8'), {
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,esModuleInterop:true},
  }).outputText;
  const env = {};
  const sandbox = { exports:{}, process:{ env, cwd:()=>'/synthetic/frontend' }, require:name=> {
    if(name==='node:fs') return {readFileSync:()=> 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000\nNEXT_PUBLIC_KAKAO_MAP_JS_KEY=synthetic-browser-key\nNEXT_PUBLIC_PUBLIC_DEMO_MODE=true\nNEXT_PUBLIC_UNEXPECTED_SECRET=synthetic-private-key\nGEMINI_API_KEY=synthetic-private-key'};
    return loadModule(name);
  }};
  vm.runInNewContext(config,sandbox);
  assert.equal(env.NEXT_PUBLIC_API_BASE_URL,'http://localhost:8000');
  assert.equal(env.NEXT_PUBLIC_PUBLIC_DEMO_MODE,'true');
  assert.equal(env.NEXT_PUBLIC_UNEXPECTED_SECRET,undefined);
  assert.equal(env.GEMINI_API_KEY,undefined);
});

test('health recovers from untyped 503 before any data is fetched', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  const { apiRequest, getApiReadiness } = api();
  let health = 0;
  let data = 0;
  global.fetch = async url => {
    if (url === '/api/health') return ++health < 3 ? new Response('preparing', {status:503}) : ok();
    data++; return ok();
  };
  const result = apiRequest('/api/regions');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(data,0);
  t.mock.timers.tick(1000);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(getApiReadiness(),'SERVER_WAKING');
  t.mock.timers.tick(2000);
  await result;
  assert.equal(health,3);
  assert.equal(data,1);
});

test('health polling stops within 120 seconds and exposes manual recovery', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  const { apiRequest, getApiReadiness } = api();
  let probes = 0;
  global.fetch = async url => { assert.equal(url,'/api/health'); probes++; return new Response('preparing',{status:503}); };
  const result = assert.rejects(apiRequest('/api/regions'), e=>e.code==='SERVER_WAKE_TIMEOUT');
  for(let n=0;n<10;n++) {
    await new Promise(resolve=>setImmediate(resolve));
    t.mock.timers.tick(15_000);
  }
  await result;
  assert.equal(getApiReadiness(),'RETRY_AVAILABLE');
  assert.ok(probes<=12);
});

test('Retry-After HTTP date delays cheap GET until the indicated time', async t => {
  t.mock.timers.enable({apis:['setTimeout','Date']});
  const { apiRequest } = api();
  let reads=0;
  global.fetch=async url=>{
    if(url==='/api/health')return ok();
    if(++reads===1)return Response.json({}, {status:429,headers:{'Retry-After':new Date(Date.now()+60_000).toUTCString()}});
    return ok();
  };
  const result=apiRequest('/api/regions');
  await new Promise(resolve=>setImmediate(resolve));
  t.mock.timers.tick(59_999);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(reads,1);
  t.mock.timers.tick(1000);
  await result;
  assert.equal(reads,2);
});

test('a stalled solver GET has a deadline and is not repeated', async t => {
  t.mock.timers.enable({apis:['setTimeout','Date']});
  const { apiRequest }=api();
  let reads=0;
  global.fetch=async (url,init)=>{
    if(['/api/health','/api/regions'].includes(url))return ok();
    reads++;
    return new Promise((resolve,reject)=>init.signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true}));
  };
  const result=assert.rejects(apiRequest('/api/overview'), e=>e.code==='REQUEST_TIMEOUT');
  await new Promise(resolve=>setImmediate(resolve));
  t.mock.timers.tick(60_000);
  await result;
  assert.equal(reads,1);
});

test('health 429 stays a rate limit error with Retry-After', async () => {
  const { apiRequest }=api();
  let probes=0;
  global.fetch=async ()=>{probes++;return Response.json({}, {status:429,headers:{'Retry-After':'180'}});};
  await assert.rejects(apiRequest('/api/regions'),e=>e.status===429 && e.retryAfterSeconds===180);
  assert.equal(probes,1);
});

test('cancellation while creating a shared read aborts the orphaned fetch', async () => {
  const { apiRequest }=api();
  const caller=new AbortController();
  let fetchSignal;
  global.fetch=async (url,init)=>{
    if(url==='/api/health')return ok();
    fetchSignal=init.signal;
    caller.abort();
    return Response.json({regions:[]});
  };
  await assert.rejects(apiRequest('/api/regions',{signal:caller.signal}),e=>e.name==='AbortError');
  assert.equal(fetchSignal.aborted,true);
});

for (const kind of ['json','html','render']) {
  test(`first regions ${kind} 429 waits then recovers with one shared request`, async t=>{
    t.mock.timers.enable({apis:['setTimeout','Date']});
    const {apiRequest,getApiReadiness}=api();let reads=0;
    global.fetch=async url=>{
      if(url==='/api/health')return ok();
      if(++reads>1)return Response.json({regions:['ready']});
      const headers={'Retry-After':'2'};
      if(kind==='render')headers['x-render-routing']='hibernate-rate-limited';
      return kind==='json' ? Response.json({code:'DEMO_SESSION_RATE_LIMITED'},{status:429,headers})
        : new Response('<private upstream body>',{status:429,headers:{...headers,'Content-Type':'text/html'}});
    };
    const a=apiRequest('/api/regions');const b=apiRequest('/api/regions');
    await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,1);
    assert.equal(getApiReadiness(),'SERVER_WAKING');
    t.mock.timers.tick(1999);await new Promise(resolve=>setImmediate(resolve));assert.equal(reads,1);
    t.mock.timers.tick(1000);assert.deepEqual(await a,{regions:['ready']});await b;assert.equal(reads,2);
  });
}

test('generic 429 is not attributed; proven Render marker is upstream',async()=>{
  for(const [marker,code] of [[undefined,'HTTP_429'],['hibernate-rate-limited','UPSTREAM_RATE_LIMITED']]){
    const {apiRequest}=api();let reads=0;
    global.fetch=async url=>{
      if(url==='/api/health')return ok();reads++;
      return new Response('internal body',{status:429,headers:{'Retry-After':'180',...(marker?{'x-render-routing':marker}:{})}});
    };
    await assert.rejects(apiRequest('/api/regions'),e=>e.code===code && !e.message.includes('internal body'));assert.equal(reads,1);
  }
});

test('429 without hint has bounded exponential backoff, then manual error',async t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});const {apiRequest}=api();const times=[];
  global.fetch=async url=>{if(url==='/api/health')return ok();times.push(Date.now());return new Response('limited',{status:429});};
  const done=assert.rejects(apiRequest('/api/regions'),e=>e.code==='HTTP_429');
  for(let n=0;n<5;n++){await new Promise(resolve=>setImmediate(resolve));t.mock.timers.tick(16_000);}
  await done;assert.equal(times.length,4);assert.ok(times[1]-times[0]>=1000);assert.ok(times[2]-times[1]>=2000);
});

test('cancelled 429 backoff stops all further requests',async t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});const {apiRequest}=api();const controller=new AbortController();let reads=0;
  global.fetch=async url=>{if(url==='/api/health')return ok();reads++;return new Response('',{status:429,headers:{'Retry-After':'2'}});};
  const done=assert.rejects(apiRequest('/api/regions',{signal:controller.signal}),e=>e.name==='AbortError');
  await new Promise(resolve=>setImmediate(resolve));controller.abort();await done;t.mock.timers.tick(10_000);assert.equal(reads,1);
});

test('health 429 recovers before requesting data',async t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});const {apiRequest}=api();let health=0;
  global.fetch=async url=>url==='/api/health' && ++health===1 ? new Response('too many',{status:429,headers:{'Retry-After':'2'}}):ok();
  const done=apiRequest('/api/regions');await new Promise(resolve=>setImmediate(resolve));t.mock.timers.tick(3000);await done;assert.equal(health,2);
});

test('parallel fresh reads establish session before owner-scoped reads',async()=>{
  const {apiRequest}=api();let release;let established=false;const calls=[];const bootstrap=new Promise(resolve=>{release=resolve;});
  global.fetch=async url=>{if(url==='/api/health')return ok();calls.push(url);if(url==='/api/regions'){await bootstrap;established=true;}else assert.equal(established,true);return ok();};
  const a=apiRequest('/api/providers');const b=apiRequest('/api/schedules');await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(calls,['/api/regions']);release();await Promise.all([a,b]);assert.equal(calls.length,3);
});
