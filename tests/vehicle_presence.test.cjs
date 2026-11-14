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
  for(const status of ['planning_vehicle','syncing_vehicle','cached_eos','waiting','read_only','active'])
    assert.equal(context.controlStatus({control_status:status}),'control.'+status);
  // Technical flags cannot override the backend's decision in the browser.
  assert.equal(context.controlStatus({control_status:'waiting',armed:true,vehicle_planning:null}),'control.waiting');
});
