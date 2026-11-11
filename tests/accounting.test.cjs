const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/accounting.js'),'utf8');
function fixture(){
  const context=vm.createContext({Intl,Date,structuredClone,Number,window:{innerWidth:390},
    language:{locale:'de-DE'},snapshot:{zone:'Europe/Berlin'},
    valid:Number.isFinite,decimal:(value)=>String(value),
    t:(key,values={})=>({'billing.average_unit_price':'Ø {price}','unit.price':'ct/kWh'}[key]??key)
      .replace(/\{(\w+)\}/g,(_match,name)=>values[name]??''),price:value=>value+' ct/kWh'});
  vm.runInContext(script,context);
  return context;
}

function amount(kwh,cost,unknown=0){
 return {kwh,cost_eur:cost,cost_unknown_kwh:unknown,seconds:3600,
  sources:Object.fromEntries(['pv','battery','grid','unknown'].map(source=>[source,
   {kwh:source==='grid'?kwh:0,cost_eur:source==='grid'?cost:0,cost_unknown_kwh:source==='grid'?unknown:0}]))};
}
function uiFixture(){
 const ctx=fixture(),elements={};
 ctx.byId=id=>elements[id]??(elements[id]={innerHTML:'',textContent:'',value:''});
 ctx.html=value=>String(value??'');ctx.th=ctx.t;ctx.percent=value=>value+' %';
 return {ctx,elements};
}

test('day overview shows the energy-weighted unit price beside every cost total',()=>{
 const {ctx,elements}=uiFixture();
 ctx.consumerEnabled=key=>key==='heat';
 ctx.snapshot.accounting={date:'2026-02-01',consumers:{house:{total:amount(1,.1)},heat:{total:amount(3,.9)}}};
 vm.runInContext('dayBalance()',ctx);
 const html=elements['day-balance'].innerHTML;
 assert.match(html,/4 kWh.*Ø 25 ct\/kWh/);
 assert.match(html,/0,10[^<]*Ø 10 ct\/kWh/);
 assert.match(html,/0,90[^<]*Ø 30 ct\/kWh/);
});

test('live and reconstructed consumption use their combined cost and energy for the unit price',()=>{
 const {ctx,elements}=uiFixture();
 ctx.consumerEnabled=()=>false;
 ctx.snapshot.accounting={date:'2026-02-01',consumers:{house:{total:amount(1,.2)}}};
 ctx.historical={date:'2026-02-01',historical_consumers:{house:amount(3,1.2)}};
 vm.runInContext('dayAccounting=historical;dayBalance()',ctx);
 assert.match(elements['day-balance'].innerHTML,/4 kWh.*Ø 35 ct\/kWh/);
});

test('unknown, partially priced and zero-consumption amounts do not invent a unit price',()=>{
 const ctx=fixture();
 for(const value of [null,amount(1,0,1),amount(1,.2,.5),amount(0,0)]){
  ctx.amount=value;
  assert.match(vm.runInContext('costWithPrice(amount)',ctx),/Ø — ct\/kWh/);
 }
 for(const value of [amount(1,null),amount(1,NaN),amount(NaN,.2)]){
  ctx.amount=value;
  assert.equal(vm.runInContext('averageCost(amount)',ctx),'—');
 }
 ctx.amount=amount(2,0);
 assert.match(vm.runInContext('costWithPrice(amount)',ctx),/Ø 0 ct\/kWh/);
 ctx.amount=amount(2,-.1);
 assert.match(vm.runInContext('costWithPrice(amount)',ctx),/Ø -5 ct\/kWh/);
});

test('both consumption and cost chart tooltips include overall and per-source unit prices',()=>{
 const {ctx}=uiFixture();
 ctx.entry={total:amount(4,1),bins:[{...amount(4,1),time:'2026-02-01',sources:{
  pv:{kwh:1,cost_eur:.1,cost_unknown_kwh:0},grid:{kwh:3,cost_eur:.9,cost_unknown_kwh:0}}}]};
 ctx.report={date:'2026-02-01',end:'2026-03-01',consumers:{house:ctx.entry}};
 vm.runInContext("billing.data=report;billing.period='month'",ctx);
 for(const cost of [false,true]){
  const chart=vm.runInContext('billingChart(entry,'+cost+')',ctx);
  assert.match(chart,/<title>[^<]*Ø 25 ct\/kWh/);
  assert.match(chart,/billing.pv:[^\n]*Ø 10 ct\/kWh/);
  assert.match(chart,/billing.grid:[^\n]*Ø 30 ct\/kWh/);
 }
});

test('every consumer and reporting period places the unit price directly under the cost KPI',()=>{
 for(const key of ['house','heat','car','car/one'])for(const period of ['day','month','year']){
  const {ctx,elements}=uiFixture();
  ctx.snapshot.vehicles=[{id:'one',name:'Auto One'}];
  ctx.report={date:'2026-02-01',end:'2026-03-01',consumers:{[key]:{total:amount(4,1),bins:[]}}};
  ctx.period=period;ctx.key=key;
  ctx.cards=values=>{ctx.kpis=values;return '';};
  vm.runInContext("billing.data=report;billing.period=period;billing.date=report.date;usageDetail(key,false)",ctx);
  assert.match(ctx.kpis[1][1],/1,00/);
  assert.match(ctx.kpis[1][2],/Ø 25 ct\/kWh/);
  assert.match(elements['usage-table'].innerHTML,/25 ct\/kWh/);
 }
});

test('the short unit-price label is translated in German and English',()=>{
 for(const language of ['de','en']){
  const ctx=fixture();
  const messages=JSON.parse(fs.readFileSync(path.join(__dirname,`../custom_components/eos_energiezentrale/energy/i18n/${language}.json`),'utf8')).messages;
  ctx.t=(key,values={})=>messages[key].replace(/\{(\w+)\}/g,(_match,name)=>values[name]??'');
  const label=vm.runInContext('averageCostLabel({kwh:4,cost_eur:1,cost_unknown_kwh:0})',ctx);
  assert.equal(label,language==='de'?'Ø 25 ct/kWh':'Avg 25 ct/kWh');
 }
});
test('calendar month slots include all days rather than compressing measurement gaps',()=>{
 const ctx=fixture();
 vm.runInContext("billing.period='month';billing.data={date:'2026-02-01',end:'2026-03-01'}",ctx);
 const slots=vm.runInContext('billingSlots()',ctx);
 assert.equal(slots.length,28);
 assert.equal(slots[0].key,'2026-02-01');
 assert.equal(slots[27].key,'2026-02-28');
});
test('year view keeps twelve monthly positions',()=>{
 const ctx=fixture();
 vm.runInContext("billing.period='year';billing.data={date:'2026-01-01',end:'2027-01-01'}",ctx);
 const slots=vm.runInContext('billingSlots()',ctx);
 assert.equal(slots.length,12);
 assert.equal(slots[11].key,'2026-12');
});
test('repeated DST hours remain separate with distinct timezone labels',()=>{
 const ctx=fixture();
 vm.runInContext("billing.period='day';billing.data={date:'2026-10-25',hours:['2026-10-25T00:00:00+00:00','2026-10-25T01:00:00+00:00']}",ctx);
 const slots=vm.runInContext('billingSlots()',ctx);
 assert.equal(slots.length,2);
 assert.notEqual(slots[0].label,slots[1].label);
});
test('unknown energy costs are never presented as free',()=>{
 const ctx=fixture();
 assert.equal(vm.runInContext('costValue({kwh:5,cost_eur:0,cost_unknown_kwh:5})',ctx),'—');
 assert.ok(vm.runInContext('costValue({kwh:5,cost_eur:1,cost_unknown_kwh:2})',ctx).startsWith('≈'));
 assert.ok(!vm.runInContext('costValue({kwh:5,cost_eur:-1,cost_unknown_kwh:0})',ctx).startsWith('≈'));
});


test('cost totals and per-kWh prices cannot be confused for small consumption',()=>{
 const ctx=fixture();
 const amount='{kwh:.03,cost_eur:.009,cost_unknown_kwh:0}';
 assert.match(vm.runInContext('costValue('+amount+')',ctx),/0,009/);
 assert.equal(vm.runInContext('averageCost('+amount+')',ctx),'30 ct/kWh');
 assert.equal(vm.runInContext('averageCost({kwh:1,cost_eur:0,cost_unknown_kwh:1})',ctx),'—');
 assert.match(vm.runInContext('costValue({kwh:5,cost_eur:.01,cost_unknown_kwh:4.9})',ctx),/billing.known_portion/);
});

test('a fully unpriced day never shows zero euros as its total cost',()=>{
 const ctx=fixture();
 const elements={};
 ctx.byId=id=>elements[id]??(elements[id]={innerHTML:''});
 ctx.consumerEnabled=key=>key==='heat';
 ctx.html=value=>value;ctx.th=key=>key;
 ctx.snapshot.accounting={date:'2026-11-10',consumers:{heat:{total:{kwh:3,cost_eur:0,cost_unknown_kwh:3,
   sources:{pv:{kwh:3,cost_eur:0,cost_unknown_kwh:3}}}}}};
 vm.runInContext('dayBalance()',ctx);
 assert.ok(elements['day-balance'].innerHTML.includes('3 kWh · —'));
});


test('the reported heat pump PV share is sub-cent cost, not a zero tariff',()=>{
 const ctx=fixture();
 ctx.amount={kwh:2.27*.011,cost_eur:2.27*.011*.082,cost_unknown_kwh:0};
 const displayed=vm.runInContext('costValue(amount)',ctx);
 assert.match(displayed,/0,002/);
 assert.ok(!displayed.includes('0,00 '));
 assert.ok(Math.abs(Number.parseFloat(vm.runInContext('averageCost(amount)',ctx))-8.2)<1e-10);
 assert.ok(vm.runInContext('money(.000001)',ctx).startsWith('< '));
 assert.ok(vm.runInContext('money(-.000001)',ctx).startsWith('> '));
 assert.match(vm.runInContext('money(0)',ctx),/^0,00/);
});
