const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/accounting.js'),'utf8');
function fixture(){
  const context=vm.createContext({Intl,Date,structuredClone,Number,window:{innerWidth:390},
    language:{locale:'de-DE'},snapshot:{zone:'Europe/Berlin'},
    decimal:(value)=>String(value),t:key=>key,price:value=>value+' ct/kWh'});
  vm.runInContext(script,context);
  return context;
}
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
