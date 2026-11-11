const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const now=Date.parse('2026-11-11T12:00:00Z');
function fixture(vehicles,locale='de'){
 const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${locale}.json`),'utf8')).messages;
 const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const ctx={snapshot:{vehicles,live:{battery_mode:'NON_EXPORT',car_mode:'IDLE'},plan:{},features:{car:true}},
  windowNow:()=>now,time:value=>value,html,t:key=>messages[key]??key,th:key=>html(messages[key]??key)};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf('const modes ='),script.indexOf('const day =')),ctx);
 vm.runInContext(script.slice(script.indexOf('function nextPlan('),script.indexOf('const localDay =')),ctx);
 vm.runInContext(script.slice(script.indexOf('const consumerEnabled ='),script.indexOf('function vehicleActive(')),ctx);
 vm.runInContext(script.slice(script.indexOf('function modeCards('),script.indexOf('function overview(')),ctx);
 return ctx;
}
const vehicle=(id,mode,plan=[])=>({id,name:'Auto '+id,live:{car_mode:mode},plan:{car:plan}});

test('one vehicle keeps its own mode tile below the overview in German and English',()=>{
 for(const language of ['de','en']){
  const ctx=fixture([vehicle('id4','SELF_CONSUMPTION')],language),result=ctx.modeCards();
  assert.equal((result.match(/<div>/g)??[]).length,2);
  assert.match(result,/#car\/id4/);assert.match(result,/Auto id4/);
  assert.ok(result.includes(ctx.t('mode.own')));assert.ok(result.includes(ctx.t('status.no_next_mode')));
 }
});

test('each car uses its own current mode and future plan without borrowing the primary car plan',()=>{
 const first=vehicle('first','IDLE',[{time:'2026-11-11T11:00:00Z',mode:'FORCED_CHARGE'},
  {time:'2026-11-11T13:00:00Z',mode:'IDLE'},{time:'2026-11-11T14:00:00Z',mode:'FORCED_CHARGE'}]);
 const second=vehicle('second','SELF_CONSUMPTION',[{time:'2026-11-11T15:00:00Z',mode:'NON_EXPORT'}]);
 const ctx=fixture([first,second]);ctx.snapshot.plan.car=[{time:'2026-11-11T16:00:00Z',mode:'IDLE'}];
 const tiles=ctx.modeCards().match(/<div>[\s\S]*?<\/div>/g);
 assert.equal(tiles.length,3);
 assert.match(tiles[1],/Auto first/);assert.match(tiles[1],/14:00/);assert.doesNotMatch(tiles[1],/13:00|15:00|16:00/);
 assert.match(tiles[2],/Auto second/);assert.match(tiles[2],/15:00/);assert.doesNotMatch(tiles[2],/14:00|16:00/);
 assert.ok(tiles[1].includes('<b>'+ctx.t('mode.idle')+'</b>'));
 assert.ok(tiles[2].includes('<b>'+ctx.t('mode.own')+'</b>'));
});

test('legacy configuration, disabled cars and absent plans render without losing the battery tile',()=>{
 const ctx=fixture([]);assert.match(ctx.modeCards(),/href="#car"/);
 ctx.snapshot.features.car=false;
 assert.equal((ctx.modeCards().match(/<div>/g)??[]).length,1);assert.doesNotMatch(ctx.modeCards(),/#car/);
 ctx.snapshot.features.car=true;ctx.snapshot.vehicles=[{id:'missing',name:'<img src=x>',live:{car_connected:false}}];
 const result=ctx.modeCards();assert.match(result,/&lt;img src=x&gt;/);assert.doesNotMatch(result,/<img/);
 assert.match(result,/<b>—<\/b>/);assert.ok(result.includes(ctx.t('status.no_next_mode')));
});
