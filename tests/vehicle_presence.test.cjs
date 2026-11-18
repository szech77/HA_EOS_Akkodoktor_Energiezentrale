const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const source=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const context={t:key=>key};
vm.runInNewContext(source.slice(source.indexOf('function vehicleActive('),source.indexOf('function carIcon(')),context);

test('absent and unreachable vehicles stay visible but inactive',()=>{
  for(const available of [true,false]){
    const vehicle={live:{car_connected:false,car_available:available,car:7000},display:{car:{value:7000}}};
    assert.equal(context.vehicleActive(vehicle),false);
    assert.equal(context.vehicleStatus(vehicle),available?'vehicle.disconnected':'vehicle.unavailable');
  }
  assert.equal(context.vehicleActive({live:{car_connected:true}}),true);
  assert.equal(context.vehicleActive({live:{}}),true);
});
test('fleet overview is active while at least one vehicle is present',()=>{
  const absent={live:{car_connected:false}},present={live:{car_connected:true}};
  assert.equal(context.vehicleActive({vehicles:[absent,absent]}),false);
  assert.equal(context.vehicleActive({vehicles:[absent,present]}),true);
});
test('presence labels are translated in German and English',()=>{
  for(const language of ['de','en']){
    const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
    for(const key of ['vehicle.disconnected','vehicle.unavailable','plugin.feature.optional_connection',
        'notice.wallbox','notice.wallbox_stop','notice.vehicle_limits',
        'control.syncing_vehicle','control.planning_vehicle'])
      assert.equal(typeof messages[key],'string');
  }
});

test('normal EOS planning has a distinct status and preserves recovery priorities',()=>{
  const status={};
  vm.runInNewContext(fs.readFileSync(path.join(root,'web/status.js'),'utf8'),status);
  const ctx={t:key=>key,html:String,time:String,modeLabel:String};
  const title=snapshot=>status.EosStatus.band(snapshot,ctx,{ready:true}).html.match(/<h2>([^<]*)<\/h2>/)[1];
  for(const name of ['planning_vehicle','syncing_vehicle','cached_eos','waiting','read_only','active','backup','power_supply_waiting'])
    assert.equal(title({control_status:name,armed:name!=='read_only'}),'control.'+name);
  // Technical flags cannot override the backend's decision in the browser.
  assert.equal(title({control_status:'waiting',armed:true,vehicle_planning:null}),'control.waiting');
  assert.equal(title({control_status:'unexpected'}),'control.read_only');
});
