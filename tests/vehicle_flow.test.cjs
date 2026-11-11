const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');

// Small DOM surface used by the renderer; all measurements and layout run unmodified.
class Element {
 constructor(){
  this.children=[];this.dataset={};this.attributes={};this.hidden=false;this.title='';
  this.classes=new Set();this.classList={toggle:(key,on)=>on?this.classes.add(key):this.classes.delete(key),contains:key=>this.classes.has(key)};
  this.style={setProperty:(key,value)=>this.style[key]=value};this.selectors={};
 }
 setAttribute(key,value){this.attributes[key]=String(value);}
 getAttribute(key){return this.attributes[key]??null;}
 toggleAttribute(key,on){if(on)this.setAttribute(key,'');else delete this.attributes[key];}
 append(node){this.children.push(node);}
 prepend(node){this.children.unshift(node);this.selectors['.power-ring']=node;}
 replaceChildren(){this.children=[];}
 querySelector(key){return this.selectors[key]??null;}
 querySelectorAll(key){return this.selectors[key]??[];}
 set innerHTML(value){
  this.markup=value;
  if(value.includes('class="orb"')){
   for(const key of ['.orb','span:nth-child(2)','strong','.car-soc'])this.selectors[key]=new Element();
   this.selectors['.car-soc-bar']=Array.from({length:5},()=>new Element());
  }
  if(value.includes('class="ring-value"'))this.selectors['.ring-value']=new Element();
 }
}
function fixture(vehicles,language='de'){
 const ids=Object.fromEntries(['energy-flow','flow-wires','vehicle-nodes','vehicle-flows'].map(id=>[id,new Element()]));
 const selectors={};
 for(const key of ['solar','grid','battery','house','car','heat']){
  const node=new Element(),flow=new Element();node.innerHTML='<span class="orb"></span>';
  node.selectors['.battery-bar']=Array.from({length:5},()=>new Element());
  flow.setAttribute('d',`M18 50 H43`);
  selectors[`[data-node="${key}"]`]=node;selectors[`[data-flow="${key}"]`]=flow;
 }
 const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
 const ctx={snapshot:{vehicles,live:{solar:1000,grid:2000,battery:0,battery_soc:60,house:1000,heat:0,car:9000},
   settings:{battery_min_soc:20},features:{car:true,heat:true},power_reference:{car:22000}},
  document:{createElement:()=>new Element(),createElementNS:()=>new Element(),querySelector:key=>selectors[key]},
  byId:id=>ids[id],valid:Number.isFinite,t:(key,values={})=>(messages[key]??key).replace(/\{(\w+)\}/g,(_,name)=>values[name]),
  power:value=>Number.isFinite(value)?value/1000+' kW':'—',percent:value=>value+' %',decimal:String,
  EosChartData:require('../custom_components/eos_energiezentrale/energy/web/chart-data.js')};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf('const consumerEnabled ='),script.indexOf('function vehicleCards(')),ctx);
 vm.runInContext(script.slice(script.indexOf('function layoutFlow('),script.indexOf('function overview(')),ctx);
 const rings=[],updateRing=ctx.updatePowerRing;
 ctx.updatePowerRing=(node,key,value,source)=>{rings.push({node,key,value,source});updateRing(node,key,value,source);};
 ctx.renderFlow();
 return {ctx,ids,selectors,rings,nodes:()=>ids['vehicle-nodes'].children,flows:()=>ids['vehicle-flows'].children};
}
const car=(id,soc,watts,extra={})=>({id,name:'Auto '+id,live:{car_soc:soc,car:watts,car_connected:true},power_reference:{car:watts*2},...extra});

test('one configured vehicle appears inside the flow with its own SoC and detail link',()=>{
 const f=fixture([car('first',20,1380)]),node=f.nodes()[0];
 assert.equal(node.href,'#car/first');
 assert.equal(node.querySelector('span:nth-child(2)').textContent,'Auto first · 20 %');
 assert.equal(node.querySelector('strong').textContent,'1.38 kW');
 assert.equal(node.querySelectorAll('.car-soc-bar').filter(bar=>bar.classes.has('filled')).length,1);
 assert.equal(f.selectors['[data-node="car"]'].hidden,true);
 assert.equal(f.selectors['[data-flow="car"]'].style.display,'none');
});

test('two cars have independent measurements, SoCs, wires and power references',()=>{
 const vehicles=[car('first',20,1380),car('second',80,11040)],f=fixture(vehicles);
 assert.equal(f.nodes().length,2);assert.equal(f.flows().length,2);
 for(const [index,vehicle] of vehicles.entries()){
  const node=f.nodes()[index],flow=f.flows()[index];
  assert.equal(node.href,'#car/'+vehicle.id);
  assert.equal(node.querySelector('strong').textContent,vehicle.live.car/1000+' kW');
  assert.equal(node.querySelectorAll('.car-soc-bar').filter(bar=>bar.classes.has('filled')).length,Math.ceil(vehicle.live.car_soc/20));
  assert.match(f.ids['flow-wires'].getAttribute('d'),new RegExp(flow.getAttribute('d')));
  assert.equal(f.rings.find(item=>item.node===node).source,vehicle);
  assert.equal(node.querySelector('.orb').querySelector('.power-ring').dataset.fraction,'0.5');
 }
 assert.notEqual(f.flows()[0].getAttribute('d'),f.flows()[1].getAttribute('d'));
 assert.notEqual(f.nodes()[0].style['--y'],f.nodes()[1].style['--y']);
});

test('offline and disconnected cars are greyed independently and never animate retained power',()=>{
 for(const language of ['de','en']){
  const f=fixture([car('active',40,7000),car('offline',70,7000,{live:{car:7000,car_soc:70,car_connected:false,car_available:false}}),
   car('unplugged',10,7000,{live:{car:7000,car_connected:false,car_available:true}})],language);
  assert.equal(f.nodes()[0].classes.has('vehicle-inactive'),false);
  for(const index of [1,2]){
   assert.equal(f.nodes()[index].classes.has('vehicle-inactive'),true);
   assert.equal(f.flows()[index].classes.has('inactive'),true);
   assert.doesNotMatch(f.nodes()[index].querySelector('strong').textContent,/kW/);
   assert.equal(f.nodes()[index].querySelector('strong').hidden,true);
   assert.equal(f.nodes()[index].querySelector('strong').textContent,'');
   assert.equal(f.rings.find(item=>item.node===f.nodes()[index]).value,null);
  }
  assert.notEqual(f.nodes()[1].title,f.nodes()[2].title);
  assert.ok(f.nodes()[1].getAttribute('aria-label').includes(f.ctx.t('vehicle.unavailable')));
 }
});

test('unknown SoC and missing power are not borrowed from another vehicle or the fleet total',()=>{
 const f=fixture([car('known',100,7000),car('missing',null,null)]),node=f.nodes()[1];
 assert.equal(node.querySelector('strong').textContent,'—');
 assert.equal(node.querySelector('span:nth-child(2)').textContent,'Auto missing');
 assert.equal(node.querySelector('.car-soc').getAttribute('hidden'),'');
 assert.equal(f.flows()[1].classes.has('inactive'),true);
});

test('retained values and sample age belong to the individual vehicle',()=>{
 const f=fixture([car('retained',null,null,{display:{car_soc:{value:0},car:{value:1400,estimated:true,age_s:120}}})]),node=f.nodes()[0];
 assert.equal(node.querySelector('strong').textContent,'≈ 1.4 kW');
 assert.equal(node.querySelector('span:nth-child(2)').textContent,'Auto retained · 0 %');
 assert.match(node.title,/2/);
 assert.equal(node.querySelectorAll('.car-soc-bar').filter(bar=>bar.classes.has('filled')).length,0);
});

test('eight vehicles fit separate rows, polling retains nodes, removal clears old wires',()=>{
 const f=fixture(Array.from({length:8},(_,index)=>car('ev'+index,index*10,0)));
 assert.equal(new Set(f.nodes().map(node=>node.style['--y'])).size,8);
 assert.equal(parseInt(f.ids['energy-flow'].style.height),10*144);
 const first=f.nodes()[0];f.ctx.renderFlow();assert.equal(f.nodes()[0],first);
 f.ctx.snapshot.vehicles=[f.ctx.snapshot.vehicles[7]];f.ctx.renderFlow();
 assert.equal(f.nodes().length,1);assert.equal(f.flows().length,1);
 assert.equal(f.nodes()[0].href,'#car/ev7');
 f.ctx.snapshot.features.car=false;f.ctx.snapshot.features.heat=false;f.ctx.renderFlow();
 assert.equal(f.nodes().length,0);assert.equal(f.flows().length,0);
 assert.equal(f.selectors['[data-node="heat"]'].hidden,true);
});

test('legacy single-car configuration retains the original diagram node and SoC',()=>{
 const f=fixture([]);f.ctx.snapshot.live.car_soc=60;f.ctx.renderFlow();
 assert.equal(f.nodes().length,0);
 const node=f.selectors['[data-node="car"]'];assert.equal(node.hidden,false);
 assert.match(node.querySelector('span:nth-child(2)').textContent,/60 %/);
});

test('vehicle names remain text, and connected status restores the power after unplugging',()=>{
 const vehicle=car('ev',30,1400);vehicle.name='<img src=x onerror=alert(1)>';
 const f=fixture([vehicle]),node=f.nodes()[0];
 assert.equal(node.querySelector('span:nth-child(2)').textContent,vehicle.name+' · 30 %');
 assert.doesNotMatch(node.markup,/<img/);
 vehicle.live.car_connected=false;f.ctx.renderFlow();assert.equal(node.querySelector('strong').hidden,true);
 vehicle.live.car_connected=true;f.ctx.renderFlow();
 assert.equal(node.querySelector('strong').hidden,false);
 assert.equal(node.querySelector('strong').textContent,'1.4 kW');
 assert.equal(node.classes.has('vehicle-inactive'),false);
});
