const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const backend=require('./backend.cjs');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const messages=JSON.parse(fs.readFileSync(path.join(root,'i18n/de.json'),'utf8')).messages;
const now=Date.parse('2026-11-18T14:00:00Z'),hour=3_600_000,iso=ms=>new Date(ms).toISOString();
const row=(hours,car,soc,{grid=0,price=30,solar=0,length=1}={})=>({time:iso(now+hours*hour),end:iso(now+(hours+length)*hour),
  car,car_soc:soc,grid,price,solar,house_total:500});
const forecast=[row(0,3700,40,{solar:5000}),row(1,0,47.4,{price:36}),row(2,0,47.4,{price:36}),row(3,0,47.4,{price:36}),
  row(4,7400,47.4,{grid:7900,price:24}),row(5,7400,62.2,{grid:7900,price:24}),row(6,3700,77,{grid:4200,price:24,length:.5}),
  row(6.5,0,80.7,{price:25,length:1.5})];
function data(values={}) {
  return {armed:true,live:{car_soc:40,car_connected:true},charge_target_soc:80,charge_departure:iso(now+8*hour),
    charge_limits:{capacity_wh:50000,efficiency:1,maximum_w:11000,max_current_a:16,phases:null},
    vehicle_forecast_source:'eos',settings:{fast:false},errors:{},plan_generated_at:iso(now-2*60000),forecast,...values};
}
class Node {
  constructor(){this.hidden=false;this.innerHTML='';this.textContent='';this.classes=new Set();
    this.classList={toggle:(name,on)=>on?this.classes.add(name):this.classes.delete(name)};}
  scrollIntoView(){this.scrolled=true;}
}
function render(values={}, snapshotValues={}) {
  const plan=backend('chargePlan',data(values),{now,pv_price_ct:8});
  const nodes=new Map(),byId=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id);};
  const decimal=(value,digits=1)=>new Intl.NumberFormat('de-DE',{maximumFractionDigits:digits}).format(value);
  const ctx={byId,decimal,language:{locale:'de-DE'},valid:Number.isFinite,windowNow:()=>now,
    snapshot:{zone:'Europe/Berlin',live:{car:3700,phases:1,car_mode:'CHARGING',soc_source:'vehicle'},charge_plan:plan,...snapshotValues},
    t:(key,vars={})=>(messages[key]??key).replace(/\{(\w+)\}/g,(_,name)=>vars[name]??`{${name}}`),
    html:value=>String(value).replace(/[&<>"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[char]),
    power:value=>`${decimal(value/1000,2)} kW`,percent:value=>Number.isFinite(value)?`${decimal(value)} %`:'—',
    price:value=>Number.isFinite(value)?`${decimal(value)} ct/kWh`:'—',modeLabel:mode=>mode==='CHARGING'?'Lädt':mode,stateLabel:(_,value)=>value,
    clock:value=>new Intl.DateTimeFormat('de-DE',{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit'}).format(new Date(value)),
    requestAnimationFrame:callback=>callback(),matchMedia:()=>({matches:true})};
  ctx.th=(key,vars)=>ctx.html(ctx.t(key,vars));ctx.when=ctx.clock;
  vm.createContext(ctx);
  vm.runInContext('let planScrollPending=false;'+script.slice(script.indexOf('const kwhText='),script.indexOf('function batteryGroupDetails(')),ctx);
  ctx.carView();
  return {plan,goal:nodes.get('car-goal'),panel:nodes.get('car-plan'),ctx};
}
test('car page answers the goal first with the backend plan summary',()=>{
  const {goal}=render();
  assert.match(goal.innerHTML,/Bis 23:00 auf 80 %/);
  assert.match(goal.innerHTML,/Noch 20 kWh\. EOS plant 3,7 kWh aus PV bis 16:00 und 16,7 kWh Netzladen ab 19:00 \(24 ct\/kWh\)\./);
  assert.match(goal.innerHTML,/aria-label="Ladestand 40 %, Ziel 80 %"/);
  assert.match(goal.innerHTML,/3,7 kW · 1-phasig/);assert.match(goal.innerHTML,/class="to-plan"/);
  assert.doesNotMatch(goal.innerHTML,/Reichweite/);
});
test('car goal shows the reported or estimated range',()=>{
  const live={car:0,soc_source:'vehicle'};
  assert.match(render({},{live:{...live,car_range:212,car_range_source:'vehicle'}}).goal.innerHTML,/Reichweite 212 km/);
  assert.match(render({},{live:{...live,car_range:180.4,car_range_source:'estimate'}}).goal.innerHTML,/Reichweite ≈ 180 km/);
});
test('charge plan shows track, list and the cheaper plan against charging now',()=>{
  const {panel}=render();
  assert.match(panel.innerHTML,/EOS-Ladeplan bis 23:00/);assert.match(panel.innerHTML,/Plan von 14:58/);
  assert.deepEqual([...panel.innerHTML.matchAll(/data-charge="\d+"[^>]*--mode|--mode:var\(--(\w+)\)" data-charge/g)].map(match=>match[1]),['solar','edge','grid','car']);
  assert.match(panel.innerHTML,/Netzladen 3-phasig mit 6,7 kW/);
  assert.match(panel.innerHTML,/80 % erreicht<\/b><br><small>1 h 30 min Puffer bis 23:00/);
  assert.match(panel.innerHTML,/<div class="win"><small>EOS-Plan<\/small><strong>4,29&nbsp;€|<div class="win"><small>EOS-Plan<\/small><strong>4,29\s€/);
  assert.match(panel.innerHTML,/Sofort laden<\/small><strong>≈ 5,55/);
  assert.match(panel.innerHTML,/Einspeisevergütung von 8 ct\/kWh/);
  assert.equal(panel.classes.has('overridden'),false);
});
test('fast charging overrides the plan and marks charging now as active',()=>{
  const {panel}=render({settings:{fast:true}});
  assert.match(panel.innerHTML,/<span class="tag">überstimmt<\/span>/);
  assert.match(panel.innerHTML,/Schnellladen ist an/);assert.match(panel.innerHTML,/80 % um ≈ 16:49/);
  assert.match(panel.innerHTML,/<div class="win"><small>Sofort laden \(aktiv\)/);
  assert.equal(panel.classes.has('overridden'),true);
});
test('a wallbox error suspends the plan and links to diagnostics; read-only only displays it',()=>{
  const suspended=render({errors:{wallbox:'TimeoutError'}}).panel.innerHTML;
  assert.match(suspended,/tone-crit" role="alert"/);assert.match(suspended,/ausgesetzt/);assert.match(suspended,/href="#notices"/);
  const readOnly=render({armed:false}).panel;
  assert.match(readOnly.innerHTML,/nur Anzeige/);assert.match(readOnly.innerHTML,/Lesemodus/);
  assert.equal(readOnly.classes.has('overridden'),true);
});
test('without an EOS curve the page says so instead of inventing segments',()=>{
  const {goal,panel}=render({vehicle_forecast_source:'constant'});
  assert.match(goal.innerHTML,/kein EOS-Ladeplan/);assert.doesNotMatch(panel.innerHTML,/data-charge/);
  assert.match(panel.innerHTML,/Die Kurve schreibt nur den Ladestand fort/);
});
