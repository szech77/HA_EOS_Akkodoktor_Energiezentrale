const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');

class Node {
 constructor(){this.dataset={};this.children=[];this.events={};this.elements={};this.value='';this.checked=false;}
 addEventListener(name,handler){this.events[name]=handler;}
 append(child){child.parent=this;this.children.push(child);}
 remove(){this.parent.children=this.parent.children.filter(child=>child!==this);}
 set innerHTML(markup){
  this.markup=markup;this.children=[];this.inputs=[];
  for(const match of markup.matchAll(/<(input|select)\b([^>]*)>/g)){
   const input=new Node(),attrs=match[2];input.name=attrs.match(/name="([^"]+)"/)?.[1];
   input.value=attrs.match(/value="([^"]*)"/)?.[1]??'';input.checked=/\bchecked\b/.test(attrs);
   if(input.name)this.inputs.push(input);
  }
  this.modes=['once','weekly'].map(mode=>Object.assign(new Node(),{dataset:{goalSchedule:mode}}));
  this.deleteButton=new Node();
 }
 querySelector(selector){
  if(selector==='.delete-goal')return this.deleteButton;
  return this.inputs?.find(input=>selector===`[name=${input.name}]`);
 }
 querySelectorAll(selector){
  if(selector==='[data-goal-schedule]')return this.modes;
  if(selector==='[name=day]:checked')return this.inputs.filter(input=>input.name==='day'&&input.checked);
  if(selector==='.charge-goal')return this.children;
  return [];
 }
}
function fixture(){
 const nodes=Object.fromEntries(['daily','vehicle-daily','vehicle-selector','vehicle-selector-label','charge-plans','vehicle-saved','add-charge-plan','saved'].map(id=>[id,new Node()]));
 for(const name of ['pv','fast','phase_auto','pv_target_soc','fast_target_soc'])nodes['vehicle-daily'].elements[name]=new Node();
 nodes.daily.elements.holiday_state=new Node();
 const messages=JSON.parse(fs.readFileSync(path.join(root,'i18n/de.json'),'utf8')).messages;
 const goal={id:'morning',active:true,schedule:'weekly',target_soc:72,departure_time:'07:45',weekdays:[0,2],holidays:true,next_departure:'2027-01-01T07:45:00+01:00'};
 const vehicle=id=>({id,settings:{pv:true,fast:false,phase_auto:true,pv_target_soc:90,target_soc:85},charge_plan_view:[{...goal,id:id+'_goal'}]});
 const ctx={byId:id=>nodes[id],document:{createElement:()=>new Node()},location:{hash:'#car'},
  snapshot:{vehicles:[vehicle('first'),vehicle('second')]},t:key=>messages[key]??key,th:key=>messages[key]??key,
  html:String,time:String,confirm:()=>false,api:async(op,values)=>{ctx.sent={op,values};},refresh:async()=>{},Date};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf("const form = byId('daily')"),script.indexOf('function batteryGroupDetails(')),ctx);
 vm.runInContext(script.slice(script.indexOf("byId('vehicle-selector').addEventListener"),script.indexOf("document.querySelectorAll('[data-control-area] button')")),ctx);
 nodes['vehicle-selector'].value='second';ctx.vehicleSettings();
 return {ctx,nodes};
}
test('vehicle editor preserves unsaved goals during refresh and saves only selected vehicle settings',async()=>{
 const {ctx,nodes}=fixture(),form=nodes['vehicle-daily'];
 assert.equal(form.dataset.vehicleId,'second');
 const card=nodes['charge-plans'].children[0];card.querySelector('[name=target_soc]').value='77';
 form.elements.fast_target_soc.value='88';
 ctx.vehicleSettings();assert.equal(nodes['charge-plans'].children[0],card);
 await form.events.submit({preventDefault(){}});
 const sent=JSON.parse(JSON.stringify(ctx.sent));
 assert.equal(sent.values.vehicle_id,'second');assert.equal(sent.values.charge_plans[0].target_soc,77);
 assert.equal(sent.values.target_soc,88);
 assert.deepEqual(sent.values.charge_plans[0].weekdays,[0,2]);assert.equal(sent.values.charge_plans[0].holidays,true);
 assert.equal(sent.values.battery_min_soc,undefined);assert.equal(sent.values.holiday_state,undefined);
 nodes['vehicle-selector'].value='first';nodes['vehicle-selector'].events.change();
 assert.equal(nodes['charge-plans'].children[0].dataset.id,'first_goal');
});
test('fast target field does not collide with repeated goal target fields in the form collection',()=>{
 const markup=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
 const form=markup.slice(markup.indexOf('<form id="vehicle-daily">'),markup.indexOf('</form>',markup.indexOf('<form id="vehicle-daily">')));
 assert.match(form,/name="fast_target_soc"/);assert.doesNotMatch(form,/name="target_soc"/);
});
test('add and delete goals require confirmation, while cancelling retains the row',()=>{
 const {ctx,nodes}=fixture();
 nodes['add-charge-plan'].events.click();assert.equal(nodes['charge-plans'].children.length,2);
 const card=nodes['charge-plans'].children[1];
 card.deleteButton.events.click();assert.equal(nodes['charge-plans'].children.length,2);
 ctx.confirm=()=>true;card.deleteButton.events.click();assert.equal(nodes['charge-plans'].children.length,1);
});
test('once and weekly inputs switch validation and submit local date without browser conversion',()=>{
 const {ctx,nodes}=fixture(),card=nodes['charge-plans'].children[0];
 const schedule=card.querySelector('[name=schedule]');
 assert.equal(card.querySelector('[name=departure_local]').required,false);
 schedule.value='once';schedule.events.change();
 assert.equal(card.querySelector('[name=departure_local]').required,true);
 assert.equal(card.querySelector('[name=departure_time]').required,false);
 card.querySelector('[name=departure_local]').value='2027-04-01T07:30';
 assert.equal(ctx.chargePlanValues()[0].departure_local,'2027-04-01T07:30');
 assert.equal(ctx.chargePlanValues()[0].departure,undefined);
});
