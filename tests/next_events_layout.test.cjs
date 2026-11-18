const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web');
const script=fs.readFileSync(path.join(root,'app.js'),'utf8');
const markup=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'style.css'),'utf8');

function restore(storage){
  const details={open:true,handlers:{},addEventListener(name,handler){this.handlers[name]=handler;}};
  const ctx={byId:id=>{assert.equal(id,'next-details');return details;},localStorage:storage};
  vm.createContext(ctx);
  vm.runInContext(script.slice(script.indexOf('const nextDetailsKey'),script.indexOf('function overview()')),ctx);
  ctx.restoreNextDetails();
  return details;
}

test('the event list of the EOS plan is collapsible and open by default',()=>{
  assert.match(markup,/<details class="next-details" id="next-details" open><summary class="list-title"><span data-i18n="plan\.what_next"><\/span><span class="tag" id="next-count" hidden><\/span><\/summary>\s*<div class="list" id="next-events"><\/div><\/details>/);
});
test('the collapsed state is remembered per viewer and survives blocked storage',()=>{
  const saved=new Map();
  const storage={getItem:key=>saved.has(key)?saved.get(key):null,setItem:(key,value)=>saved.set(key,value)};
  const first=restore(storage);
  assert.equal(first.open,true);
  first.open=false;first.handlers.toggle();
  assert.equal(restore(storage).open,false);
  const blocked={getItem(){throw new Error('denied');},setItem(){throw new Error('denied');}};
  const fallback=restore(blocked);
  assert.equal(fallback.open,true);assert.doesNotThrow(()=>fallback.handlers.toggle());
});
test('the EOS plan sits below the energy flow in full width',()=>{
  assert.match(css,/\.overview-grid \{display:grid;grid-template-columns:minmax\(0,1fr\);/);
  assert.ok(markup.indexOf('class="flow-panel"')<markup.indexOf('id="plan-panel"'));
  // The flow diagram keeps its proportions instead of stretching across the page.
  assert.match(css,/#eos-energy-design \.flow \{max-width:760px;\}/);
});
