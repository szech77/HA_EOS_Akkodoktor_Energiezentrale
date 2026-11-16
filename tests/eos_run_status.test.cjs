const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
test('the header shows backend calculation state and elapsed seconds in both languages',()=>{
 for(const language of ['de','en']){
  const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
  const context={t:(key,args={})=>(messages[key]??key).replace(/\{(\w+)\}/g,(_,name)=>args[name])};
  vm.runInNewContext(script.slice(script.indexOf('function controlStatus('),script.indexOf('function carIcon(')),context);
  const normal=context.controlStatus({control_status:'active'});
  assert.equal(normal,messages['control.active']);
  for(const state of ['calculating','updating']){
   const label=context.controlStatus({control_status:'active',eos_run:{state,elapsed_s:240}});
   assert.ok(label.startsWith(normal));assert.ok(label.includes('240'));
   assert.ok(label.includes(messages['eos.run_'+state].split(' (')[0]));
  }
 }
});
