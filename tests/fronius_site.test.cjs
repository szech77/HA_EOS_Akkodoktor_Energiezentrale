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
  assert.match(result,/10 kWh/);assert.match(result,/SoC: <strong>0 %/);assert.match(result,/AC[^:]*: <strong>− 0.5 kW/);
  assert.match(result,/roof/);assert.match(result,language==='de'?/Nur PV/:/PV only/);
 }
});
test('missing measurements stay unknown and device names are escaped',()=>{
 const ctx=fixture('de');
 assert.equal(ctx.batteryGroupDetails(undefined),'');
 const result=ctx.batteryGroupDetails({inverter_count:2,battery_count:2,devices:[
  {name:'<device>',battery:true,soc:null,solar:null,ac:null,available:false}]});
 assert.match(result,/&lt;device&gt;/);assert.doesNotMatch(result,/<device>/);
 assert.match(result,/SoC: <strong>—/);assert.match(result,/Messwerte unvollständig/);
});

test('Victron firmware diagnostics show backend version, source and raw registers in both languages',()=>{
 for(const language of ['de','en']){
  const ctx=fixture(language);
  const render=firmware=>ctx.batteryGroupDetails({devices:[{name:'GX',battery:true,measurements:{},
   read_diagnostics:{firmware}}]});
  const manual=render({version:'v3.66',source:'configured',register_status:'reserved',raw_words:[65535,65535]});
  assert.match(manual,/Venus OS: <strong>v3.66/);
  assert.match(manual,language==='de'?/manuell angegeben/:/manually configured/);
  assert.match(manual,/0xFFFF 0xFFFF/);
  const detected=render({version:'v3.74~42',source:'detected',register_status:'valid',raw_words:[0x0374,0x42]});
  assert.match(detected,/v3.74~42/);
  assert.match(detected,language==='de'?/automatisch erkannt/:/automatically detected/);
  const unknown=render({version:null,source:'unknown',register_status:'unsupported',raw_words:null});
  assert.match(unknown,language==='de'?/unbekannt/:/unknown/);
  assert.doesNotMatch(unknown,/v3.66/);
  assert.match(render({version:'<unsafe>',source:'unknown',register_status:'invalid',raw_words:null}),/&lt;unsafe&gt;/);
 }
});

test('Victron shows its declared consumption and grid values without an unsupported AC placeholder',()=>{
 for(const language of ['de','en']){
  const ctx=fixture(language);
  const result=ctx.batteryGroupDetails({inverter_count:1,battery_count:1,devices:[
   {name:'Victron',battery:true,soc:100,available:true,measurements:{solar:250,house_total:408,grid:0}}]});
  assert.match(result,language==='de'?/PV-Leistung/:/PV power/);
  assert.match(result,language==='de'?/Hausverbrauch/:/House consumption/);
  assert.match(result,/0.408 kW/);assert.match(result,/0 kW/);
  assert.doesNotMatch(result,/Wechselrichter AC|Inverter AC|—/);
  const missing=ctx.batteryGroupDetails({inverter_count:1,battery_count:0,devices:[
   {name:'PV',battery:false,available:false,measurements:{solar:0,inverter_ac:null}}]});
  assert.match(missing,language==='de'?/Wechselrichter AC-Leistung: <strong>—/:/Inverter AC power: <strong>—/);
 }
});

test('mixed plugin names are escaped and the pooled EOS approximation is visible',()=>{
 for(const language of ['de','en']){
  const ctx=fixture(language);
  const result=ctx.batteryGroupDetails({inverter_count:2,battery_count:2,approximate:true,devices:[
   {name:'storage',battery:true,plugin:{name:'<custom plugin>'},soc:55,available:true}]});
  assert.match(result,/&lt;custom plugin&gt;/);assert.doesNotMatch(result,/<custom plugin>/);
  assert.match(result,language==='de'?/angenäherte EOS-Planung/:/approximate EOS planning/);
 }
});

test('removing the last battery shows a configuration hint',()=>{
 for(const language of ['de','en']){
  const ctx=fixture(language);
  const result=ctx.batteryGroupDetails({inverter_count:0,battery_count:0,devices:[]});
  assert.match(result,language==='de'?/Kein Speicher eingerichtet/:/No battery configured/);
 }
});
