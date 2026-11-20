const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'../custom_components/eos_energiezentrale/energy');
const backend=require('./backend.cjs');

function fixture(language){
  const messages=JSON.parse(fs.readFileSync(path.join(root,`i18n/${language}.json`),'utf8')).messages;
  const context={};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(root,'web/status.js'),'utf8'),context);
  const t=(key,values={})=>{assert.equal(typeof messages[key],'string',key);return messages[key].replace(/\{(\w+)\}/g,(_,name)=>String(values[name]));};
  const html=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const ctx={t,html,time:value=>'T'+value,modeLabel:mode=>'M'+mode,text:notice=>t(notice.message,{values:(notice.measurements??[]).join(', ')})};
  return {status:context.EosStatus,messages,ctx};
}

test('backup is a neutral status band, while independent errors remain sorted warnings in both languages',()=>{
  for(const language of ['de','en']){
    const {status,messages,ctx}=fixture(language);
    const state={armed:true,control_paused:true,power_supply:{state:'backup',sample:'2026-11-08T12:00:00Z'},
      source_configuration:{unavailable:['grid','house_total']}};
    let snapshot=backend('view',state,{now:Date.parse(state.power_supply.sample)});
    let band=status.band(snapshot,ctx,{ready:true,car:true});
    assert.equal(band.tone,'info');
    assert.ok(band.html.includes(ctx.html(messages['control.backup'])));
    assert.deepEqual(snapshot.notices.map(notice=>notice.severity),['info']);
    assert.ok(status.noticeCard(snapshot.notices[0],ctx).includes(ctx.html(messages['notice.backup_power_paused'])));
    snapshot=backend('view',{...state,errors:{release:'TimeoutError'}},{now:Date.parse(state.power_supply.sample)});
    const sorted=status.sortNotices(snapshot.notices);
    assert.equal(sorted[0].code,'release');
    assert.equal(sorted[0].severity,'error');
    const card=status.noticeCard(sorted[0],ctx);
    assert.ok(card.includes('tone-crit')&&card.includes('role="alert"'));
    assert.ok(card.includes(ctx.html(messages['notice.release'])));
    assert.ok(card.includes(ctx.html(messages['notice_card.id'].replace('{id}',sorted[0].id))));
    snapshot=backend('view',{armed:true});
    assert.deepEqual(snapshot.notices,[]);
    band=status.band(snapshot,ctx,{ready:true,car:true});
    assert.equal(band.tone,'ok');
    assert.ok(band.html.includes(ctx.html(messages['control.active'])));
  }
});

test('the band shows the backend calculation state and elapsed seconds',()=>{
  for(const language of ['de','en']){
    const {status,messages,ctx}=fixture(language);
    for(const state of ['calculating','updating']){
      const band=status.band({control_status:'active',armed:true,eos_run:{state,elapsed_s:240}},ctx,{ready:true});
      // The calculation state is information in the text, not part of the headline.
      assert.ok(band.html.includes('<h2>'+ctx.html(messages['control.active'])+'</h2>'));
      assert.ok(band.html.includes(ctx.html(messages['eos.run_'+state].replace('{seconds}','240'))));
    }
    const next=status.band({control_status:'active',armed:true,next_mode:{battery:{time:'X',mode:'SELF_CONSUMPTION'}}},ctx,{ready:true});
    assert.ok(next.html.includes('TX')&&next.html.includes('MSELF_CONSUMPTION'));
  }
});

test('control changes need an inline confirmation that matches the devices',()=>{
  const {status,messages,ctx}=fixture('de');
  const off={control_status:'read_only',armed:false};
  let band=status.band(off,ctx,{ready:true,car:false});
  assert.ok(band.html.includes('data-control="take"')&&!band.html.includes('data-control="confirm"'));
  assert.match(status.band(off,ctx,{ready:false}).html,/data-control="take"[^>]*disabled/);
  band=status.band(off,ctx,{ready:true,car:false,confirming:'take'});
  assert.ok(band.html.includes(messages['control.take_battery'])&&!band.html.includes(messages['control.take_devices']));
  assert.match(band.html,/data-control="take"[^>]*disabled/);
  band=status.band({control_status:'active',armed:true},ctx,{ready:true,car:true,confirming:'release'});
  assert.ok(band.html.includes(messages['control.release_wallbox'])&&band.html.includes(messages['control.release_battery']));
  assert.ok(band.html.includes('btn danger'));
  band=status.band({control_status:'active',armed:true},ctx,{ready:true,confirming:'release',busy:true});
  assert.match(band.html,/data-control="confirm"[^>]*disabled/);
  // An unconfirmed release keeps offering the release instead of a take-over.
  // Separate control areas: the confirmation names only controllable or controlled devices.
  const areas=(battery,vehicle)=>({battery:{available:true,enabled:false,release_pending:false,...battery},vehicle:{available:true,enabled:false,release_pending:false,...vehicle}});
  band=status.band({control_status:'read_only',armed:false,control:areas({available:false},{})},ctx,{ready:true,car:true,confirming:'take'});
  assert.ok(band.html.includes(messages['control.take_vehicle'])&&!band.html.includes(messages['control.take_devices']));
  band=status.band({control_status:'read_only',armed:false,control:areas({},{})},ctx,{ready:true,car:false,confirming:'take'});
  assert.ok(band.html.includes(messages['control.take_devices']));
  band=status.band({control_status:'active',armed:true,control:areas({enabled:true},{})},ctx,{ready:true,car:true,confirming:'release'});
  assert.ok(band.html.includes(messages['control.release_battery'])&&!band.html.includes(messages['control.release_wallbox']));
  band=status.band({control_status:'active',armed:true,control:areas({},{enabled:true}),next_mode:{battery:{time:'X',mode:'SELF_CONSUMPTION'}}},ctx,{ready:true,car:true});
  assert.ok(band.html.includes(ctx.html(messages['status_band.active_vehicle']))&&!band.html.includes('TX'));
  band=status.band({control_status:'active',armed:true,control:areas({enabled:true},{enabled:true})},ctx,{ready:true,car:true});
  assert.ok(band.html.includes(ctx.html(messages['status_band.active'])));
  const pending=status.band({control_status:'read_only',armed:false,release_pending:true},ctx,{ready:true});
  assert.equal(pending.tone,'warn');
  assert.ok(pending.html.includes('data-control="release"')&&pending.html.includes(messages['status_band.release_pending']));
});

test('notice cards link to the affected page and keep browser notices local',()=>{
  const {status,messages,ctx}=fixture('en');
  assert.equal(status.noticeLink({code:'wallbox_stop',scope:'system'}),'#car');
  assert.equal(status.noticeLink({code:'goal',scope:'vehicle/2'}),'#car');
  assert.equal(status.noticeLink({code:'battery_read',scope:'system'}),'#battery');
  assert.equal(status.noticeLink({code:'runtime',scope:'system'}),null);
  const compact=status.noticeCard({id:'system/eos',code:'eos',severity:'warning',message:'notice.eos',since:'S'},ctx,{compact:true});
  assert.ok(compact.includes('href="#notices"')&&!compact.includes('TS'));
  const full=status.noticeCard({id:'system/eos',code:'eos',severity:'warning',message:'notice.eos',since:'S'},ctx);
  assert.ok(full.includes('TS')&&full.includes('system/eos'));
  const browser=status.noticeCard({severity:'warning',message:'notice.connection',browser:true},ctx);
  assert.ok(browser.includes(messages['notice_card.browser'])&&!browser.includes('ID '));
  const resolved=status.resolvedRow({id:'system/eos',code:'eos',at:'2026-11-18T14:05:00Z',since:'2026-11-18T14:02:00Z'},{...ctx,text:()=>'EOS back'});
  assert.ok(resolved.includes('EOS back')&&resolved.includes(messages['notice_card.duration'].replace('{minutes}','3')));
});
