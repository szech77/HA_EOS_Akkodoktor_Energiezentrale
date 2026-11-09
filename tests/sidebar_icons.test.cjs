const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../custom_components/eos_energiezentrale/energy/web/icons.js'),'utf8');

test('sidebar logo resolves before opening a panel, without changing other icon providers',async()=>{
 const other={getIcon:async()=>({path:'M0 0'})},registry={other},window={customIcons:registry};
 vm.runInNewContext(source,{window});
 assert.equal(window.customIcons,registry);
 assert.equal(window.customIcons.other,other);
 const provider=window.customIcons['eos-energy'];
 const icon=await provider.getIcon('logo');
 assert.ok(icon.path.length>0);
 assert.equal(icon.viewBox,'0 0 128 128');
 assert.ok(!icon.path.includes('NaN'));
 assert.equal((await provider.getIcon('missing')).path,'');
 assert.ok((await provider.getIconList()).some(item=>item.name==='logo'));
 vm.runInNewContext(source,{window});
 assert.equal((await window.customIcons['eos-energy'].getIcon('logo')).path,icon.path);
 assert.equal(window.customIcons.other,other);
});

test('logo registration also works before Home Assistant creates an icon registry',async()=>{
 const window={};
 vm.runInNewContext(source,{window});
 assert.ok((await window.customIcons['eos-energy'].getIcon('logo')).path);
});
