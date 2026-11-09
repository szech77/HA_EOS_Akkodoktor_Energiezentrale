const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/accounting.js'),'utf8');
function fixture(){
  const context=vm.createContext({Intl,Date,structuredClone,Number,window:{innerWidth:390},
    language:{locale:'de-DE'},snapshot:{zone:'Europe/Berlin'},
    decimal:(value)=>String(value),t:key=>key});
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
