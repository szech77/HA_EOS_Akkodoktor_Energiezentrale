const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web');
const script=fs.readFileSync(path.join(root,'app.js'),'utf8');
const context={valid:Number.isFinite};
vm.runInNewContext(script.slice(script.indexOf('function socBarCount('),script.indexOf('function vehicleCards(')),context);

test('car SoC fills five vertical bars in the same 20 percent steps as the battery',()=>{
 for(const [soc,expected] of [[0,0],[1,1],[20,1],[21,2],[40,2],[41,3],[60,3],[61,4],[80,4],[81,5],[100,5]]){
  const icon=context.carIcon(soc);
  assert.equal((icon.match(/class="car-soc-bar/g)||[]).length,5);
  assert.equal((icon.match(/class="car-soc-bar filled"/g)||[]).length,expected);
  assert.doesNotMatch(icon,/<g class="car-soc" hidden/);
 }
});
test('unknown and invalid SoC are distinct from a known empty battery',()=>{
 for(const soc of [null,undefined,NaN,Infinity,-1,101,'50']){
  assert.equal(context.socBarCount(soc),null);
  assert.match(context.carIcon(soc),/<g class="car-soc" hidden/);
  assert.doesNotMatch(context.carIcon(soc),/class="car-soc-bar filled"/);
 }
 assert.doesNotMatch(context.carIcon(0),/<g class="car-soc" hidden/);
});
test('the overview contains the same five bars as the vehicle cards',()=>{
 const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
 const node=html.match(/<a class="node car"[\s\S]*?<\/a>/)[0];
 assert.equal((node.match(/class="car-soc-bar"/g)||[]).length,5);
 assert.match(node,/<g class="car-soc" hidden/);
});
