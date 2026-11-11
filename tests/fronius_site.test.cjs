const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
function fixture(language){
 const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
 const t=(key,values={})=>{assert.equal(typeof messages[key],'string',key);return messages[key].replace(/\{(\w+)\}/g,(_match,name)=>values[name]??'');};
 const html=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
 const ctx={valid:Number.isFinite,html,t,th:(key,values)=>html(t(key,values)),decimal:String,
  power:value=>Number.isFinite(value)?Math.abs(value)/1000+' kW':'—',percent:value=>Number.isFinite(value)?value+' %':'—'};
 vm.runInNewContext(script.slice(script.indexOf('function batteryGroupDetails('),script.indexOf('function settings()')),ctx);
 return ctx;
}
test('group diagnostics identify PV-only units, storage SoC and combined capacity in both languages',()=>{
 for(const language of ['de','en']){
  const ctx=fixture(language);
  const result=ctx.batteryGroupDetails({inverter_count:2,battery_count:1,capacity_wh:10000,devices:[
   {name:'primary',battery:true,soc:0,solar:2000,ac:-500,available:true},
   {name:'roof',battery:false,solar:1200,ac:1200,available:true}]});
  assert.match(result,/10 kWh/);assert.match(result,/SoC 0 %/);assert.match(result,/AC − 0.5 kW/);
  assert.match(result,/roof/);assert.match(result,language==='de'?/Nur PV/:/PV only/);
 }
});
test('missing measurements stay unknown and device names are escaped',()=>{
 const ctx=fixture('de');
 assert.equal(ctx.batteryGroupDetails(undefined),'');
 const result=ctx.batteryGroupDetails({inverter_count:2,battery_count:2,devices:[
  {name:'<device>',battery:true,soc:null,solar:null,ac:null,available:false}]});
 assert.match(result,/&lt;device&gt;/);assert.doesNotMatch(result,/<device>/);
 assert.match(result,/SoC —/);assert.match(result,/Messwerte unvollständig/);
});
