const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const css=fs.readFileSync(path.join(root,'web/style.css'),'utf8');
const now=Date.parse('2026-11-19T11:15:00Z'),hour=3_600_000,minute=60_000;

function track(timeline){
  const ctx={snapshot:{zone:'Europe/Berlin',mode_timeline:{battery:timeline}},language:{locale:'de-DE'},
    modes:{SELF_CONSUMPTION:['mode.own','house'],NON_EXPORT:['mode.pv','battery'],FORCED_CHARGE:['mode.grid','car']},
    modeLabel:mode=>mode,t:key=>key,th:key=>key,html:String,when:String,Intl};
  vm.createContext(ctx);
  vm.runInContext(script.slice(script.indexOf('const planWindow'),script.indexOf('function planEventText(')),ctx);
  return ctx.overviewTrack(now);
}
const positions=markup=>[...markup.matchAll(/--start:([\d.e-]+);--duration:([\d.e-]+)/g)].map(match=>[Number(match[1]),Number(match[2])]);

test('plan segments are placed by time, so many short EOS changes cannot push the plan before now',()=>{
  // History until now, then EOS switching every 15 minutes for twelve hours.
  const timeline=[{start:now-3*hour,end:now,mode:'SELF_CONSUMPTION',kind:'history'}];
  for(let index=0;index<48;index++)
    timeline.push({start:now+index*15*minute,end:now+(index+1)*15*minute,mode:index%2?'NON_EXPORT':'FORCED_CHARGE',kind:'plan'});
  const markup=track(timeline),placed=positions(markup),span=15*hour;
  assert.equal(placed.length,49);
  assert.deepEqual(placed[0],[0,3*hour/span]);
  // The first plan segment starts exactly at the now marker.
  assert.equal(placed[1][0],3*hour/span);
  assert.match(markup,/class="plan-now" style="left:20\.00%"/);
  placed.slice(1).forEach(([start,duration],index)=>{
    assert.ok(Math.abs(start-(3*hour+index*15*minute)/span)<1e-12);
    assert.ok(Math.abs(duration-15*minute/span)<1e-12);
  });
});
test('segments are positioned absolutely instead of flowing in a flex row',()=>{
  assert.match(css,/\.mode-segment \{ position:absolute;[^}]*left:calc\(var\(--start\) \* 100%\);[^}]*width:calc\(var\(--duration\) \* 100%\);[^}]*box-sizing:border-box/);
  assert.doesNotMatch(css,/\.plan-track \{[^}]*display:flex/);assert.doesNotMatch(css,/\.mode-track \{[^}]*display:flex/);
});
