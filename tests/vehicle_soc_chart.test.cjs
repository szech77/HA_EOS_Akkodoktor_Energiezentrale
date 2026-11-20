const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const EosChartData=require(path.join(root,'web/chart-data.js'));
const now=Date.parse('2026-11-16T12:00:00Z'),day=86400000;
const row=(offset,soc)=>({time:new Date(now+offset).toISOString(),end:new Date(now+offset+900000).toISOString(),car_soc:soc});
function fixture(count=1){
 const messages=JSON.parse(fs.readFileSync(path.join(root,'i18n/de.json'),'utf8')).messages;
 const nodes=new Map();
 const vehicles=Array.from({length:count},(_,i)=>({id:'ev'+i,name:'Auto '+i,vehicle_forecast_source:i?'constant':'eos',
  live:{car_soc:30+i*10},settings:{target_soc:80},plan:{car:[]},forecast:[row(0,30+i*10),row(900000,50+i*10)]}));
 const original={vehicles,live:{car:0},forecast:[],settings:{},plan:{}};
 const ctx={snapshot:original,history:{local:[],vehicles:Object.fromEntries(vehicles.map((v,i)=>[v.id,[row(-60000,20+i)]]))},
  EosChartData,day,windowNow:()=>now,valid:Number.isFinite,decimal:String,html:String,t:key=>messages[key]??key,th:key=>messages[key]??key,
  byId:id=>{if(!nodes.has(id))nodes.set(id,{classList:{toggle(){}},innerHTML:''});return nodes.get(id);},
  vehicleActive:()=>true,vehicleSettings(){},carView(){},vehicleCards:()=>'',time:String,vehicleForecastNote:()=>'',
  cards:()=>'',displayed:()=>30,percent:String,stateLabel:String,modeLabel:String,solarToday:()=>'',solarForecastCards:()=>[],displayedPower:()=>'',displayAge:()=>'',timeline:()=>'',showProbe(){}};
 vm.createContext(ctx);
 vm.runInContext('function actualPoints(){return history.local;}',ctx);
 vm.runInContext(script.slice(script.indexOf('const chartModels ='),script.indexOf('function hideProbe()')),ctx);
 vm.runInContext(script.slice(script.indexOf('function vehicleSocChart('),script.indexOf("const form = byId('daily')")),ctx);
 return {ctx,nodes,original,models:()=>vm.runInContext('chartModels',ctx)};
}
test('Auto overview renders future SoC for a single configured vehicle',()=>{
 const f=fixture();f.ctx.detail('car');
 assert.match(f.nodes.get('charts').innerHTML,/data-chart="vehicle_soc_ev0"/);
 const model=f.models().get('vehicle_soc_ev0');
 assert.deepEqual(Array.from(model.series[0].future,p=>p.value),[30,50]);
 assert.deepEqual(Array.from(model.series[0].actual,p=>p.value),[20]);
 assert.match(f.nodes.get('charts').innerHTML,/curve forecast[^>]+d="M50\.000,70\.000 L50\.521,50\.000"/);
 assert.equal(f.ctx.snapshot,f.original);
});
test('each car has an independent SoC chart, tooltip model, history and forecast source label',()=>{
 const f=fixture(2);f.ctx.detail('car');
 assert.deepEqual(Array.from(f.models().get('vehicle_soc_ev0').series[0].future,p=>p.value),[30,50]);
 assert.deepEqual(Array.from(f.models().get('vehicle_soc_ev1').series[0].future,p=>p.value),[40,60]);
 assert.deepEqual(Array.from(f.models().get('vehicle_soc_ev1').series[0].actual,p=>p.value),[21]);
 assert.match(f.nodes.get('charts').innerHTML,/Aktueller SoC fortgeschrieben/);
});
test('individual vehicle detail keeps the same future SoC data',()=>{
 const f=fixture();f.ctx.detail('car/ev0');
 assert.deepEqual(Array.from(f.models().get('car_soc').series[0].future,p=>p.value),[30,50]);
 assert.match(f.nodes.get('charts').innerHTML,/SoC-Prognose aus EOS/);
 assert.equal(f.ctx.snapshot,f.original);
});

test('local fallback renders a constant known SoC above zero in the future graph',()=>{
 const f=fixture(),vehicle=f.original.vehicles[0];
 vehicle.live.car_soc=53;vehicle.vehicle_forecast_source='constant';
 vehicle.forecast=[row(0,53),row(900000,53)];
 f.ctx.detail('car');
 assert.deepEqual(Array.from(f.models().get('vehicle_soc_ev0').series[0].future,p=>p.value),[53,53]);
 assert.match(f.nodes.get('charts').innerHTML,/curve forecast[^>]+d="M50\.000,47\.000 L50\.521,47\.000"/);
});

test('the fleet view shows all vehicles without one vehicle\'s goal, switches or goals',()=>{
 const f=fixture(2);f.ctx.detail('car');
 assert.equal(f.nodes.get('car-view').hidden,true);
 assert.equal(f.nodes.get('vehicle-goals').hidden,true);
 assert.equal(f.nodes.get('detail-title').textContent,'Fahrzeuge und Ladepunkte');
 const nav=f.nodes.get('car-nav');
 assert.equal(nav.hidden,false);
 assert.match(nav.innerHTML,/<a href="#car" aria-current="page">Alle Fahrzeuge<\/a>/);
 assert.match(nav.innerHTML,/<a href="#car\/ev0">Auto 0<\/a><a href="#car\/ev1">Auto 1<\/a>/);
});
test('a vehicle page of a fleet keeps the vehicle choice and marks the shown vehicle',()=>{
 const f=fixture(2);f.ctx.detail('car/ev1');
 assert.equal(f.nodes.get('car-view').hidden,false);
 assert.equal(f.nodes.get('vehicle-goals').hidden,false);
 assert.equal(f.nodes.get('detail-title').textContent,'Auto 1');
 const nav=f.nodes.get('car-nav');
 assert.equal(nav.hidden,false);
 assert.match(nav.innerHTML,/<a href="#car">Alle Fahrzeuge<\/a>/);
 assert.match(nav.innerHTML,/<a href="#car\/ev1" aria-current="page">Auto 1<\/a>/);
 assert.equal(f.ctx.snapshot,f.original);
});
test('vehicle ids are one encoded route segment and a single vehicle needs no choice',()=>{
 const f=fixture(2);f.original.vehicles[1].id='a/b';
 f.ctx.detail('car/a%2Fb');
 assert.equal(f.nodes.get('detail-title').textContent,'Auto 1');
 assert.match(f.nodes.get('car-nav').innerHTML,/href="#car\/a%2Fb" aria-current="page"/);
 assert.equal(f.ctx.routeVehicleId('car/%E0%A4%A'),null);
 const single=fixture(1);single.ctx.detail('car/ev0');
 assert.equal(single.nodes.get('car-nav').hidden,true);
});
test('the Auto menu opens the only vehicle\'s page, like the energy flow does',()=>{
 const f=fixture();
 assert.equal(f.ctx.singleVehicleRoute('car',[{id:'a/b'}]),'car/a%2Fb');
 assert.equal(f.ctx.singleVehicleRoute('car',[{id:'a'},{id:'b'}]),null);
 assert.equal(f.ctx.singleVehicleRoute('car',[]),null);
 assert.equal(f.ctx.singleVehicleRoute('car/a',[{id:'a'}]),null);
});
