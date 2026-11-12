const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/bootstrap.js'),'utf8');
async function bootstrap(failingFile){
  const nodes={notice:{},overview:{hidden:false},'startup-details':{hidden:true},'startup-detail':{},'startup-details-title':{},'startup-retry':{hidden:true,addEventListener(_event,callback){this.click=callback;}}};
  const listeners={};
  const resources=[],stylesheet={};let replaced;
  const context={URL,Date,Error,Promise,encodeURIComponent,navigator:{language:'de-DE'},
    location:{href:'http://ha.test/index.html?v=build123&lang=de',replace(url){replaced=url;}},
    window:{addEventListener(name,handler){listeners[name]=handler;}},document:{getElementById:id=>nodes[id],querySelector:selector=>selector==='link[rel=icon]'?null:stylesheet,querySelectorAll:()=>[],createElement:()=>({}),
      head:{append(node){resources.push(node.src);queueMicrotask(()=>node.src.includes(failingFile??'never-match')?node.onerror():node.onload());}}}};
  vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));
  return {nodes,resources,stylesheet,replaced:()=>replaced,emitError:event=>listeners.error(event)};
}
test('all UI dependencies share the build version instead of mixing cached releases',async()=>{
  const f=await bootstrap();
  assert.deepEqual(f.resources,['./chart-data.js?v=build123','./accounting.js?v=build123','./forecast.js?v=build123','./app.js?v=build123']);
  assert.equal(f.stylesheet.href,'./style.css?v=build123');
  assert.equal(f.nodes['startup-retry'].hidden,true);
});
test('a missing script names the actual file and offers a cache-refresh retry',async()=>{
  const f=await bootstrap('accounting.js');
  assert.ok(f.nodes.notice.textContent.includes('accounting.js'));
  assert.ok(!f.nodes.notice.textContent.includes('/api/language'));
  assert.equal(f.nodes.overview.hidden,true);
  assert.equal(f.nodes['startup-retry'].hidden,false);
  f.nodes['startup-retry'].click();
  assert.notEqual(new URL(f.replaced()).searchParams.get('v'),'build123');
});

test('a runtime error is not called a missing file and does not hide an already running overview',async()=>{
 const f=await bootstrap();
 f.emitError({filename:'https://ha.test/app.js?v=build123',lineno:759,error:{name:'ReferenceError',message:'private raw error'}});
 assert.match(f.nodes.notice.textContent,/JavaScript-Fehler/);
 assert.doesNotMatch(f.nodes.notice.textContent,/nicht laden/);
 assert.equal(f.nodes.overview.hidden,false);assert.equal(f.nodes['startup-retry'].hidden,false);
 assert.equal(f.nodes['startup-detail'].textContent,'app.js:759:ReferenceError');
 assert.doesNotMatch(f.nodes['startup-detail'].textContent,/private raw error/);
});
