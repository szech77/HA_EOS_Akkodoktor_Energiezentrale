const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/app.js'),'utf8');
function fixture(){
 const ids={'pv-view':{}};
 const calls={scripts:[],opened:0,renders:0},options={fail:false,brokenDialog:false,stall:false};
 const ctx={URL,Date,Promise,setTimeout,clearTimeout,location:{href:'https://ha.test/static/index.html?v=old'},
  appScriptUrl:'https://ha.test/static/app.js?v=new-build',snapshot:{},language:{locale:'de'},t:key=>key,html:String,decimal:String,
  api(){},windowNow:()=>0,byId:id=>ids[id],render(){calls.renders++;},requestError:code=>Object.assign(new Error('safe error'),{code}),
  document:{createElement:()=>({remove(){}}),head:{append(node){calls.scripts.push(node);if(options.stall)return;
   queueMicrotask(()=>{if(options.fail)node.onerror();else{ctx.EosForecast={create(){return {open(){if(options.brokenDialog)throw Error('view unavailable');calls.opened++;}};}};node.onload();}});
  }}}};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf('let forecastView=null;'),script.indexOf("byId('flow-weather').addEventListener")),ctx);
 return {ctx,calls,options,ids,failed:()=>vm.runInContext('forecastOpenFailure',ctx)};
}

test('opening the PV page loads the missing module when a cached bootstrap omitted it',async()=>{
 const f=fixture();assert.equal(f.ctx.EosForecast,undefined);
 await f.ctx.openPvView();
 assert.equal(f.calls.scripts.length,1);
 assert.equal(f.calls.scripts[0].src,'https://ha.test/static/vue/eos-vue.js?v=new-build');
 assert.equal(f.calls.opened,1);assert.equal(f.failed(),false);assert.equal(vm.runInContext('pvViewLoading',f.ctx),false);
 await f.ctx.openPvView();assert.equal(f.calls.scripts.length,1);assert.equal(f.calls.opened,2);
});

test('concurrent module requests are coalesced and repeated renders cannot open the page twice',async()=>{
 const f=fixture(),first=f.ctx.ensureForecastModule(),second=f.ctx.ensureForecastModule();
 assert.equal(first,second);await first;assert.equal(f.calls.scripts.length,1);
 await Promise.all([f.ctx.openPvView(),f.ctx.openPvView()]);
 assert.equal(f.calls.opened,1);
});

test('a failed module load leaves the panel alive, reports once and the next visit can retry',async()=>{
 const f=fixture();f.options.fail=true;await f.ctx.openPvView();
 assert.equal(f.failed(),true);assert.equal(vm.runInContext('pvViewLoading',f.ctx),false);assert.equal(f.calls.renders,1);
 f.options.fail=false;await f.ctx.openPvView();
 assert.equal(f.failed(),false);assert.equal(f.calls.opened,1);assert.equal(f.calls.scripts.length,2);
});

test('view errors and mismatched markup are caught instead of escaping the render loop',async()=>{
 for(const missingMarkup of [false,true]){
  const f=fixture();f.options.brokenDialog=true;if(missingMarkup)f.ids['pv-view']=null;
  await assert.doesNotReject(f.ctx.openPvView());
  assert.equal(f.failed(),true);assert.equal(vm.runInContext('pvViewLoading',f.ctx),false);assert.equal(f.calls.renders,1);
 }
});

test('a stalled module request times out and can be retried',async()=>{
 const f=fixture();f.options.stall=true;
 f.ctx.setTimeout=callback=>{queueMicrotask(callback);return 1;};f.ctx.clearTimeout=()=>{};
 await f.ctx.openPvView();
 assert.equal(f.failed(),true);assert.equal(vm.runInContext('pvViewLoading',f.ctx),false);
});

test('the chart helper module is loaded with the app build version when a cached bootstrap omitted it',async()=>{
 const f=fixture();
 f.ctx.document.head.append=node=>{f.calls.scripts.push(node);queueMicrotask(()=>{f.ctx.EosChartData={powerFraction(){}};node.onload();});};
 const ready=()=>typeof f.ctx.EosChartData?.powerFraction==='function'?f.ctx.EosChartData:null;
 const loaded=await f.ctx.ensureModule('chart-data.js',ready);
 assert.equal(loaded,f.ctx.EosChartData);
 assert.equal(f.calls.scripts[0].src,'https://ha.test/static/chart-data.js?v=new-build');
 await f.ctx.ensureModule('chart-data.js',ready);assert.equal(f.calls.scripts.length,1);
 // A file that loads but does not provide the module is reported by name.
 const g=fixture();g.ctx.document.head.append=node=>queueMicrotask(()=>node.onload());
 await assert.rejects(g.ctx.ensureModule('chart-data.js',()=>null),error=>error.code==='asset_mismatch'&&error.asset==='chart-data.js');
});
