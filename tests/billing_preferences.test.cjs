const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/accounting.js'),'utf8');
const key='eos-energiezentrale.billing-period';
function storage(value){
  const values=new Map(value===undefined?[]:[[key,value]]);
  return {values,getItem:name=>values.get(name)??null,setItem:(name,value)=>values.set(name,value)};
}
function browser(localStorage){
  const elements={},requests=[];
  function element(id){
    return elements[id]??= {listeners:{},addEventListener(name,handler){this.listeners[name]=handler;}};
  }
  element('cost-settings').elements={pv_price_source:element('pv-price-source')};
  const context=vm.createContext({window:{localStorage,addEventListener(){}},byId:element,
    route:'house',snapshot:{},localDay:()=> '2026-11-15',windowNow:()=>new Date('2026-11-15T12:00:00Z'),
    api:async(action,values)=>{requests.push({action,...values});return {};}});
  vm.runInContext(script,context);
  vm.runInContext('initializeBilling()',context);
  return {context,elements,requests,
    period:()=>vm.runInContext('billing.period',context),
    select:value=>elements.usage.listeners.click({target:{closest:selector=>selector==='[data-billing-period]'?{dataset:{billingPeriod:value}}:null}}),
    bin:date=>elements.usage.listeners.click({target:{closest:selector=>selector==='[data-billing-bin]'?{dataset:{billingBin:date}}:null}})};
}
const settled=()=>new Promise(resolve=>setImmediate(resolve));

test('the last selected report period survives reopening and drives the first backend request',async()=>{
  const saved=storage();
  assert.equal(browser(saved).period(),'month');
  for(const period of ['day','month','year']){
    const first=browser(saved);
    first.select(period);await settled();
    assert.equal(first.requests[0].period,period);
    const reopened=browser(saved);
    assert.equal(reopened.period(),period);
    await vm.runInContext('fetchBilling()',reopened.context);
    assert.equal(reopened.requests[0].period,period);
    assert.deepEqual([...saved.values],[[key,period]]);
  }
});

test('chart drill-down also remembers the displayed period without storing the date',async()=>{
  const saved=storage('year'),view=browser(saved);
  view.bin('2026-10-01');await settled();
  assert.equal(view.requests[0].period,'month');
  assert.equal(browser(saved).period(),'month');
  view.bin('2026-10-12');await settled();
  assert.equal(view.requests[1].period,'day');
  const reopened=browser(saved);
  await vm.runInContext('fetchBilling()',reopened.context);
  assert.deepEqual(reopened.requests,[{action:'accounting',period:'day',date:'2026-11-15'}]);
  assert.deepEqual([...saved.values],[[key,'day']]);
});

test('invalid saved or selected values cannot become report requests',async()=>{
  for(const value of ['invalid','',null,'{"period":"day"}']){
    const view=browser(storage(value));
    assert.equal(view.period(),'month');
    view.select('invalid');await settled();
    assert.equal(view.period(),'month');assert.equal(view.requests.length,0);
  }
});

test('blocked reads and writes leave the report usable without backend error reports',async()=>{
  for(const blocked of [undefined,{getItem(){throw new Error('blocked');},setItem(){throw new Error('full');}}]){
    const view=browser(blocked);
    assert.equal(view.period(),'month');
    view.select('day');await settled();
    assert.equal(view.period(),'day');
    assert.deepEqual(view.requests,[{action:'accounting',period:'day',date:'2026-11-15'}]);
  }
  const window={addEventListener(){},get localStorage(){throw new Error('SecurityError');}};
  const context=vm.createContext({window});
  assert.doesNotThrow(()=>vm.runInContext(script,context));
  assert.equal(vm.runInContext("selectBillingPeriod('day');billing.period",context),'day');
});
