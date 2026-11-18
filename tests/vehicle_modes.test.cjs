const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const now=Date.parse('2026-11-11T12:00:00Z');
const backend=require('./backend.cjs');
const at=hours=>new Date(now+hours*3600000).toISOString();
function fixture(data,locale='de'){
 const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${locale}.json`),'utf8')).messages;
 const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const t=(key,values={})=>(messages[key]??key).replace(/\{(\w+)\}/g,(_,name)=>values[name]);
 const snapshot={zone:'Europe/Berlin',vehicle_name:'E-Auto',...data,plan_events:backend('planEvents',data,{now})};
 const ctx={snapshot,language:{locale:locale==='de'?'de-DE':'en-GB',messages},windowNow:()=>now,time:value=>'T'+value,html,t,th:(key,values)=>html(t(key,values)),
  valid:Number.isFinite,decimal:value=>String(value),price:value=>value+' ct'};
 vm.createContext(ctx);
 vm.runInContext(script.slice(script.indexOf('const modes ='),script.indexOf('const pages =')),ctx);
 vm.runInContext(script.slice(script.indexOf('const when ='),script.indexOf('const modes =')),ctx);
 vm.runInContext('const day=86400000;'+script.slice(script.indexOf('function planEventText('),script.indexOf('function overview()')),ctx);
 return ctx;
}
const base={live:{battery_mode:'NON_EXPORT',car_mode:'IDLE'},features:{car:true},
 forecast:[{time:at(0),end:at(6),price:30.4},{time:at(6),end:at(30),price:24.1}]};

test('upcoming battery and car changes read as everyday sentences with time and price in German and English',()=>{
 for(const language of ['de','en']){
  const ctx=fixture({...base,plan:{battery:[{time:at(1),mode:'SELF_CONSUMPTION'},{time:at(2),mode:'SELF_CONSUMPTION'},{time:at(8),mode:'FORCED_CHARGE'}],
   car:[{time:at(9),mode:'FORCED_CHARGE'}]}},language);
  const rows=ctx.nextEvents().match(/<div class="row">[\s\S]*?<\/div>/g);
  assert.equal(rows.length,3);
  assert.ok(rows[0].includes(ctx.th('plan_event.battery_SELF_CONSUMPTION')));
  assert.ok(rows[0].includes('30.4 ct')&&rows[1].includes('24.1 ct'));
  assert.ok(rows[1].includes(ctx.th('plan_event.battery_FORCED_CHARGE')));
  assert.ok(rows[2].includes('E-Auto')&&rows[2].includes(ctx.t('mode.grid')));
 }
});

test('each vehicle keeps its own plan and names are escaped',()=>{
 const ctx=fixture({...base,plan:{battery:[]},vehicles:[
  {id:'first',name:'<img src=x>',live:{car_mode:'IDLE'},plan:{car:[{time:at(3),mode:'FORCED_CHARGE'}]}},
  {id:'second',name:'Auto second',live:{car_mode:'FORCED_CHARGE'},plan:{car:[{time:at(4),mode:'FORCED_CHARGE'},{time:at(5),mode:'IDLE'}]}}]});
 const result=ctx.nextEvents();
 assert.match(result,/&lt;img src=x&gt;/);assert.doesNotMatch(result,/<img/);
 assert.equal((result.match(/Auto second/g)??[]).length,1);
 assert.ok(result.includes(ctx.t('mode.idle')));
});

test('no plan and disabled cars render a calm empty state without car entries',()=>{
 let ctx=fixture({...base,plan:{}});
 assert.ok(ctx.nextEvents().includes(ctx.t('status.no_next_mode')));
 ctx=fixture({...base,features:{car:false},plan:{car:[{time:at(1),mode:'FORCED_CHARGE'}]}});
 assert.ok(ctx.nextEvents().includes(ctx.t('status.no_next_mode')));
 // Unknown battery modes fall back to the generic label instead of a raw key.
 ctx=fixture({...base,plan:{battery:[{time:at(1),mode:'NEW_MODE'}]}});
 assert.ok(ctx.nextEvents().includes(ctx.t('plan_event.battery',{mode:'NEW_MODE'})));
});

test('battery events name what the forecast battery does and keep the EOS mode as detail',()=>{
 for(const language of ['de','en']){
  // Night: EOS plans NON_EXPORT, but without PV the battery only holds its charge level.
  const forecast=[{time:at(0),end:at(1),price:28.1,battery:2600,solar:0},{time:at(1),end:at(3),price:28.4,battery:0,solar:0}];
  const ctx=fixture({...base,live:{battery_mode:'FORCED_CHARGE'},forecast,plan:{battery:[{time:at(1),mode:'NON_EXPORT'}]}},language);
  const result=ctx.nextEvents();
  assert.ok(result.includes(ctx.th('plan_event.effect_hold')));
  assert.ok(!result.includes(ctx.th('plan_event.battery_NON_EXPORT')));
  assert.ok(result.includes(ctx.th('plan_event.eos_mode',{mode:ctx.t('mode.pv')}))&&result.includes('28.4 ct'));
 }
});
