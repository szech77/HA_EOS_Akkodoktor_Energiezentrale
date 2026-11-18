/* PV & weather view. The backend prepares hours, days and plan effects; this module only presents them. */
(function(root){
  'use strict';
  const valid=Number.isFinite;
  const STATUSES=['available','missing_source','unsupported','unavailable','empty'];
  function weatherIcon(condition){
    const sun='<circle cx="16" cy="13" r="5"/><path d="M16 3v2m0 16v2M6 13H4m24 0h-2M8 5l2 2m12 12 2 2M24 5l-2 2M10 19l-2 2"/>';
    const cloud='<path d="M8 23h16a6 6 0 0 0 0-12 8 8 0 0 0-15-1 6.5 6.5 0 0 0-1 13Z"/>';
    let shape=condition==='sunny'?sun:condition==='clear-night'?'<path d="M24 23A12 12 0 0 1 11 3a12 12 0 1 0 13 20Z"/>':cloud;
    if(condition==='partlycloudy')shape='<circle cx="9" cy="8" r="5"/>'+cloud;
    if(['rainy','pouring','lightning-rainy','snowy-rainy'].includes(condition))shape+='<path d="m9 26-1 3m8-3-1 3m8-3-1 3"/>';
    if(['lightning','lightning-rainy'].includes(condition))shape+='<path d="m17 17-4 7h5l-3 6"/>';
    if(['snowy','snowy-rainy','hail'].includes(condition))shape+='<path d="M8 27h3m-1.5-1.5v3M22 27h3m-1.5-1.5v3"/>';
    if(condition==='fog')shape+='<path d="M4 26h24M7 30h18"/>';
    if(['windy','windy-variant'].includes(condition))shape='<path d="M3 11h20a4 4 0 1 0-4-4M3 17h24M3 23h15a4 4 0 1 1-4 4"/>';
    if(!condition||['unknown','exceptional'].includes(condition))shape='<circle cx="16" cy="16" r="12"/><path d="M16 8v10m0 5v1"/>';
    return `<svg class="wx-ico" viewBox="0 0 32 32" aria-hidden="true" focusable="false">${shape}</svg>`;
  }
  function create({document,request,getSnapshot,t,html,decimal,getLocale,now=Date.now}){
    const byId=id=>document.getElementById(id);
    let data=null,status='loading',generation=0,key='',selected=null;
    const zone=()=>getSnapshot().zone;
    const format=(stamp,options)=>new Intl.DateTimeFormat(getLocale(),{timeZone:zone(),...options}).format(stamp);
    const clock=stamp=>valid(Date.parse(stamp))?format(Date.parse(stamp),{hour:'2-digit',minute:'2-digit'}):'—';
    const dayKey=stamp=>new Intl.DateTimeFormat('sv-SE',{timeZone:zone()}).format(stamp);
    const when=stamp=>{
      const value=Date.parse(stamp);
      if(!valid(value))return '—';
      return dayKey(value)===dayKey(now()) ? clock(stamp) : format(value,{weekday:'short',hour:'2-digit',minute:'2-digit'});
    };
    const kwh=value=>valid(value)?`${decimal(value,1)} kWh`:'—';
    const kw=value=>valid(value)?`${decimal(value/1000,1)} kW`:'—';
    const ct=value=>valid(value)?`${decimal(value,1)} ${t('unit.price')}`:'—';
    // Rounding must not show a negative zero.
    const temperature=value=>valid(value)?`${decimal(Math.round(value)||0,0)}°`:'—';
    const condition=value=>value?t('weather.'+value):t('pv.no_weather');
    const forecastKey=()=>{const snapshot=getSnapshot();return JSON.stringify([snapshot.forecast,snapshot.pv_forecast_totals]);};

    function lead(){
      const snapshot=getSnapshot(),totals=snapshot.pv_forecast_totals??[];
      const parts=[valid(snapshot.live?.solar)?t('pv.lead_now',{power:kw(snapshot.live.solar)}):'',
        valid(snapshot.pv_today_kwh)?t('pv.lead_today',{kwh:kwh(snapshot.pv_today_kwh)}):'',
        valid(totals[0]?.kwh)?t('pv.lead_rest',{kwh:kwh(totals[0].kwh)}):'',
        valid(totals[1]?.kwh)?t('pv.lead_tomorrow',{kwh:kwh(totals[1].kwh)}):''];
      return parts.filter(Boolean).join(' · ');
    }
    function current(){
      const snapshot=getSnapshot(),weather=snapshot.live?.weather,pv=snapshot.pv_now??{};
      const hour=(data?.hours??[]).find(item=>item.now);
      const meta=[valid(hour?.cloud_coverage)?t('pv.clouds',{percent:decimal(hour.cloud_coverage,0)}):'',
        valid(hour?.precipitation_probability)?t('pv.rain_chance',{percent:decimal(hour.precipitation_probability,0)}):'',
        valid(pv.power_w)?t('pv.now_power',{power:kw(pv.power_w)})+(valid(pv.ratio)?' · '+t('pv.now_ratio',{percent:decimal(pv.ratio*100,0)}):''):''].filter(Boolean);
      return `${weatherIcon(weather?.condition)}<span class="temp">${html(valid(weather?.temperature)?decimal(weather.temperature,0)+' '+weather.unit:'—')}</span>
        <div class="wx-now-text"><b>${html(weather?condition(weather.condition):t('pv.no_weather'))}</b><div class="meta">${meta.map(item=>`<span>${html(item)}</span>`).join('')}</div></div>`;
    }
    function hourLabel(item,index,hours){
      if(item.now)return t('pv.now');
      const previous=hours.slice(0,index).reverse().find(entry=>entry.kind==='hour');
      const label=clock(item.start);
      return previous && dayKey(Date.parse(previous.start))!==dayKey(Date.parse(item.start))
        ? format(Date.parse(item.start),{weekday:'short'})+' '+label : label;
    }
    function hourText(item){
      const parts=[when(item.start),condition(item.condition)+(valid(item.temperature)?', '+temperature(item.temperature):''),
        valid(item.cloud_coverage)?t('pv.clouds',{percent:decimal(item.cloud_coverage,0)}):'',
        valid(item.precipitation)&&item.precipitation>0?t('pv.rain',{mm:decimal(item.precipitation,1)}):'',
        valid(item.precipitation_probability)?t('pv.rain_chance',{percent:decimal(item.precipitation_probability,0)}):'',
        t('pv.hour_pv',{kwh:kwh(item.pv_kwh)})+(item.now?' · '+t('pv.rest_of_hour'):'')];
      return parts.filter(Boolean).join(' · ');
    }
    function strip(){
      const hours=data?.hours??[],max=Math.max(.1,...hours.map(item=>item.pv_kwh).filter(valid));
      if(!hours.length)return `<p class="footnote">${html(t('pv.no_hours'))}</p>`;
      return hours.map((item,index)=>item.kind==='night'
        ? `<div class="wx-gap" role="listitem">${html(t('pv.night'))}<br>${html([item.condition?condition(item.condition):'',valid(item.low)?t('pv.night_low',{temperature:temperature(item.low)}):''].filter(Boolean).join(' · '))}<br><small>${html(clock(item.start)+'–'+clock(item.end))}</small></div>`
        : `<button type="button" role="listitem" class="wx-h${item.now?' now':''}" data-hour="${index}" aria-pressed="${String(selected===item.start)}" aria-label="${html(hourText(item))}">
          <span class="t">${html(hourLabel(item,index,hours))}</span>${weatherIcon(item.condition)}<span class="tmp">${html(temperature(item.temperature))}</span>
          <span class="pvbar"><i style="height:${valid(item.pv_kwh)?(item.pv_kwh/max*100).toFixed(0):0}%"></i></span><span class="kwh">${html(valid(item.pv_kwh)?decimal(item.pv_kwh,1):'—')}</span>
          <span class="cc">${html(valid(item.cloud_coverage)?'☁ '+decimal(item.cloud_coverage,0)+' %':'')}</span></button>`).join('');
    }
    function days(){
      return (data?.days??[]).map(day=>{
        const stamp=Date.parse(day.date+'T12:00:00Z');
        const name=day.today?t('pv.today'):format(stamp,{weekday:'short',day:'numeric',month:'numeric'});
        const weather=[day.condition?condition(day.condition):'',valid(day.high)?`${temperature(day.high)} / ${temperature(day.low)}`:'',
          valid(day.precipitation)&&day.precipitation>0?t('pv.rain',{mm:decimal(day.precipitation,1)}):''].filter(Boolean).join(' · ');
        const note=day.today&&valid(day.measured_kwh)?t('pv.day_measured',{kwh:kwh(day.measured_kwh)}):!day.complete?t('pv.day_partial'):'';
        return `<div class="wx-day" role="listitem"><div class="hd"><b>${html(name)}</b>${day.condition?weatherIcon(day.condition):''}</div>
          <small>${html(weather||t('pv.no_weather'))}</small><strong>${html(valid(day.pv_kwh)?'≈ '+kwh(day.pv_kwh):'—')}</strong>${note?`<small>${html(note)}</small>`:''}</div>`;
      }).join('');
    }
    function effect(item){
      const snapshot=getSnapshot(),vehicle=item.vehicle_name??snapshot.vehicle_name??t('node.car');
      const plan=item.vehicle_id?'#car/'+item.vehicle_id:'#car';
      const rows={
        tomorrow_low:()=>[t('pv.effect_tomorrow_low'),t('pv.effect_tomorrow',{kwh:kwh(item.kwh),today:kwh(item.today_kwh)}),t('pv.tag_outlook')],
        tomorrow_high:()=>[t('pv.effect_tomorrow_high'),t('pv.effect_tomorrow',{kwh:kwh(item.kwh),today:kwh(item.today_kwh)}),t('pv.tag_outlook')],
        battery_full:()=>[t('pv.effect_battery_full'),t('pv.effect_battery_full_detail',{soc:decimal(item.soc,0),time:when(item.start)}),t('pv.tag_battery'),'#battery'],
        battery_grid:()=>[t('pv.effect_battery_grid'),t('pv.effect_battery_grid_detail',{start:when(item.start),end:clock(item.end),kwh:kwh(item.kwh),price:ct(item.price_ct)})
          +(valid(item.soc)?' '+t('pv.effect_battery_soc',{soc:decimal(item.soc,0)}):''),t('pv.tag_battery'),'#battery'],
        export:()=>[t('pv.effect_export'),t('pv.effect_export_detail',{kwh:kwh(item.kwh),time:when(item.start)}),t('pv.tag_grid'),'#usage/grid'],
        car_grid:()=>[t('pv.effect_car_grid',{vehicle}),t('pv.effect_car_grid_detail',{kwh:kwh(item.kwh),time:when(item.start),price:ct(item.price_ct)}),t('pv.tag_plan'),plan],
        car_pv:()=>[t('pv.effect_car_pv',{vehicle}),t('pv.effect_car_pv_detail',{kwh:kwh(item.kwh),time:when(item.end)}),t('pv.tag_plan'),plan]};
      const row=rows[item.id]?.();
      if(!row)return '';
      const [title,detail,tag,href]=row,body=`<span><b>${html(title)}</b><br><small>${html(detail)}</small></span>`;
      return href?`<a class="row rowlink" href="${html(href)}">${body}<span class="tag accent">${html(tag)} →</span></a>`:`<div class="row">${body}<span class="tag">${html(tag)}</span></div>`;
    }
    function drawSnapshot(){
      const effects=getSnapshot().pv_effects??[];
      byId('pv-lead').textContent=lead();
      byId('pv-now').innerHTML=current();
      byId('pv-effects').innerHTML=effects.length?effects.map(effect).join(''):`<p class="footnote">${html(t('pv.effects_none'))}</p>`;
    }
    function draw(){
      drawSnapshot();
      const source=[data?.source,data?.fetched_at?t('pv.updated',{time:clock(data.fetched_at)}):''].filter(Boolean).join(' · ');
      byId('pv-source').textContent=source;byId('pv-source').hidden=!source;
      byId('pv-status').textContent=status==='available'?'':t('forecast.'+status);
      byId('pv-status').hidden=status==='available';
      byId('pv-strip').innerHTML=status==='loading'?'':strip();
      byId('pv-days').innerHTML=status==='loading'?'':days();
      const item=(data?.hours??[]).find(entry=>entry.start===selected);
      byId('pv-detail').textContent=item?hourText(item):t('pv.hour_hint');
    }
    async function load(){
      const token=++generation;status='loading';key=forecastKey();draw();
      try{const result=await request('weather_forecast');if(token!==generation)return;data=result;status=result.status;}
      catch{if(token!==generation)return;data=null;status='unavailable';}
      if(!STATUSES.includes(status))status='unavailable';
      draw();
    }
    byId('pv-strip').addEventListener('click',event=>{
      const button=event.target.closest('[data-hour]');
      if(!button)return;
      selected=data?.hours?.[Number(button.dataset.hour)]?.start??null;
      byId('pv-strip').querySelectorAll('[data-hour]').forEach(node=>node.setAttribute('aria-pressed',String(node===button)));
      const item=data?.hours?.[Number(button.dataset.hour)];
      byId('pv-detail').textContent=item?hourText(item):t('pv.hour_hint');
    });
    return {
      open(){selected=null;load();},
      // Snapshot refreshes update live values; a new PV forecast reloads the hourly strip.
      update(){if(status!=='loading'&&forecastKey()!==key)load();else drawSnapshot();},
      close(){generation++;}
    };
  }
  const api={weatherIcon,create};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EosForecast=api;
})(globalThis);
