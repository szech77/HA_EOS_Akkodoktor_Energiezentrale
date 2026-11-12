/* Display-only 24-hour forecasts. Missing intervals never become zero output. */
(function(root){
  'use strict';
  const hour=3600000,day=24*hour,valid=Number.isFinite;
  function solarSlots(rows,start,end=start+day){
    const sorted=(rows??[]).filter(row=>valid(row.solar)&&row.solar>=0).map(row=>({
      start:Date.parse(row.time),end:Date.parse(row.end),value:row.solar/1000
    })).filter(row=>valid(row.start)&&valid(row.end)&&row.end>row.start&&row.end>start&&row.start<end)
      .sort((a,b)=>a.start-b.start);
    let cursor=start;
    return sorted.flatMap(row=>{
      const first=Math.max(start,cursor,row.start),last=Math.min(end,row.end);
      if(last<=first)return [];
      cursor=last;return [{start:first,end:last,value:row.value}];
    });
  }
  function solarSummary(slots){
    const covered=slots.reduce((sum,row)=>sum+row.end-row.start,0);
    return {kwh:covered?slots.reduce((sum,row)=>sum+row.value*(row.end-row.start)/hour,0):null,
      peak:slots.length?Math.max(...slots.map(row=>row.value)):null,complete:covered>=day,covered};
  }
  function valueAt(rows,stamp){return rows.find(row=>row.start<=stamp&&stamp<row.end);}
  function weatherRows(rows,start){
    return (rows??[]).map(row=>({...row,start:Date.parse(row.time),end:Date.parse(row.end)}))
      .filter(row=>valid(row.start)&&valid(row.end)&&row.end>row.start&&row.end>start&&row.start<start+day)
      .sort((a,b)=>a.start-b.start);
  }
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
    return `<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">${shape}</svg>`;
  }
  function create({document,request,getSnapshot,t,html,decimal,getLocale,now=Date.now}){
    const dialog=document.getElementById('weather-dialog'),body=document.getElementById('forecast-body');
    let data=null,status='loading',start=0,generation=0,selected=null,solar=[],weather=[],pvKey='';
    const dateTime=stamp=>new Intl.DateTimeFormat(getLocale(),{timeZone:getSnapshot().zone,dateStyle:'short',timeStyle:'short'}).format(stamp);
    const clock=stamp=>new Intl.DateTimeFormat(getLocale(),{timeZone:getSnapshot().zone,hour:'2-digit',minute:'2-digit'}).format(stamp);
    const text=key=>html(t(key));
    const condition=value=>t('weather.'+value);
    const amount=(value,unit)=>valid(value)?decimal(value,2)+' '+unit:'—';
    const x=stamp=>Math.max(0,Math.min(100,(stamp-start)*100/day));
    function axis(){
      return `<div class="forecast-axis">${Array.from({length:7},(_,i)=>`<span>${html(clock(start+i*4*hour))}</span>`).join('')}</div>`;
    }
    function plot(kind,content,labels){
      return `<div class="forecast-chart ${kind}"><div class="forecast-y">${labels.map(html).map(label=>`<span>${label}</span>`).join('')}</div><div class="forecast-plot" data-forecast-plot="${kind}"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path class="forecast-guide" d="M0 0H100M0 25H100M0 50H100M0 75H100M0 100H100"/>${content}<line class="forecast-probe" x1="0" x2="0" y1="0" y2="100" hidden/></svg><div class="forecast-tooltip" hidden></div></div>${axis()}</div>`;
    }
    function weatherChart(){
      const temperatures=weather.map(row=>row.temperature).filter(valid);
      const low=temperatures.length?Math.floor(Math.min(...temperatures))-1:0;
      const high=temperatures.length?Math.max(low+2,Math.ceil(Math.max(...temperatures))+1):1;
      const y=value=>(high-value)*75/(high-low);
      let previous=null;
      const line=weather.map(row=>{
        if(!valid(row.temperature)){previous=null;return '';}
        const command=previous&&row.start<=previous.end?'L':'M';previous=row;
        return `${command}${x(row.start).toFixed(3)} ${y(row.temperature).toFixed(3)}`;
      }).join(' ');
      const rainMax=Math.max(1,...weather.map(row=>row.precipitation).filter(valid));
      const rain=weather.filter(row=>valid(row.precipitation)).map(row=>{
        const h=row.precipitation*18/rainMax;
        return `<rect class="forecast-rain" x="${x(row.start).toFixed(3)}" y="${100-h}" width="${Math.max(0,x(row.end)-x(row.start)-.3).toFixed(3)}" height="${h}"/>`;
      }).join('');
      const icons=Array.from({length:9},(_,i)=>{
        const stamp=start+i*3*hour,row=valueAt(weather,Math.min(stamp,start+day-1));
        return `<span title="${html(clock(stamp)+' · '+(row?condition(row.condition):t('forecast.no_hour')))}">${row?weatherIcon(row.condition):'—'}</span>`;
      }).join('');
      return `<div class="forecast-icons">${icons}</div>`+plot('weather',`<path class="forecast-temperature" d="${line}"/>${rain}`,
        [amount(high,data.temperature_unit),amount((low+high)/2,data.temperature_unit),amount(low,data.temperature_unit),decimal(rainMax,1)+' mm'])
        +`<div class="forecast-legend"><span class="temperature-key">${text('forecast.temperature')}</span><span class="rain-key">${text('forecast.precipitation')} · 0–${html(decimal(rainMax,1))} mm</span></div>`
        +(!temperatures.length?`<p class="footnote">${text('forecast.temperature_missing')}</p>`:'')
        +(!weather.some(row=>valid(row.precipitation))?`<p class="footnote">${text('forecast.precipitation_missing')}</p>`:'');
    }
    function solarChart(){
      const max=Math.max(1,...solar.map(row=>row.value)),y=value=>100-value/max*100;
      const area=solar.map(row=>`M${x(row.start)} 100V${y(row.value)}H${x(row.end)}V100Z`).join(' ');
      const line=solar.map(row=>`M${x(row.start)} ${y(row.value)}H${x(row.end)}`).join(' ');
      return plot('solar',`<path class="forecast-solar-area" d="${area}"/><path class="forecast-solar-line" d="${line}"/>`,
        [amount(max,'kW'),amount(max/2,'kW'),'0 kW']);
    }
    function draw(){
      const focused=document.activeElement?.id;
      const snapshot=getSnapshot();
      solar=solarSlots(snapshot.forecast,start);weather=weatherRows(data?.rows,start);
      pvKey=JSON.stringify(snapshot.forecast);
      const summary=solarSummary(solar),current=snapshot.live?.weather;
      const weatherBody=status==='loading'?`<p role="status">${text('forecast.loading')}</p>`:
        status!=='available'?`<p role="status">${text('forecast.'+status)}</p>`:weatherChart();
      document.getElementById('forecast-title').textContent=t('forecast.title');
      document.getElementById('forecast-close').setAttribute('aria-label',t('forecast.close'));
      body.innerHTML=`<p class="forecast-subtitle">${text('forecast.next24')}</p><p class="forecast-range">${html(dateTime(start)+' – '+dateTime(start+day))}</p>
        <section class="forecast-panel"><div class="panel-heading"><h3>${text('forecast.weather')}</h3><span>${current?html(t('forecast.now')+' '+amount(current.temperature,current.unit)+' · '+condition(current.condition)):''}</span></div>${weatherBody}</section>
        <section class="forecast-panel"><div class="panel-heading"><h3>${text('forecast.pv')}</h3><div class="forecast-summary"><div><small>${text(summary.complete?'forecast.yield':'forecast.yield_partial')}</small><strong>${html(amount(summary.kwh,'kWh'))}</strong></div><div><small>${text('forecast.peak')}</small><strong>${html(amount(summary.peak,'kW'))}</strong></div></div></div>
        ${solar.length?solarChart():`<p>${text('forecast.pv_missing')}</p>`}${!summary.complete&&solar.length?`<p class="footnote">${text('forecast.partial')}</p>`:''}</section>
        <div class="forecast-selection"><label>${text('forecast.select_hour')}<input id="forecast-hour" type="range" min="0" max="23.99" step="0.25" value="${selected===null?0:(selected-start)/hour}"/></label><output id="forecast-selected" aria-live="polite"></output></div>
        <footer class="forecast-footer"><span>${text('forecast.sources')}${data?.source?' · '+html(data.source):''}${data?.fetched_at?' · '+html(t('forecast.updated')+' '+dateTime(Date.parse(data.fetched_at))):''}</span><button type="button" id="forecast-retry">${text('forecast.refresh')}</button></footer>`;
      document.getElementById('forecast-retry').addEventListener('click',load);
      document.getElementById('forecast-retry').disabled=status==='loading';
      document.getElementById('forecast-hour').addEventListener('input',event=>probe(start+Number(event.target.value)*hour));
      body.querySelectorAll('[data-forecast-plot]').forEach(node=>{
        const point=event=>{const box=node.getBoundingClientRect();probe(start+Math.max(0,Math.min(.9999,(event.clientX-box.left)/box.width))*day);};
        node.addEventListener('pointermove',event=>{if(event.pointerType==='mouse'||event.buttons)point(event);});
        node.addEventListener('pointerdown',point);
      });
      if(selected!==null)probe(selected);
      if(focused==='forecast-hour')document.getElementById('forecast-hour').focus();
    }
    function probe(stamp){
      selected=stamp;
      const row=valueAt(weather,stamp),pv=valueAt(solar,stamp);
      const temperature=amount(row?.temperature,data?.temperature_unit??'°C');
      const weatherText=row?`${temperature} · ${condition(row.condition)} · ${t('forecast.precipitation')} ${amount(row.precipitation,'mm')}${valid(row.precipitation_probability)?' · '+decimal(row.precipitation_probability)+' %':''}`:t('forecast.no_hour');
      const pvText=amount(pv?.value,'kW');
      document.getElementById('forecast-selected').textContent=`${dateTime(stamp)} · ${weatherText} · ${t('forecast.pv')} ${pvText}`;
      const slider=document.getElementById('forecast-hour');slider.value=(stamp-start)/hour;slider.setAttribute('aria-valuetext',dateTime(stamp));
      body.querySelectorAll('[data-forecast-plot]').forEach(node=>{
        const line=node.querySelector('.forecast-probe');line.removeAttribute('hidden');line.setAttribute('x1',x(stamp));line.setAttribute('x2',x(stamp));
        const tip=node.querySelector('.forecast-tooltip');tip.hidden=false;tip.style.left=x(stamp)+'%';tip.style.transform=x(stamp)>50?'translateX(-100%)':'';
        tip.textContent=clock(stamp)+' · '+(node.dataset.forecastPlot==='solar'?pvText:temperature);
      });
    }
    async function load(){
      const token=++generation;status='loading';draw();
      try{const result=await request('weather_forecast');if(token!==generation||!dialog.open)return;data=result;status=result.status;}
      catch{if(token!==generation||!dialog.open)return;data=null;status='unavailable';}
      if(!['available','missing_source','unsupported','unavailable','empty'].includes(status))status='unavailable';
      draw();
    }
    document.getElementById('forecast-close').addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{generation++;document.getElementById('flow-weather').focus();});
    dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();});
    return {open(){if(dialog.open)return;start=now();selected=null;data=null;dialog.showModal();load();},
      update(){if(dialog.open&&JSON.stringify(getSnapshot().forecast)!==pvKey)draw();}};
  }
  const api={solarSlots,solarSummary,valueAt,weatherRows,weatherIcon,create};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.EosForecast=api;
})(globalThis);
