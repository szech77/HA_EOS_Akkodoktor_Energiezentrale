const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const forecast=require('../custom_components/eos_energiezentrale/energy/web/forecast.js');
const start=Date.parse('2026-11-12T07:00:00Z'),hour=3600000;
const slot=(from,to,solar)=>({time:new Date(start+from*hour).toISOString(),end:new Date(start+to*hour).toISOString(),solar});

test('PV energy clips the exact next 24 hours and never counts overlapping intervals twice',()=>{
 const slots=forecast.solarSlots([slot(0,2,4000),slot(-1,1,2000),slot(2,30,1000)],start);
 assert.deepEqual(forecast.solarSummary(slots),{kwh:28,peak:4,complete:true,covered:24*hour});
 assert.equal(slots[0].start,start);assert.equal(slots.at(-1).end,start+24*hour);
});
test('missing and invalid PV remains unknown while measured forecast zero is a covered interval',()=>{
 const slots=forecast.solarSlots([slot(0,1,0),slot(1,2,null),slot(2,3,NaN),slot(3,4,-1),slot(4,5,'1000')],start);
 assert.deepEqual(forecast.solarSummary(slots),{kwh:0,peak:0,complete:false,covered:hour});
 assert.equal(forecast.valueAt(slots,start+2*hour),undefined);
 assert.equal(forecast.solarSummary([]).kwh,null);
});
test('24 elapsed hours stay 24 hours across daylight-saving transitions',()=>{
 for(const date of ['2026-03-29T00:00:00Z','2026-10-25T00:00:00Z']){
  const stamp=Date.parse(date),rows=[{time:date,end:new Date(stamp+25*hour).toISOString(),solar:1000}];
  assert.equal(forecast.solarSummary(forecast.solarSlots(rows,stamp)).kwh,24);
 }
});

class Element {
 constructor(){this.handlers={};this.open=false;this.hidden=true;this.attributes={};this.style={};this.dataset={};}
 addEventListener(name,handler){this.handlers[name]=handler;}
 setAttribute(key,value){this.attributes[key]=value;}
 removeAttribute(key){delete this.attributes[key];}
 focus(){this.focused=true;}
 showModal(){this.open=true;}
 close(){this.open=false;this.handlers.close?.();}
 getBoundingClientRect(){return {left:0,top:0,width:100,right:100,bottom:100};}
 querySelector(key){return this.parts[key];}
}
function fixture(request,code='de'){
 const language=JSON.parse(fs.readFileSync(path.join(__dirname,`../custom_components/eos_energiezentrale/energy/i18n/${code}.json`),'utf8'));
 const ids=Object.fromEntries(['weather-dialog','forecast-body','forecast-title','forecast-close','flow-weather'].map(id=>[id,new Element()]));
 const snapshot={zone:'Europe/Berlin',live:{weather:{condition:'sunny',temperature:8,unit:'°C'}},forecast:[slot(0,24,1000)]};
 let plots=[];
 Object.defineProperty(ids['forecast-body'],'innerHTML',{set(value){
  this.markup=value;
  for(const id of ['forecast-hour','forecast-retry','forecast-selected'])ids[id]=new Element();
  plots=[...value.matchAll(/data-forecast-plot="(\w+)"/g)].map(match=>{
   const node=new Element();node.dataset.forecastPlot=match[1];node.parts={'.forecast-probe':new Element(),'.forecast-tooltip':new Element()};return node;
  });
 }});
 ids['forecast-body'].querySelectorAll=()=>plots;
 const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const t=key=>{assert.equal(typeof language.messages[key],'string',key);return language.messages[key];};
 const view=forecast.create({document:{getElementById:id=>ids[id]},getSnapshot:()=>snapshot,request,t,html,
  decimal:(value,digits=1)=>new Intl.NumberFormat(language.locale,{maximumFractionDigits:digits}).format(value),getLocale:()=>language.locale,now:()=>start});
 return {view,ids,snapshot,plots:()=>plots,t,markup:()=>ids['forecast-body'].markup};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const weather={status:'available',temperature_unit:'°C',source:'<provider>',rows:[{
 time:new Date(start).toISOString(),end:new Date(start+hour).toISOString(),temperature:0,precipitation:0,condition:'sunny',precipitation_probability:0}]};

test('dialog opens weather above PV, shares a probe, and renders German and English without injecting provider names',async()=>{
 for(const code of ['de','en']){
  const f=fixture(async()=>weather,code);f.view.open();await flush();
  assert.equal(f.ids['weather-dialog'].open,true);
  assert.ok(f.markup().indexOf(f.t('forecast.weather'))<f.markup().indexOf(f.t('forecast.pv')));
  assert.match(f.markup(),/24 kWh/);assert.match(f.markup(),/&lt;provider&gt;/);assert.doesNotMatch(f.markup(),/<provider>/);
  assert.equal(f.plots().length,2);
  f.ids['forecast-hour'].handlers.input({target:{value:'0'}});
  assert.match(f.ids['forecast-selected'].textContent,/0 °C/);assert.match(f.ids['forecast-selected'].textContent,/0 mm/);
  for(const plot of f.plots())assert.equal(plot.parts['.forecast-probe'].attributes.x1,0);
  f.ids['forecast-hour'].handlers.input({target:{value:'2'}});
  assert.ok(f.ids['forecast-selected'].textContent.includes(f.t('forecast.no_hour')));
  assert.match(f.ids['forecast-selected'].textContent,/1 kW/);
  f.ids['forecast-close'].handlers.click();assert.equal(f.ids['weather-dialog'].open,false);assert.equal(f.ids['flow-weather'].focused,true);
 }
});

test('slow or failed weather leaves PV visible and late responses cannot reopen a closed dialog',async()=>{
 let release;const f=fixture(()=>new Promise(resolve=>release=resolve));f.view.open();
 assert.match(f.markup(),/24 kWh/);assert.ok(f.markup().includes(f.t('forecast.loading')));
 f.ids['weather-dialog'].close();release(weather);await flush();assert.equal(f.ids['weather-dialog'].open,false);
 const g=fixture(async()=>{throw Error('private-provider-response');});g.view.open();await flush();
 assert.ok(g.markup().includes(g.t('forecast.unavailable')));assert.match(g.markup(),/24 kWh/);
 assert.doesNotMatch(g.markup(),/private-provider-response/);
});

test('unsupported weather and incomplete PV are explicit and updates preserve the selected timestamp',async()=>{
 const f=fixture(async()=>({status:'unsupported',rows:[]}));f.snapshot.forecast=[slot(0,1,1000)];
 f.view.open();await flush();assert.ok(f.markup().includes(f.t('forecast.unsupported')));
 assert.ok(f.markup().includes(f.t('forecast.partial')));
 f.ids['forecast-hour'].handlers.input({target:{value:'2'}});
 assert.match(f.ids['forecast-selected'].textContent,/—/);
 f.snapshot.forecast=[slot(0,24,2000)];f.view.update();
 assert.match(f.ids['forecast-selected'].textContent,/2 kW/);assert.match(f.markup(),/48 kWh/);
});
