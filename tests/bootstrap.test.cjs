const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/bootstrap.js'),'utf8');
async function bootstrap(failingFile){
  const nodes={notice:{},overview:{hidden:false},'startup-retry':{hidden:true,addEventListener(_event,callback){this.click=callback;}}};
  const resources=[],stylesheet={};let replaced;
  const context={URL,Date,Error,Promise,encodeURIComponent,navigator:{language:'de-DE'},
    location:{href:'http://ha.test/index.html?v=build123&lang=de',replace(url){replaced=url;}},
    window:{addEventListener(){}},document:{getElementById:id=>nodes[id],querySelector:selector=>selector==='link[rel=icon]'?null:stylesheet,querySelectorAll:()=>[],createElement:()=>({}),
      head:{append(node){resources.push(node.src);queueMicrotask(()=>node.src.includes(failingFile??'never-match')?node.onerror():node.onload());}}}};
  vm.runInNewContext(script,context);await new Promise(resolve=>setImmediate(resolve));
  return {nodes,resources,stylesheet,replaced:()=>replaced};
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
