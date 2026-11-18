const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const backend=require('./backend.cjs');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const markupFile=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const now=Date.parse('2026-11-18T17:50:00Z'),iso=new Date(now).toISOString();

function render(view,code='de'){
  const language=JSON.parse(fs.readFileSync(path.join(root,`i18n/${code}.json`),'utf8'));
  const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const t=(key,values={})=>{assert.equal(typeof language.messages[key],'string',key);return language.messages[key].replace(/\{(\w+)\}/g,(_,name)=>values[name]??`{${name}}`);};
  const ctx={language,snapshot:{zone:'Europe/Berlin'},html,t,th:(key,values)=>html(t(key,values)),valid:Number.isFinite,Intl,Date,
    decimal:(value,digits=1)=>new Intl.NumberFormat(language.locale,{maximumFractionDigits:digits}).format(value)};
  vm.createContext(ctx);
  vm.runInContext(script.slice(script.indexOf('// Numeric source diagnostics'),script.indexOf('function settings()')),ctx);
  return ctx.sourceDiagnostics(view);
}
const plugin={type:'plugin',name:'Configured devices'};
const data={live:{time:iso,solar:0,grid:10,house_total:940,house:940,heat:0,car:0,battery_soc:87,battery_charge:0,battery_discharge:510},
  features:{car:true,heat:true},
  plugins:{battery:{name:'Configured devices',measurements:['battery_soc','battery_charge','battery_discharge']},wallbox:{name:'go-e <v2>',measurements:['car']}},
  source_configuration:{missing:[],unavailable:['heat'],sources:{
    solar:{source:plugin,available:true,reason:null,max_age_s:45,sample:iso},
    grid:{source:plugin,available:true,reason:null,max_age_s:45,sample:iso},
    house_total:{source:plugin,available:true,reason:null,max_age_s:120,sample:iso},
    heat:{source:{type:'sensor',name:'sensor.heat_pump'},available:false,reason:'stale',max_age_s:120,sample:new Date(now-300000).toISOString()}}},
  battery_group:{devices:[{name:'Victron',battery:true,available:true,plugin:{name:'Victron GX'},soc:87,charge:0,discharge:510,measurements:{grid:10,house_total:940}}]}};

test('settings show every configured source with numeric values, age and status',()=>{
  const view=backend('sourceDiagnostics',data,{now});
  const markup=render(view);
  assert.match(markup,/<td>Netzanschlussleistung<\/td><td>Plugin: Configured devices<\/td><td class="num">10 W<\/td><td class="num">0 s<\/td><td>OK<\/td>/);
  assert.match(markup,/<tr class="warn"><td>Wärmepumpenleistung<\/td><td>Sensor: <code>sensor\.heat_pump<\/code><\/td><td class="num">—<\/td><td class="num">300 s<\/td><td>veraltet \(max\. 120 s\)<\/td>/);
  assert.match(markup,/Speicher-Entladeleistung<\/td><td>Plugin: Configured devices<\/td><td class="num">510 W/);
  assert.match(markup,/Plugin: go-e &lt;v2&gt;/);assert.doesNotMatch(markup,/<v2>/);
  assert.match(markup,/Stand 18:50:00/);
});
test('the energy balance explains why consumption is booked as unknown',()=>{
  const markup=render(backend('sourceDiagnostics',data,{now}));
  assert.match(markup,/Quellen: PV \+ Netzbezug \+ Speicherentladung<\/td><td class="num">520 W/);
  assert.match(markup,/Bilanzrest \(Quellen − Senken\)<\/strong><\/td><td class="num">−420 W/);
  assert.match(markup,/<tr class="warn"><td colspan="2"><strong>Bilanz geht nicht auf/);
  assert.match(markup,/<h3>Victron · Victron GX<\/h3>/);assert.match(markup,/Speicher-SoC<\/td><td class="num">87 %/);
  const balanced=render(backend('sourceDiagnostics',{...data,live:{...data.live,house_total:500,house:500}},{now}),'en');
  assert.match(balanced,/<tr class=""><td colspan="2"><strong>Balance closes/);
});
test('no diagnostics yet and the settings panel exists',()=>{
  assert.match(render(undefined),/Noch keine Messwerte/);
  assert.match(markupFile,/<details class="plan-panel" id="source-diagnostics-panel"><summary data-i18n="diagnostics.title"><\/summary>/);
});
