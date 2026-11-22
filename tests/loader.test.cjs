'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const web=path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web');
const script=fs.readFileSync(path.join(web,'loader.js'),'utf8');

async function load(fails=false){
  const node=extra=>({hidden:false,textContent:'',...extra});
  const nodes={app:node(),startup:node({hidden:true}),notice:node(),'startup-details':node({hidden:true}),'startup-detail':node(),'startup-details-title':node(),
    'startup-retry':node({hidden:true,addEventListener(_event,callback){this.click=callback;}})};
  const listeners={},resources=[],stylesheet={};let replaced;
  const context={URL,Date,encodeURIComponent,Number,console:{warn(){}},navigator:{language:'de-DE'},
    location:{href:'http://ha.test/index.html?v=build123&lang=de',replace(url){replaced=url;}},
    window:{addEventListener(name,handler){listeners[name]=handler;}},
    document:{getElementById:id=>nodes[id],querySelector:selector=>selector==='link[rel=icon]'?null:stylesheet,createElement:()=>({}),
      head:{append(element){resources.push(element.src);queueMicrotask(()=>fails?element.onerror():element.onload());}}}};
  vm.runInNewContext(script,context);
  await new Promise(resolve=>setImmediate(resolve));
  return {nodes,resources,stylesheet,replaced:()=>replaced,emitError:event=>listeners.error(event)};
}

test('the panel loads one bundle and the stylesheet with the build version of the page',async()=>{
  const f=await load();
  assert.deepEqual(f.resources,['./vue/eos-vue.js?v=build123']);
  assert.equal(f.stylesheet.href,'./style.css?v=build123');
  assert.equal(f.nodes.startup.hidden,true);
  assert.equal(f.nodes['startup-retry'].hidden,true);
});

test('a missing bundle names the build output and offers a cache-refresh retry',async()=>{
  const f=await load(true);
  assert.match(f.nodes.notice.textContent,/vue\/eos-vue\.js/);
  assert.equal(f.nodes.startup.hidden,false);
  assert.equal(f.nodes.app.hidden,true);
  assert.equal(f.nodes['startup-retry'].hidden,false);
  f.nodes['startup-retry'].click();
  assert.notEqual(new URL(f.replaced()).searchParams.get('v'),'build123');
});

test('a runtime error of the bundle is named without its raw message and keeps a running panel',async()=>{
  const f=await load();
  f.emitError({filename:'https://ha.test/eos-energiezentrale-static/vue/eos-vue.js?v=build123',lineno:1,error:{name:'TypeError',message:'private raw error'}});
  assert.match(f.nodes.notice.textContent,/JavaScript-Fehler/);
  assert.doesNotMatch(f.nodes.notice.textContent,/nicht laden/);
  assert.equal(f.nodes['startup-detail'].textContent,'vue/eos-vue.js:1:TypeError');
  assert.doesNotMatch(f.nodes['startup-detail'].textContent,/private raw error/);
  assert.equal(f.nodes.app.hidden,false);
  // Errors of other scripts (e.g. browser extensions) are not attributed to the panel.
  const other=await load();
  other.emitError({filename:'https://ha.test/extension.js',lineno:3,error:{name:'Error'}});
  assert.equal(other.nodes.startup.hidden,true);
});

test('the page contains only the app mount point and the startup message; no inline script',()=>{
  const markup=fs.readFileSync(path.join(web,'index.html'),'utf8');
  assert.match(markup,/<div id="app"><\/div>/);
  assert.match(markup,/<script src="\.\/loader\.js" defer><\/script>/);
  assert.equal((markup.match(/<script/g)??[]).length,1);
  for(const id of ['notice','startup-retry','startup-details','startup-detail','startup-details-title'])assert.match(markup,new RegExp(`id="${id}"`));
  for(const file of ['app.js','accounting.js','bootstrap.js'])assert.equal(fs.existsSync(path.join(web,file)),false,file);
});
