/* Status band and notice cards. The backend decides state, severity and ids; this only presents them. */
(function(root){
  'use strict';
  const ICONS={
    ok:'<path d="m5 12 4 4 10-10"/>',
    wait:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pause:'<path d="M9 6v12M15 6v12"/>',
    off:'<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>'
  };
  // Tone and icon per backend control_status; unknown states fall back to the neutral read-only look.
  const BAND={active:['ok','ok'],waiting:['info','wait'],cached_eos:['warn','wait'],syncing_vehicle:['info','wait'],
    planning_vehicle:['info','wait'],backup:['info','pause'],power_supply_waiting:['warn','pause'],read_only:['off','off']};
  const SEVERITY={error:0,warning:1,info:2};
  const TONE={error:'crit',warning:'warn',info:'info'};

  function sortNotices(list){
    return [...(list??[])].sort((a,b)=>(SEVERITY[a.severity]??1)-(SEVERITY[b.severity]??1));
  }
  function bandState(snapshot){
    const state=Object.hasOwn(BAND,snapshot.control_status)?snapshot.control_status:'read_only';
    const releasing=!snapshot.armed&&snapshot.release_pending===true;
    return {state,releasing,tone:releasing?'warn':BAND[state][0],icon:releasing?'wait':BAND[state][1],
      action:snapshot.armed||releasing?'release':'take'};
  }
  function band(snapshot,ctx,view={}){
    const {t,html,time,modeLabel}=ctx,info=bandState(snapshot);
    const run=snapshot.eos_run;
    let title=t('control.'+info.state);
    if(['calculating','updating'].includes(run?.state))title+=' · '+t('eos.run_'+run.state,{seconds:run.elapsed_s??0});
    let text=t(info.releasing?'status_band.release_pending':'status_band.'+info.state);
    const next=snapshot.next_mode?.battery;
    if(info.state==='active'&&!info.releasing&&next?.time)text+=' '+t('status_band.next_change',{time:time(next.time),mode:modeLabel(next.mode)});
    const primary=info.action==='take';
    let content=`<span class="status-dot" aria-hidden="true"><svg viewBox="0 0 24 24">${ICONS[info.icon]}</svg></span>
      <div class="status-text"><h2>${html(title)}</h2><p>${html(text)}</p>${view.result?`<p class="status-result" role="status">${html(view.result)}</p>`:''}</div>
      <div class="status-actions"><button type="button" class="btn${primary?' primary':''}" data-control="${info.action}"${view.ready&&!view.busy&&!view.confirming?'':' disabled'}><span class="label-long">${html(t('control.'+info.action))}</span><span class="label-short">${html(t('status_band.'+info.action+'_short'))}</span></button></div>`;
    if(view.confirming){
      const items=view.confirming==='release'
        ?[...(view.car?['control.release_wallbox']:[]),'control.release_battery','control.release_persist']
        :[view.car?'control.take_devices':'control.take_battery','control.take_start','control.take_persist'];
      content+=`<div class="status-confirm"><b>${html(t('control.'+view.confirming+'_title'))}</b><ul>${items.map(key=>`<li>${html(t(key))}</li>`).join('')}</ul>
        <div class="status-actions"><button type="button" class="btn ${view.confirming==='release'?'danger':'primary'}" data-control="confirm"${view.busy?' disabled':''}>${html(t('control.'+view.confirming+'_confirm'))}</button><button type="button" class="btn ghost" data-control="cancel"${view.busy?' disabled':''}>${html(t('control.cancel'))}</button></div></div>`;
    }
    return {tone:info.tone,html:content};
  }
  function noticeLink(notice){
    if(notice.scope?.startsWith('vehicle/')||['goal','vehicle_limits','wallbox','wallbox_stop','wallbox_read'].includes(notice.code))return '#car';
    if(['battery_read','battery_limits'].includes(notice.code))return '#battery';
    if(notice.code==='eos'||notice.code==='eos_cached')return '#settings';
    return null;
  }
  function noticeCard(notice,ctx,{compact=false}={}){
    const {t,html,time,text}=ctx,tone=TONE[notice.severity]??'warn';
    const meta=[notice.id?t('notice_card.id',{id:notice.id}):'',notice.since?t('notice_card.since',{time:time(notice.since)}):'',
      notice.browser?t('notice_card.browser'):''].filter(Boolean).join(' · ');
    const link=compact?'#notices':noticeLink(notice);
    return `<div class="notice-card tone-${tone}" role="${tone==='crit'?'alert':'status'}"><span class="sev">${html(t('notice_card.'+(notice.severity??'warning')))}</span>
      <div><b>${html(text(notice))}</b>${compact||!meta?'':`<small>${html(meta)}</small>`}</div>
      ${link?`<a href="${link}">${html(t(compact?'notice_card.all':'notice_card.open'))}</a>`:'<span></span>'}</div>`;
  }
  function resolvedRow(item,ctx){
    const {t,html,time,text}=ctx;
    const duration=item.since&&item.at?Math.max(1,Math.round((Date.parse(item.at)-Date.parse(item.since))/60000)):null;
    return `<div class="row"><span><b>${html(text({...item,message:'notice.'+item.code}))}</b><br><small>${html([t('notice_card.resolved_at',{time:time(item.at)}),
      duration?t('notice_card.duration',{minutes:duration}):''].filter(Boolean).join(' · '))}</small></span><span class="tag">${html(item.id??item.code)}</span></div>`;
  }
  root.EosStatus={sortNotices,bandState,band,noticeCard,resolvedRow,noticeLink};
})(globalThis);
