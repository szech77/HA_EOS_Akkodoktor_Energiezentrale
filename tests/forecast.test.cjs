const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const forecast=require('../custom_components/eos_energiezentrale/energy/web/forecast.js');
const backend=require('./backend.cjs');
// 14:30 local time in Berlin.
const now=Date.parse('2026-11-18T13:30:00Z'),hour=3600000,iso=ms=>new Date(ms).toISOString();
const top=Date.parse('2026-11-18T13:00:00Z');
const solar=Array.from({length:40},(_,index)=>{
  const local=(14+index)%24;
  return {time:iso(top+index*hour),end:iso(top+(index+1)*hour),solar:local>=8&&local<16?2000:0,grid:300,battery:0,price:30};
});
const weatherRows=Array.from({length:30},(_,index)=>({time:iso(top+index*hour),end:iso(top+(index+1)*hour),
  condition:index<2?'sunny':'cloudy',temperature:7-index*.2,cloud_coverage:index<2?10:90,precipitation:index===20?1.2:0,precipitation_probability:20}));
const totals=[{date:'2026-11-18',kwh:3,total_kwh:12,complete:true},{date:'2026-11-19',kwh:16,complete:true},{date:'2026-11-20',kwh:null,complete:false}];

class Element {
  constructor(){this.handlers={};this.hidden=false;this.textContent='';this.markup='';this.attributes={};}
  set innerHTML(value){this.markup=value;}
  get innerHTML(){return this.markup;}
  addEventListener(name,handler){this.handlers[name]=handler;}
  setAttribute(key,value){this.attributes[key]=value;}
  querySelectorAll(){return [];}
}
function fixture({request,code='de',snapshotValues={},clock=()=>now}={}){
  const language=JSON.parse(fs.readFileSync(path.join(__dirname,`../custom_components/eos_energiezentrale/energy/i18n/${code}.json`),'utf8'));
  const ids=Object.fromEntries(['pv-lead','pv-now','pv-source','pv-status','pv-strip','pv-detail','pv-days','pv-effects'].map(id=>[id,new Element()]));
  const snapshot={zone:'Europe/Berlin',live:{solar:1800,weather:{condition:'sunny',temperature:7,unit:'°C'}},forecast:solar,
    pv_today_kwh:9,pv_forecast_totals:totals,pv_now:backend('pvNow',{live:{solar:1800},forecast:solar},{now}),pv_effects:[],...snapshotValues};
  const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const t=(key,values={})=>{assert.equal(typeof language.messages[key],'string',key);return language.messages[key].replace(/\{(\w+)\}/g,(_,name)=>values[name]??`{${name}}`);};
  const response={status:'available',source:'<provider>',fetched_at:iso(now-60000),rows:weatherRows,
    hours:backend('pvHours',solar,{now,weather:weatherRows,zone:'Europe/Berlin'}),
    days:backend('pvDays',totals,{now,weather:weatherRows,measured:9,zone:'Europe/Berlin'})};
  const calls=[];
  const view=forecast.create({document:{getElementById:id=>ids[id]},getSnapshot:()=>snapshot,
    request:request??(async action=>{calls.push(action);return response;}),t,html,
    decimal:(value,digits=1)=>new Intl.NumberFormat(language.locale,{maximumFractionDigits:digits}).format(value),getLocale:()=>language.locale,now:clock});
  return {view,ids,snapshot,calls,response};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('PV page leads with live power, today and tomorrow, and compares PV now with the forecast',async()=>{
  const f=fixture();f.view.open();await flush();
  assert.equal(f.ids['pv-lead'].textContent,'1,8 kW jetzt · heute 9 kWh erzeugt · Rest ≈ 3 kWh · morgen ≈ 16 kWh');
  assert.match(f.ids['pv-now'].markup,/Sonnig/);assert.match(f.ids['pv-now'].markup,/Bewölkung 10 %/);
  assert.match(f.ids['pv-now'].markup,/PV jetzt 1,8 kW · ≈ 90 % der Prognose/);
  assert.equal(f.ids['pv-source'].textContent,'<provider> · Stand 14:29');assert.equal(f.ids['pv-status'].hidden,true);
});
test('hourly strip shows weather above PV, folds the night and explains a tapped hour',async()=>{
  const f=fixture();f.view.open();await flush();
  const strip=f.ids['pv-strip'].markup;
  assert.match(strip,/class="wx-h now"[^>]*data-hour="0"/);assert.match(strip,/<span class="t">Jetzt<\/span>/);
  assert.equal((strip.match(/class="wx-gap"/g)??[]).length,2);assert.match(strip,/Nacht<br>Bewölkt · bis 4°<br><small>16:00–08:00<\/small>/);
  assert.match(strip,/<span class="t">Do 08:00<\/span>/);assert.match(strip,/<span class="t">15:00<\/span>/);assert.match(strip,/☁ 90 %/);
  assert.doesNotMatch(strip,/&lt;provider|<provider/);
  const button={dataset:{hour:'1'}};
  f.ids['pv-strip'].handlers.click({target:{closest:()=>button}});
  assert.match(f.ids['pv-detail'].textContent,/^15:00 · Sonnig, 7° · Bewölkung 10 % · Regenwahrscheinlichkeit 20 % · PV ≈ 2 kWh$/);
});
test('day cards show weather and expected PV without a range',async()=>{
  const f=fixture();f.view.open();await flush();
  const days=f.ids['pv-days'].markup;
  assert.match(days,/<b>Heute<\/b>/);assert.match(days,/≈ 12 kWh/);assert.match(days,/9 kWh bereits erzeugt/);
  assert.match(days,/≈ 16 kWh/);assert.match(days,/Bewölkt · /);assert.match(days,/1,2 mm Regen/);
  assert.match(days,/Prognose unvollständig/);assert.doesNotMatch(days,/Spanne|range/);
});
test('plan effects come from the backend and link to the matching view',async()=>{
  const rows=solar.map((row,index)=>index===12||index===13?{...row,battery:3000,solar:0,price:24}:index===14?{...row,battery_soc:90}:row);
  const effects=backend('pvEffects',{forecast:rows,pv_forecast_totals:[{total_kwh:20,complete:true},{date:'2026-11-19',kwh:6,complete:true}],
    vehicle_name:'ID.4',charge_plan:{state:'active',grid_kwh:25.4,grid_from:iso(top+12*hour),grid_price_ct:24.1,pv_kwh:0}},{now});
  const f=fixture({snapshotValues:{pv_effects:effects}});f.view.open();await flush();
  const list=f.ids['pv-effects'].markup;
  assert.match(list,/Morgen deutlich weniger Sonne<\/b><br><small>Morgen ≈ 6 kWh PV erwartet, heute 20 kWh\./);
  assert.match(list,/href="#battery"><span><b>Speicher lädt aus dem Netz<\/b><br><small>Fr\.? ?|href="#battery"><span><b>Speicher lädt aus dem Netz/);
  assert.match(list,/6 kWh zu Ø 24 ct\/kWh\. Danach 90 %\./);
  assert.match(list,/href="#car"><span><b>ID\.4 lädt aus dem Netz/);
  const empty=fixture();empty.view.open();await flush();
  assert.match(empty.ids['pv-effects'].markup,/nichts Besonderes/);
});
test('missing weather keeps PV visible and a new PV forecast reloads the strip',async()=>{
  let answer={status:'missing_source',rows:[],days:[],hours:backend('pvHours',solar,{now,weather:[],zone:'Europe/Berlin'})};
  const calls=[];const f=fixture({request:async action=>{calls.push(action);return answer;}});
  f.view.open();await flush();
  assert.equal(f.ids['pv-status'].hidden,false);assert.match(f.ids['pv-status'].textContent,/Wetterquelle|Wetter/);
  assert.match(f.ids['pv-strip'].markup,/data-hour="0"/);assert.match(f.ids['pv-strip'].markup,/Kein Wetter/);
  f.view.update();await flush();assert.equal(calls.length,1);
  f.snapshot.forecast=[...solar];f.snapshot.forecast[0]={...solar[0],solar:500};f.view.update();await flush();
  assert.equal(calls.length,2);
});
test('a failed request reports unavailable weather and late answers cannot overwrite a newer load',async()=>{
  let resolveFirst;const answers=[new Promise(resolve=>{resolveFirst=resolve;}),Promise.reject(new Error('offline'))];
  const f=fixture({request:()=>answers.shift()});
  f.view.open();f.view.open();await flush();
  assert.match(f.ids['pv-status'].textContent,/nicht verfügbar|unavailable/i);
  resolveFirst({status:'available',rows:[],hours:[],days:[]});await flush();
  assert.match(f.ids['pv-status'].textContent,/nicht verfügbar|unavailable/i);
});
test('English renders the same structure',async()=>{
  const f=fixture({code:'en'});f.view.open();await flush();
  assert.match(f.ids['pv-lead'].textContent,/1\.8 kW now · 9 kWh generated today/);
  assert.match(f.ids['pv-days'].markup,/<b>Today<\/b>/);assert.match(f.ids['pv-strip'].markup,/Night/);
});
test('poll-driven totals and vehicle rows do not reload; a reload keeps the strip visible',async()=>{
  let time=now,release;const calls=[];
  const f=fixture({clock:()=>time,request:async action=>{calls.push(action);if(calls.length>1)await new Promise(resolve=>{release=resolve;});return f.response;}});
  f.view.open();await flush();const strip=f.ids['pv-strip'].markup;assert.equal(calls.length,1);
  // Every poll changes the rest of today and adds vehicle estimate rows without PV.
  f.snapshot.pv_forecast_totals=[{...totals[0],kwh:2.9},...totals.slice(1)];
  f.snapshot.forecast=[...solar,{time:iso(now),end:iso(now+60000),car_soc:41}];
  f.view.update();await flush();assert.equal(calls.length,1);
  // At the latest after 15 minutes the strip reloads, without blanking it meanwhile.
  time=now+15*60000;f.view.update();await flush();assert.equal(calls.length,2);
  assert.equal(f.ids['pv-strip'].markup,strip);assert.equal(f.ids['pv-status'].hidden,true);
  release();await flush();assert.match(f.ids['pv-strip'].markup,/data-hour="0"/);
});
