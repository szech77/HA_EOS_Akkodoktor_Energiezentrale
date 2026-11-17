const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8'),backend=require('./backend.cjs');

test('backup is a neutral status, while independent errors remain warnings in both languages',()=>{
 for(const language of ['de','en']){
  const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
  const nodes={},classes=new Set();
  const context={snapshot:{},location:{hash:'#overview'},route:'overview',pages:new Set(['overview']),
   billingRoute:()=>false,consumerEnabled:()=>true,overview:()=>{},forecastView:null,
   connectionFailure:false,forecastOpenFailure:false,
   t:(key,values={})=>{assert.equal(typeof messages[key],'string',key);return messages[key].replace(/\{(\w+)\}/g,(_,name)=>values[name]);},
   byId:id=>nodes[id]??(nodes[id]={classList:{toggle:(name,on)=>on?classes.add(name):classes.delete(name)}})};
  vm.createContext(context);
  vm.runInContext(script.slice(script.indexOf('function noticeText('),script.indexOf('let connectionFailure=')),context);
  vm.runInContext(script.slice(script.indexOf('function controlStatus('),script.indexOf('function carIcon(')),context);
  const state={armed:true,control_paused:true,power_supply:{state:'backup',sample:'2026-11-08T12:00:00Z'},
   source_configuration:{unavailable:['grid','house_total']}};
  context.snapshot=backend('view',state,{now:Date.parse(state.power_supply.sample)});
  context.renderView();
  assert.equal(nodes.notice.textContent,messages['notice.backup_power_paused']);
  assert.ok(classes.has('information'));
  assert.equal(context.controlStatus(context.snapshot),messages['control.backup']);
  context.snapshot=backend('view',{...state,errors:{release:'TimeoutError'}},{now:Date.parse(state.power_supply.sample)});
  context.renderView();
  assert.ok(nodes.notice.textContent.includes(messages['notice.check']));
  assert.ok(nodes.notice.textContent.includes(messages['notice.release']));
  assert.ok(!classes.has('information'));
  context.snapshot=backend('view',{armed:true});
  context.renderView();
  assert.equal(nodes.notice.textContent,'');
  assert.equal(context.controlStatus(context.snapshot),messages['control.active']);
 }
});
