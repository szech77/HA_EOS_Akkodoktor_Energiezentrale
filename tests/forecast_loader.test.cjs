const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/app.js'),'utf8');
function fixture(){
 const ids={'flow-weather':{disabled:false},'weather-dialog':{},'forecast-close':{},'forecast-body':{}};
 const calls={scripts:[],opened:0,renders:0},options={fail:false,brokenDialog:false,stall:false};
 const ctx={URL,Date,Promise,setTimeout,clearTimeout,location:{href:'https://ha.test/static/index.html?v=old'},
  appScriptUrl:'https://ha.test/static/app.js?v=new-build',snapshot:{},language:{locale:'de'},t:key=>key,html:String,decimal:String,
  api(){},byId:id=>ids[id],render(){calls.renders++;},requestError:code=>Object.assign(new Error('safe error'),{code}),
  document:{createElement:()=>({remove(){}}),head:{append(node){calls.scripts.push(node);if(options.stall)return;
   queueMicrotask(()=>{if(options.fail)node.onerror();else{ctx.EosForecast={create(){return {open(){if(options.brokenDialog)throw Error('dialog unavailable');calls.opened++;}};}};node.onload();}});
  }}}};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf('let forecastView=null;'),script.indexOf("byId('flow-weather').addEventListener")),ctx);
 return {ctx,calls,options,ids,failed:()=>vm.runInContext('forecastOpenFailure',ctx)};
}

test('weather click loads the missing module when a cached bootstrap omitted it',async()=>{
 const f=fixture();assert.equal(f.ctx.EosForecast,undefined);
 await f.ctx.openWeatherForecast();
 assert.equal(f.calls.scripts.length,1);
 assert.equal(f.calls.scripts[0].src,'https://ha.test/static/forecast.js?v=new-build');
 assert.equal(f.calls.opened,1);assert.equal(f.failed(),false);assert.equal(f.ids['flow-weather'].disabled,false);
 await f.ctx.openWeatherForecast();assert.equal(f.calls.scripts.length,1);assert.equal(f.calls.opened,2);
});

test('concurrent module requests are coalesced and repeated clicks cannot create duplicate dialogs',async()=>{
 const f=fixture(),first=f.ctx.ensureForecastModule(),second=f.ctx.ensureForecastModule();
 assert.equal(first,second);await first;assert.equal(f.calls.scripts.length,1);
 await Promise.all([f.ctx.openWeatherForecast(),f.ctx.openWeatherForecast()]);
 assert.equal(f.calls.opened,1);
});

test('a failed module load leaves the overview alive and the next click can retry',async()=>{
 const f=fixture();f.options.fail=true;await f.ctx.openWeatherForecast();
 assert.equal(f.failed(),true);assert.equal(f.ids['flow-weather'].disabled,false);assert.equal(f.calls.renders,1);
 f.options.fail=false;await f.ctx.openWeatherForecast();
 assert.equal(f.failed(),false);assert.equal(f.calls.opened,1);assert.equal(f.calls.scripts.length,2);
});

test('dialog errors and mismatched markup are caught instead of escaping the event handler',async()=>{
 for(const missingMarkup of [false,true]){
  const f=fixture();f.options.brokenDialog=true;if(missingMarkup)f.ids['weather-dialog']=null;
  await assert.doesNotReject(f.ctx.openWeatherForecast());
  assert.equal(f.failed(),true);assert.equal(f.ids['flow-weather'].disabled,false);assert.equal(f.calls.renders,1);
 }
});

test('a stalled module request times out and re-enables the weather button',async()=>{
 const f=fixture();f.options.stall=true;
 f.ctx.setTimeout=callback=>{queueMicrotask(callback);return 1;};f.ctx.clearTimeout=()=>{};
 await f.ctx.openWeatherForecast();
 assert.equal(f.failed(),true);assert.equal(f.ids['flow-weather'].disabled,false);
});
