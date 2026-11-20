/* Consumption reports include explicit estimates, never control/display-held power. */
const billingPeriods = ['day','month','year'];
const billingPeriodKey = 'eos-energiezentrale.billing-period';
function savedBillingPeriod() {
  try {
    const value=window.localStorage.getItem(billingPeriodKey);
    if(billingPeriods.includes(value))return value;
  } catch { /* Browser storage may be disabled. */ }
  return 'month';
}
// The report charts show power (kW, day view only), energy (kWh) or money (€); the choice is a
// per-viewer convenience.
const billingUnits = ['kw','kwh','eur'];
const billingUnitKey = 'eos-energiezentrale.billing-unit';
function savedBillingUnit() {
  try {
    const value=window.localStorage.getItem(billingUnitKey);
    if(billingUnits.includes(value))return value;
  } catch { /* Browser storage may be disabled. */ }
  return 'kwh';
}
const billing = {period:savedBillingPeriod(),unit:savedBillingUnit(),date:null,data:null,key:null,loading:false,at:0,error:null};
function selectBillingUnit(value) {
  if(!billingUnits.includes(value))return false;
  billing.unit=value;
  try {window.localStorage.setItem(billingUnitKey,value);} catch { /* Keep the in-memory selection. */ }
  return true;
}
function selectBillingPeriod(value) {
  if(!billingPeriods.includes(value))return false;
  billing.period=value;
  try {window.localStorage.setItem(billingPeriodKey,value);} catch { /* Keep the in-memory selection. */ }
  return true;
}
const sourceColors = {pv:'#f2c94c',battery:'#55c7cb',grid:'#5794f2',unknown:'#8995a5'};
const money = value => {
  const tiny = value !== 0 && Math.abs(value) < .0001;
  const format = new Intl.NumberFormat(language.locale,{style:'currency',currency:'EUR',
    minimumFractionDigits:2, maximumFractionDigits:value !== 0 && Math.abs(value)<.01 ? 4 : 2});
  return tiny ? (value>0 ? '< ' : '> ')+format.format(Math.sign(value)*.0001) : format.format(value);
};
const energyValue = value => `${decimal(value,2)} kWh`;
const isEstimated = amount => amount?.estimated === true;
const costValue = amount => amount?.cost_available ? `${isEstimated(amount) ? '≈ ' : ''}${money(amount.cost_eur)}${amount.cost_partial ? ' ('+t('billing.known_portion')+')' : ''}` : '—';
const averageCost = amount => {
  const rate=amount?.average_price_ct;
  return valid(rate) ? `${isEstimated(amount) ? '≈ ' : ''}${price(rate)}` : '—';
};
const estimatedAverageNote = amount => isEstimated(amount)&&valid(amount?.average_price_ct) ? t('billing.estimated_average_note') : '';
const averageCostLabel = amount => {
  const value=averageCost(amount);
  return t('billing.average_unit_price',{price:value==='—' ? `— ${t('unit.price')}` : value});
};
const costWithPrice = amount => `${costValue(amount)} · ${averageCostLabel(amount)}`;
const billingName = key => key==='total' ? t('billing.total_consumption') : key==='grid' ? t('usage.grid_title') : key==='pv' ? t('usage.pv_title') : key.startsWith('car/') ? snapshot.vehicles?.find(item=>item.id===key.slice(4))?.name ?? t('device.car') : t(`device.${key}`);
const isCarKey = key => key==='car' || key.startsWith('car/');
const usageEnabled = key => key==='house' || (typeof consumerEnabled==='function' && consumerEnabled(key));
// Report pages in the order of the sub navigation; single vehicles stay on the car page.
function usageKeys() {
  const cars=usageEnabled('car') ? ['car',...(snapshot.vehicles?.length>1 ? snapshot.vehicles.map(item=>'car/'+item.id) : [])] : [];
  return ['pv','house',...cars,...(usageEnabled('heat') ? ['heat'] : []),'grid','total'];
}
const energyOr = value => valid(value) ? energyValue(value) : '—';
const moneyOr = (value, approximate=false) => valid(value) ? (approximate ? '≈ ' : '')+money(value) : '—';
const plusMoney = (value, approximate=false) => valid(value) ? (approximate ? '≈ +' : '+')+money(value) : '—';
const feedInMoney = balance => balance && !(balance.export_kwh>.0001 && !valid(balance.feed_in_price_ct)) ? plusMoney(balance.export_eur,balance.cost_partial) : '—';

function dayBalance() {
  const report=snapshot.accounting, target=byId('day-balance');
  if (!report) {target.innerHTML='';return;}
  const keys=Object.keys(report.overview?.consumers??{}), total=report.overview?.total, balance=report.balance, views=report.views??{};
  const tile=(href,name,value,context,extra='',kind='')=>`<a class="balance-card${kind}" href="${href}"><span>${html(name)}</span><strong>${html(value)}</strong><span>${html(context)}</span>${extra}<small class="more">${th('usage.open')}</small></a>`;
  const shareText=key=>valid(views[key]?.self_percent) ? t('usage.self_share',{share:percent(views[key].self_percent)})+' · ' : '';
  const tiles=keys.map(key=>{
    const value=report.overview.consumers[key];
    return tile('#usage/'+key,billingName(key),(value?.energy_estimated?'≈ ':'')+(value?energyValue(value.kwh):'—'),shareText(key)+costWithPrice(value),sourceBar(value));
  });
  if (balance) tiles.push(tile('#usage/grid',t('usage.feed_in'),energyValue(balance.export_kwh),
    feedInMoney(balance)+' · '+t('usage.import_short',{energy:energyValue(balance.grid_import_kwh)}),'',' feed'));
  tiles.push(tile('#usage/total',t('billing.total_consumption'),(total?.energy_estimated?'≈ ':'')+(total?energyValue(total.kwh):'—'),
    costWithPrice(total)+(balance ? ' · '+t('usage.net_short',{value:moneyOr(balance.net_eur,balance.cost_partial)}) : '')));
  const sum=`${total?energyValue(total.kwh):'—'} · ${costValue(total)}`+(balance ? ' · '+t('usage.feed_short',{value:feedInMoney(balance)}) : '');
  target.innerHTML=`<div class="panel-heading"><h2>${th('billing.today')}</h2><span>${th('billing.total')}: ${html(sum)}</span></div>
    <div class="balance-grid">${tiles.join('')}</div><p class="footnote">${th('billing.partial')} ${total?.cost_partial?th('billing.unknown_cost'):''} ${html(estimatedAverageNote(total))}</p>`;
}

function sourceBar(value) {
  if (!value || value.kwh<=0) return '<div class="source-bar empty"></div>';
  return `<div class="source-bar" role="img" aria-label="${html(Object.entries(value.sources).map(([key,item])=>`${t('billing.'+key)} ${decimal(item.share_percent)} %`).join(', '))}">${Object.entries(value.sources).map(([key,item])=>`<span style="width:${item.share_percent}%;background:${sourceColors[key]}" title="${html(t('billing.'+key))}: ${decimal(item.share_percent)} %"></span>`).join('')}</div>`;
}

function billingRoute(requested) {
  if (!requested.startsWith('usage/')) return false;
  const key=requested.slice(6);
  return key==='total' || key==='grid' || key==='pv' || (['house','heat','car'].includes(key) ? usageEnabled(key) : key.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===key.slice(4)));
}

async function fetchBilling(force=false) {
  if (!billing.date) billing.date=localDay(windowNow());
  const key=`${billing.period}/${billing.date}`;
  if (billing.loading || (!force && billing.key===key && Date.now()-billing.at<60000)) return;
  billing.loading=true;billing.error=null;
  try {
    const result=await api('accounting',{period:billing.period,date:billing.date});
    if (`${billing.period}/${billing.date}`===key) {billing.data=result;billing.key=key;billing.at=Date.now();}
  } catch(error) {billing.error=error.message;}
  finally {billing.loading=false;if(`${billing.period}/${billing.date}`!==key){void fetchBilling(true);}else if(route.startsWith('usage/')) usageDetail(route.slice(6),false);}
}

// Filled areas stacked over time for the power profile. Layers stack in order, positive values
// upwards and negative ones downwards; entries without data split the areas.
function stackedAreas(slots, rows, layers, x, y) {
  const stacks=slots.map(slot=>{
    const row=rows.find(item=>item.time===slot.key);
    if(!row)return null;
    let positive=0,negative=0;
    return layers.map(layer=>{
      const value=layer.value(row)??0,from=value>=0?positive:negative,to=from+value;
      if(value>=0)positive=to;else negative=to;
      return [from,to];
    });
  });
  return layers.map((layer,index)=>{
    const segments=[];let current=[];
    stacks.forEach((stack,slot)=>{
      if(stack)current.push([slot,...stack[index]]);
      else if(current.length){segments.push(current);current=[];}
    });
    if(current.length)segments.push(current);
    return segments.filter(points=>points.some(([,from,to])=>Math.abs(to-from)>1e-9)).map(points=>{
      // A single hour between gaps becomes a narrow plateau instead of a line.
      if(points.length===1)points=[[points[0][0]-.35,points[0][1],points[0][2]],[points[0][0]+.35,points[0][1],points[0][2]]];
      const edge=points.map(([slot,,to])=>`${x(slot).toFixed(1)},${y(to).toFixed(1)}`);
      const base=[...points].reverse().map(([slot,from])=>`${x(slot).toFixed(1)},${y(from).toFixed(1)}`);
      return `<polygon class="area" points="${edge.join(' ')} ${base.join(' ')}" style="fill:${layer.color}"/>`;
    }).join('');
  }).join('');
}

// Day view: the backend's power profile (short averages from the local minute history) in kW
// over time, as stacked areas. Hours stay tappable for their energy and cost.
function profilePoints(key) {
  const profile=billing.period==='day' ? billing.data?.power_profile : null;
  const points=(profile?.points??[]).filter(point=>key==='grid' ? point.grid : key==='pv' ? valid(point.solar) : point[key]);
  // The PV view also draws when only the forecast exists, e.g. early in the morning.
  if(key==='pv' && billing.period==='day' && (points.length || billing.data?.pv_forecast?.points?.length))return {...(profile??{}),points};
  return points.length ? {...profile,points} : null;
}
// Pointer readout of the power chart: the values of the profile point under the cursor.
let powerHover=null,powerPointer=null;
function powerReadout(point, key) {
  const kw=value=>`${decimal((value??0)/1000,2)} kW`;
  const stamp=new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,hour:'2-digit',minute:'2-digit'}).format(new Date(point.time));
  if(key==='grid')return {title:stamp,lines:[[t('usage.import'),kw(point.grid.import),sourceColors.grid],[t('usage.feed_in'),kw(point.grid.export),sourceColors.pv]]};
  if(key==='pv'){
    const measured=valid(point.solar);
    const watts=(values,names,prefix)=>measured?names.filter(([name])=>(values?.[name]??0)>5).map(([name,color])=>[t(prefix+name),kw(values[name]),color]):[];
    const flows=watts(point.pv_flow,pvFlows,'usage.pv_to_'),gaps=watts(point.pv_gap,pvGaps,'usage.pv_gap_');
    return {title:measured?`${stamp} · PV ${kw(point.solar)}`:stamp,lines:[...flows,...gaps,
      ...(valid(point.forecast)?[[t('usage.pv_forecast'),kw(point.forecast),'transparent']]:[])]};
  }
  const parts=point[key],total=Object.values(parts).reduce((sum,value)=>sum+(value??0),0);
  return {title:`${stamp} · ${kw(total)}`,lines:Object.entries(sourceColors).filter(([source])=>parts[source]>0).map(([source,color])=>[t('billing.'+source),kw(parts[source]),color])};
}
function showPowerReadout(event) {
  const svg=event.target.closest?.('svg.power-chart'),tip=byId('usage-charts').querySelector?.('.power-tip');
  const cursor=svg?.querySelector('.power-cursor');
  if(!svg||!tip||!cursor||!powerHover?.points.length)return;
  // Remembered so the readout survives the periodic redraw of the page.
  powerPointer=event.clientX;
  const box=svg.getBoundingClientRect(),position=(event.clientX-box.left)/box.width*powerHover.width;
  let nearest=powerHover.points[0];
  for(const item of powerHover.points)if(Math.abs(item.x-position)<Math.abs(nearest.x-position))nearest=item;
  // Between data (a gap or after the last sample) nothing is shown.
  if(Math.abs(nearest.x-position)>powerHover.reach){hidePowerReadout();return;}
  cursor.setAttribute('x1',nearest.x);cursor.setAttribute('x2',nearest.x);cursor.removeAttribute('visibility');
  const readout=powerReadout(nearest.row,powerHover.key);
  tip.innerHTML=`<b>${html(readout.title)}</b>`+readout.lines.map(([label,value,color])=>`<span><i style="background:${color}"></i>${html(label)}<em>${html(value)}</em></span>`).join('');
  tip.hidden=false;
  const container=byId('usage-charts').getBoundingClientRect(),pixel=box.left-container.left+nearest.x/powerHover.width*box.width;
  const width=tip.offsetWidth||160;
  tip.style.left=`${Math.max(0,Math.min(container.width-width,pixel+12>container.width-width ? pixel-width-12 : pixel+12))}px`;
}
function hidePowerReadout(event) {
  if(event)powerPointer=null;
  const charts=byId('usage-charts');
  charts.querySelector?.('.power-cursor')?.setAttribute('visibility','hidden');
  const tip=charts.querySelector?.('.power-tip');if(tip)tip.hidden=true;
}

function powerChart(key, profile, entry, balance, forecast=null) {
  const width=Math.max(280,Math.min(1000,window.innerWidth-100)),height=240,left=44,right=12,top=18,bottom=38;
  const slots=billingSlots(),step=(width-left-right)/Math.max(1,slots.length),starts=slots.map(slot=>Date.parse(slot.key));
  const half=(profile.step_s??120)*500,gap=(profile.gap_s??600)*1000;
  // Position on the hour slots, so a 23- or 25-hour day keeps its real hours.
  const position=stamp=>{
    const index=Math.max(0,starts.findLastIndex(start=>start<=stamp));
    return left+(index+Math.min(1,Math.max(0,(stamp-starts[index])/3600000)))*step;
  };
  const grid=key==='grid',pv=key==='pv',kw=value=>(value??0)/1000;
  const layers=grid ? [{color:sourceColors.grid,value:point=>kw(point.grid.import)},{color:sourceColors.pv,value:point=>-kw(point.grid.export)}]
    : pv ? [...pvFlows.map(([name,color])=>({color,value:point=>kw(point.pv_flow?.[name])})),
            ...pvGaps.map(([name,color])=>({color,value:point=>-kw(point.pv_gap?.[name])}))]
    : Object.entries(sourceColors).map(([source,color])=>({color,value:point=>kw(point[key][source])}));
  // PV forecast power (backend, from now on) as a dashed step line over the measured area.
  const ahead=pv ? (forecast?.points??[]) : [];
  const forecastAt=stamp=>ahead.find(item=>Date.parse(item.time)<=stamp&&stamp<Date.parse(item.end))?.w;
  const entries=[],rows=[],xs=[];
  let previous=null;
  for(const point of profile.points){
    const stamp=Date.parse(point.time)+half;
    if(previous!==null && stamp-previous>gap){entries.push({key:'gap'+entries.length});xs.push(null);}
    entries.push({key:point.time});rows.push({...point,time:point.time});xs.push(position(stamp));previous=stamp;
  }
  const sums=rows.map(row=>layers.reduce((sum,layer)=>sum+Math.max(0,layer.value(row)),0));
  const lows=rows.map(row=>layers.reduce((sum,layer)=>sum+Math.min(0,layer.value(row)),0));
  const maximum=Math.max(.1,...sums,...ahead.map(item=>kw(item.w))),minimum=Math.min(0,...lows),span=maximum-minimum,plot=height-top-bottom;
  const y=value=>top+(maximum-value)/span*plot;
  const x=index=>{const base=Math.round(index);return (xs[base]??left)+(index-base)*step/30;};
  const ticks=minimum<0?[0,maximum,maximum/2,minimum,minimum/2].filter((value,index)=>index===0||Math.abs(y(value)-y(0))>=14):Array.from({length:5},(_,i)=>minimum+span*i/4);
  const axis=ticks.map(value=>`<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--edge)"${value===0&&minimum<0?' stroke-width="2"':''}/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${html(decimal(Math.abs(value),span<3?2:1))}</text>`).join('');
  const areas=stackedAreas(entries,rows,layers,x,y);
  const line=ahead.length ? `<polyline class="forecast-line" points="${ahead.flatMap(item=>[Date.parse(item.time),Date.parse(item.end)].map(stamp=>`${position(stamp).toFixed(1)},${y(kw(item.w)).toFixed(1)}`)).join(' ')}" stroke="${sourceColors.pv}"/>` : '';
  const hours=grid||pv ? (balance?.bins??[]) : (entry?.bins??[]);
  const hits=slots.map((slot,index)=>{
    const row=hours.find(item=>item.time===slot.key);if(!row && !pv)return '';
    const tooltip=grid ? gridTooltip(row,slot) : pv ? pvTooltip(row,slot,forecast) : binTooltip(row,slot);
    // No native title here: the pointer readout shows the values at the cursor.
    return `<g tabindex="0" role="button" data-billing-bin="${html(slot.date)}" aria-label="${html(tooltip)}"><rect x="${left+index*step}" y="${top}" width="${step}" height="${plot}" fill="transparent"/></g>`;
  }).join('');
  const labels=slots.map((slot,index)=>index%Math.max(1,Math.ceil(slots.length/(window.innerWidth<600?5:10)))===0?`<text x="${left+(index+.5)*step}" y="${height-12}" text-anchor="middle">${html(slot.label)}</text>`:'').join('');
  const measured=rows.map(row=>({row:pv?{...row,forecast:forecastAt(Date.parse(row.time)+half)}:row,x:xs[entries.findIndex(item=>item.key===row.time)]}));
  // Ahead of the measurements the PV readout follows the forecast in 15-minute steps.
  const last=rows.length ? Date.parse(rows.at(-1).time)+half : -Infinity;
  const future=ahead.flatMap(item=>{const out=[];for(let stamp=Date.parse(item.time);stamp<Date.parse(item.end);stamp+=900000)if(stamp>last)out.push({row:{time:new Date(stamp).toISOString(),forecast:item.w},x:position(stamp)});return out;});
  powerHover={key,width,reach:Math.max(6,step*(profile.gap_s??600)/7200),
    points:[...measured,...future].filter(item=>item.x!==null&&item.x!==undefined)};
  return `<svg class="billing-chart power-chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${html(t(grid?'usage.grid_power_chart':pv?'usage.pv_power_chart':'usage.power_chart'))}">${axis}${areas}${line}${hits}${labels}`
    +`<line class="power-cursor" x1="0" x2="0" y1="${top}" y2="${top+plot}" visibility="hidden"/></svg><div class="power-tip" role="status" hidden></div>`;
}
// PV destinations above zero and the consumption PV did not cover below zero (backend values:
// pv_flow / pv_gap per bin and per profile point; battery energy split by its charging origin).
const pvFlows=[['house','var(--house)'],['car','var(--car)'],['heat','var(--heat)'],['storage','var(--battery)'],['export','var(--solar)']];
const pvGaps=[['battery_pv','color-mix(in srgb,var(--battery) 60%,transparent)'],['battery_grid','color-mix(in srgb,var(--battery) 35%,var(--grid) 35%)'],
  ['battery_unknown','color-mix(in srgb,var(--battery) 30%,transparent)'],['grid','color-mix(in srgb,var(--grid) 70%,transparent)'],['unknown','var(--dim)']];
const pvParts=(values,names)=>names.filter(([name])=>(values?.[name]??0)>.005);
const pvTooltip=(row,slot,forecast)=>{
  const ahead=forecast?.bins?.find(item=>item.time===slot.key)?.kwh;
  const flows=pvParts(row?.pv_flow,pvFlows).map(([name])=>`${t('usage.pv_to_'+name)} ${energyValue(row.pv_flow[name])}`).join(' · ');
  const gaps=pvParts(row?.pv_gap,pvGaps).map(([name])=>`${t('usage.pv_gap_'+name)} ${energyValue(row.pv_gap[name])}`).join(' · ');
  return [slot.label,row ? `${t('usage.pv_produced')} ${energyValue(row.pv_kwh)}${flows ? ': '+flows : ''}` : '',
    gaps ? `${t('usage.pv_uncovered')}: ${gaps}` : '',valid(ahead)&&ahead>0 ? `${t('usage.pv_forecast')} ${energyValue(ahead)}` : ''].filter(Boolean).join('\n');
};
function pvChart(balance, forecast) {
  const rows=balance?.bins ?? [],ahead=forecast?.bins ?? [];
  if (!rows.length && !ahead.length) return `<p class="empty-state">${th('billing.no_data')}</p>`;
  const width=Math.max(280,Math.min(1000,window.innerWidth-100)),height=280,left=44,right=12,top=18,bottom=38;
  const slots=billingSlots(),step=(width-left-right)/Math.max(1,slots.length),barWidth=Math.max(1,step*.7);
  const row=key=>rows.find(item=>item.time===key),total=(values,names)=>names.reduce((sum,[name])=>sum+Math.max(0,values?.[name]??0),0);
  const expected=key=>ahead.find(item=>item.time===key)?.kwh??0;
  const maximum=Math.max(.1,...slots.map(slot=>total(row(slot.key)?.pv_flow,pvFlows)+expected(slot.key)));
  const minimum=-Math.max(.1,...slots.map(slot=>total(row(slot.key)?.pv_gap,pvGaps)));
  const span=maximum-minimum,plot=height-top-bottom,y=value=>top+(maximum-value)/span*plot;
  const ticks=[0,maximum,maximum/2,minimum,minimum/2].filter((value,index)=>index===0||Math.abs(y(value)-y(0))>=14);
  const axis=ticks.map(value=>`<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--edge)"${value===0?' stroke-width="2"':''}/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${html(decimal(Math.abs(value),1))}</text>`).join('');
  const bars=slots.map((slot,index)=>{
    const bin=row(slot.key),coming=expected(slot.key);
    if(!bin && !(coming>0))return '';
    const x=left+(index+.5)*step;let stack=0,below=0;
    const rect=(from,to,color)=>`<rect x="${x-barWidth/2}" y="${Math.min(y(from),y(to))}" width="${barWidth}" height="${Math.max(0,Math.abs(y(from)-y(to)))}" style="fill:${color}"/>`;
    const shapes=pvFlows.map(([name,color])=>{const from=stack;stack+=Math.max(0,bin?.pv_flow?.[name]??0);return stack>from?rect(from,stack,color):'';}).join('')
      +pvGaps.map(([name,color])=>{const from=below;below-=Math.max(0,bin?.pv_gap?.[name]??0);return below<from?rect(from,below,color):'';}).join('')
      +(coming>0?`<rect class="forecast-bar" x="${x-barWidth/2}" y="${y(stack+coming)}" width="${barWidth}" height="${Math.max(0,y(stack)-y(stack+coming))}" stroke="${sourceColors.pv}"/>`:'');
    const tooltip=pvTooltip(bin,slot,forecast);
    return `<g tabindex="0" role="button" data-billing-bin="${html(slot.date)}" aria-label="${html(tooltip)}"><title>${html(tooltip)}</title>${shapes}<rect x="${x-step/2}" y="${top}" width="${step}" height="${plot}" fill="transparent"/></g>`;
  }).join('');
  const labels=slots.map((slot,index)=>index%Math.max(1,Math.ceil(slots.length/(window.innerWidth<600?5:10)))===0?`<text x="${left+(index+.5)*step}" y="${height-12}" text-anchor="middle">${html(slot.label)}</text>`:'').join('');
  return `<svg class="billing-chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${html(t('usage.pv_chart'))}">${axis}${bars}${labels}</svg>`;
}
const binTooltip=(row,slot)=>`${slot.label} · ${energyValue(row.kwh)} · ${costWithPrice(row)}\n${Object.entries(row.sources).map(([source,item])=>`${t('billing.'+source)}: ${energyValue(item.kwh)} · ${costWithPrice(item)}`).join('\n')}`;
const gridTooltip=(row,slot)=>{
  const amounts=valid(row.grid_import_eur) ? ` (${money(row.grid_import_eur)}${row.cost_partial?' '+t('billing.known_portion'):''})` : '';
  const credit=valid(row.export_eur) ? ` (+${money(row.export_eur)})` : '';
  return `${slot.label} · ${t('usage.import')} ${energyValue(row.grid_import_kwh)}${amounts} · ${t('usage.feed_in')} ${energyValue(row.export_kwh)}${credit}`;
};

function billingChart(entry, cost=false) {
  const rows=entry?.bins ?? [];
  if (!rows.length) return `<p class="empty-state">${th('billing.no_data')}</p>`;
  const width=Math.max(280,Math.min(1000,window.innerWidth-100)),height=240,left=44,right=12,top=18,bottom=38;
  const field=cost?'cost_eur':'kwh';
  const sums=rows.map(row=>Object.values(row.sources).reduce((sum,item)=>sum+Math.max(0,item[field]),0));
  const minimum=cost?Math.min(0,...rows.map(row=>Object.values(row.sources).reduce((sum,item)=>sum+Math.min(0,item[field]),0))):0;
  const maximum=Math.max(.01,...sums),span=maximum-minimum,plot=height-top-bottom;
  const y=value=>top+(maximum-value)/span*plot;
  const slots=billingSlots(),barWidth=Math.max(1,(width-left-right)/slots.length*.7);
  const axis=Array.from({length:5},(_,i)=>{const value=minimum+span*i/4;return `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--edge)"/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${html(decimal(value,cost&&span<10?2:1))}</text>`;}).join('');
  const center=index=>left+(index+.5)*(width-left-right)/slots.length;
  const bars=slots.map((slot,index)=>{
    const row=rows.find(item=>item.time===slot.key);if(!row) return '';
    const x=center(index);
    let positive=0,negative=0;
    const shapes=Object.entries(row.sources).map(([source,item])=>{
      const value=item[field],from=value>=0?positive:negative,to=from+value;
      if(value>=0)positive=to;else negative=to;
      return `<rect x="${x-barWidth/2}" y="${Math.min(y(from),y(to))}" width="${barWidth}" height="${Math.max(0,Math.abs(y(from)-y(to)))}" fill="${sourceColors[source]}"/>`;
    }).join('');
    const tooltip=binTooltip(row,slot);
    return `<g tabindex="0" role="button" data-billing-bin="${html(slot.date)}" aria-label="${html(tooltip)}"><title>${html(tooltip)}</title>${shapes}<rect x="${x-(width-left-right)/slots.length/2}" y="${top}" width="${(width-left-right)/slots.length}" height="${plot}" fill="transparent"/></g>`;
  }).join('');
  const labels=slots.map((slot,index)=>index%Math.max(1,Math.ceil(slots.length/(window.innerWidth<600?5:10)))===0?`<text x="${left+(index+.5)*(width-left-right)/slots.length}" y="${height-12}" text-anchor="middle">${html(slot.label)}</text>`:'').join('');
  return `<svg class="billing-chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${html(t(cost?'billing.cost_chart':'billing.energy_chart'))}">${axis}${bars}${labels}</svg>`;
}

function gridChart(balance, cost=false) {
  const rows=balance?.bins ?? [];
  if (!rows.length) return `<p class="empty-state">${th('billing.no_data')}</p>`;
  const width=Math.max(280,Math.min(1000,window.innerWidth-100)),height=240,left=44,right=12,top=18,bottom=38;
  // Up: grid import (energy or its cost); down: feed-in (energy or its credit).
  const up=row=>Math.max(0,(cost?row.grid_import_eur:row.grid_import_kwh)??0),down=row=>Math.max(0,(cost?row.export_eur:row.export_kwh)??0);
  const maximum=Math.max(.01,...rows.map(up)),minimum=-Math.max(.01,...rows.map(down));
  const span=maximum-minimum,plot=height-top-bottom,y=value=>top+(maximum-value)/span*plot;
  const slots=billingSlots(),step=(width-left-right)/slots.length,barWidth=Math.max(1,step*.7);
  // A small feed-in (or import) squeezes its ticks against zero; drop ticks that would overlap.
  const apart=(a,b)=>Math.abs(y(a)-y(b))>=14;
  const ticks=[0,...[maximum,minimum].flatMap(edge=>[edge,edge/2].filter(value=>apart(value,0)&&(value===edge||apart(value,edge))))];
  const axis=ticks.map(value=>`<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--edge)"${value===0?' stroke-width="2"':''}/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${html(decimal(Math.abs(value),cost&&span<10?2:1))}</text>`).join('');
  const bars=slots.map((slot,index)=>{
    const row=rows.find(item=>item.time===slot.key);if(!row) return '';
    const x=left+(index+.5)*step;
    const tooltip=gridTooltip(row,slot);
    return `<g tabindex="0" role="button" data-billing-bin="${html(slot.date)}" aria-label="${html(tooltip)}"><title>${html(tooltip)}</title>`
      +`<rect x="${x-barWidth/2}" y="${y(up(row))}" width="${barWidth}" height="${Math.max(0,y(0)-y(up(row)))}" fill="${sourceColors.grid}"/>`
      +`<rect x="${x-barWidth/2}" y="${y(0)}" width="${barWidth}" height="${Math.max(0,y(-down(row))-y(0))}" fill="${sourceColors.pv}"/>`
      +`<rect x="${x-step/2}" y="${top}" width="${step}" height="${plot}" fill="transparent"/></g>`;
  }).join('');
  const labels=slots.map((slot,index)=>index%Math.max(1,Math.ceil(slots.length/(window.innerWidth<600?5:10)))===0?`<text x="${left+(index+.5)*step}" y="${height-12}" text-anchor="middle">${html(slot.label)}</text>`:'').join('');
  return `<svg class="billing-chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${html(t(cost?'usage.grid_cost_chart':'usage.grid_chart'))}">${axis}${bars}${labels}</svg>`;
}

function billingSlots() {
  const report=billing.data;if(!report)return [];
  const start=new Date(report.date+'T12:00:00Z'),end=new Date(report.end+'T12:00:00Z'),rows=[];
  if(billing.period==='day') {
    // Server bins carry actual UTC hours: repeated DST hours stay distinct.
    const keys=report.hours??[...new Set(Object.values(report.consumers).flatMap(item=>item.bins.map(row=>row.time)))].sort();
    return keys.map(key=>({key,date:report.date,label:new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,hour:'2-digit',minute:'2-digit',timeZoneName:'short'}).format(new Date(key))}));
  }
  for(let cursor=start;cursor<end;billing.period==='year'?cursor.setUTCMonth(cursor.getUTCMonth()+1):cursor.setUTCDate(cursor.getUTCDate()+1)){
    const date=cursor.toISOString().slice(0,10);
    rows.push({key:billing.period==='year'?date.slice(0,7):date,date,label:billing.period==='year'?new Intl.DateTimeFormat(language.locale,{month:'short',timeZone:'UTC'}).format(cursor):String(cursor.getUTCDate())});
  }
  return rows;
}

const usageUnits = {day:'hour',month:'day',year:'month'};
function binLabel(time, unit) {
  if (unit==='hour') return new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,weekday:'short',hour:'2-digit',minute:'2-digit'}).format(new Date(time));
  if (unit==='day') return new Intl.DateTimeFormat(language.locale,{timeZone:'UTC',weekday:'short',day:'numeric',month:'short'}).format(new Date(time+'T12:00:00Z'));
  return new Intl.DateTimeFormat(language.locale,{timeZone:'UTC',month:'long',year:'numeric'}).format(new Date(time+'-15T12:00:00Z'));
}
// Facts are selected by the backend; the browser only words them.
function factText(fact) {
  const time=fact.time ? binLabel(fact.time,fact.unit) : '';
  switch (fact.id) {
    case 'best': return [t('usage.fact_best_'+fact.unit),t('usage.fact_best_text',{time,share:percent(fact.percent)}),percent(fact.percent)];
    case 'max_pv': return [t('usage.fact_max_pv'),t('usage.fact_max_pv_text',{time,energy:energyValue(fact.kwh)}),energyValue(fact.kwh)];
    case 'pv_per_day': return [t('usage.fact_per_day'),t('usage.fact_pv_per_day_text',{energy:energyValue(fact.kwh)}),'Ø'];
    case 'max_grid': return [t('usage.fact_max_grid'),t('usage.fact_max_grid_text',{time,energy:energyValue(fact.kwh)}),energyValue(fact.kwh)];
    case 'charge_days': return [t('usage.fact_charge_days'),t('usage.fact_charge_days_text',{count:fact.count,days:fact.days}),t('usage.days',{count:fact.count})];
    case 'per_day': return [t('usage.fact_per_day'),`${energyValue(fact.kwh)} · ${fact.cost_available ? money(fact.eur) : '—'}`,'Ø'];
    case 'savings': return [t(fact.eur>=0 ? 'usage.fact_savings' : 'usage.fact_extra_cost'),t('usage.fact_savings_text',{self:price(fact.self_price_ct),grid:price(fact.grid_price_ct)}),(fact.eur>=0?'+':'')+money(fact.eur)];
    case 'consumer': return [billingName(fact.key),`${energyValue(fact.kwh)} · ${valid(fact.self_percent) ? t('usage.self_share',{share:percent(fact.self_percent)})+' · ' : ''}${fact.cost_available ? money(fact.cost_eur) : '—'}`,t('usage.open'),'#usage/'+fact.key];
    case 'export': return [t('usage.feed_in'),`${energyValue(fact.kwh)} · ${valid(fact.eur) ? '+'+money(fact.eur) : '—'}`,t('usage.open'),'#usage/grid'];
    case 'max_export': return [t('usage.fact_max_export'),`${time} · ${energyValue(fact.kwh)}`,valid(fact.eur) ? '+'+money(fact.eur) : '—'];
    case 'max_import': return [t('usage.fact_max_import'),`${time} · ${energyValue(fact.kwh)}`,moneyOr(fact.eur)];
    case 'grid_per_day': return [t('usage.fact_per_day'),t('usage.fact_grid_per_day_text',{feed:energyValue(fact.export_kwh),import:energyValue(fact.import_kwh)}),'Ø'];
    default: return [t('usage.fact_'+fact.id),t('usage.fact_'+fact.id+'_text'),'—'];
  }
}
const factRow = ([title,text,tag,href]) => href
  ? `<a class="row rowlink" href="${html(href)}"><span><b>${html(title)}</b><br><small>${html(text)}</small></span><span class="tag accent">${html(tag)}</span></a>`
  : `<div class="row"><span><b>${html(title)}</b><br><small>${html(text)}</small></span><span class="tag">${html(tag)}</span></div>`;

function usageFigures(key, view, amount, balance) {
  const days=view?.per_day_kwh!==undefined && valid(view?.per_day_kwh);
  const perDay=value=>days ? t('usage.per_day',{energy:energyValue(value)}) : t('billing.observed');
  if (key==='pv') {
    // Forecast only for the rest of the period; EOS plans about two days ahead.
    const forecast=billing.data?.pv_forecast,more=forecast&&!forecast.complete&&forecast.kwh>0 ? t('usage.pv_forecast_partial') : '';
    return {
      lead:balance ? t('usage.lead_pv',{energy:energyValue(balance.pv_kwh),share:percent(balance.self_consumption_percent)}) : '',
      kpis:[[t('usage.pv_produced'),energyOr(balance?.pv_kwh),perDay(balance && balance.base_days>1 && billing.period!=='day' ? balance.pv_kwh/balance.base_days : null)],
        [t('usage.self_consumption'),percent(balance?.self_consumption_percent),t('usage.self_consumption_note')],
        [t('usage.feed_in'),energyOr(balance?.export_kwh),`${feedInMoney(balance)} · ${price(balance?.feed_in_price_ct)}`],
        [t('usage.pv_forecast'),forecast ? energyValue(forecast.kwh) : '—',[t('usage.pv_forecast_note'),more].filter(Boolean).join(' ')]]};
  }
  if (key==='grid') return {
    lead:balance ? t('usage.lead_grid',{feed:energyValue(balance.export_kwh),import:energyValue(balance.grid_import_kwh),share:percent(balance.self_consumption_percent)}) : '',
    kpis:[[t('usage.feed_in'),energyOr(balance?.export_kwh),`${feedInMoney(balance)} · ${price(balance?.feed_in_price_ct)}`],
      [t('usage.import'),energyOr(balance?.grid_import_kwh),`${moneyOr(balance?.grid_import_cost_eur,balance?.cost_partial)} · ${t('billing.average_unit_price',{price:price(balance?.grid_import_price_ct)})}`],
      [t('usage.self_consumption'),percent(balance?.self_consumption_percent),t('usage.self_consumption_note')],
      [t('usage.autarky'),percent(balance?.autarky_percent),t('usage.autarky_note')]]};
  const estimated=amount?.energy_estimated ? '≈ ' : '';
  if (key==='total') return {
    lead:amount&&balance ? t('usage.lead_total',{energy:estimated+energyValue(amount.kwh),share:percent(balance.autarky_percent),net:moneyOr(balance.net_eur,balance.cost_partial)}) : '',
    kpis:[[t('billing.consumption'),amount?estimated+energyValue(amount.kwh):'—',perDay(view?.per_day_kwh)],
      [t('usage.autarky'),percent(balance?.autarky_percent),t('usage.autarky_parts',{energy:energyOr(balance?.own_kwh)})],
      [t('usage.costs_total'),moneyOr(balance?.total_cost_eur,balance?.cost_partial),t('usage.incl_base')],
      [t('usage.net'),moneyOr(balance?.net_eur,balance?.cost_partial),t('usage.net_note',{value:feedInMoney(balance)})]]};
  const car=isCarKey(key);
  return {
    lead:amount?.kwh>0 ? t('usage.lead_consumer',{energy:estimated+energyValue(amount.kwh),share:percent(view?.self_percent),cost:costValue(amount)}) : t(car?'usage.lead_no_charging':'usage.lead_none'),
    kpis:[[t(car?'usage.charged':'billing.consumption'),amount?estimated+energyValue(amount.kwh):'—',perDay(view?.per_day_kwh)],
      [t('usage.self_supply'),percent(view?.self_percent),t('usage.self_parts',{pv:energyOr(view?.pv_kwh),battery:energyOr(view?.battery_own_kwh)})],
      [t(amount?.cost_partial?'billing.known_costs':'billing.costs'),costValue(amount),averageCostLabel(amount)],
      [t('usage.savings'),moneyOr(view?.savings_eur),t('usage.savings_note')]]};
}

function priceRows(key, view, balance) {
  const row=(label,rate,value,kind='')=>`<div class="prow${kind}"><span>${html(label)}</span><span class="num dim">${html(rate)}</span><span class="num">${html(value)}</span></div>`;
  const approx=balance?.cost_partial;
  const base=()=>row(t('usage.base_price',{days:balance.base_days}),t('usage.per_month',{value:money(balance.base_price_eur_month)}),money(balance.base_eur));
  const feed=()=>row(t('usage.feed_in_credit',{energy:energyValue(balance.export_kwh)}),price(balance.feed_in_price_ct),valid(balance.feed_in_price_ct)||balance.export_kwh<=.0001 ? '−'+money(balance.export_eur) : '—');
  if (key==='pv') return balance ? feed() : '';
  if (key==='grid') {
    if (!balance) return '';
    return `<p class="ph">${th('usage.grid_price',{price:price(balance.grid_import_price_ct)})}</p>`
      +row(t('usage.grid_import',{energy:energyValue(balance.grid_import_kwh)}),price(balance.grid_import_price_ct),moneyOr(balance.grid_import_cost_eur,approx))
      +base()+feed()+row(t('usage.grid_balance'),'',moneyOr(balance.grid_balance_eur,approx),' sum')
      +(balance.storage_grid_kwh>.0001 ? `<p class="footnote">${th('usage.price_note_grid',{energy:energyValue(balance.storage_grid_kwh)})}</p>` : '');
  }
  if (!view) return '';
  let result=`<p class="ph">${th('usage.grid_price',{price:price(view.grid_price_ct)})}</p>`
    +row(t('usage.grid_import',{energy:energyValue(view.grid_kwh)}),price(view.grid_price_ct),moneyOr(view.grid_cost_eur,view.cost_partial));
  if (key==='total' && balance) result+=base();
  // Own power is split by origin; grid-charged storage is listed apart instead of as own power.
  const origin=view.self_origin;
  if (origin) {
    for (const part of ['pv_direct','battery_pv','battery_grid','battery_unknown']) {
      const item=origin[part];
      if (!item || (part!=='pv_direct' && !(item.kwh>.0001))) continue;
      result+=row(t('usage.self_'+part,{energy:energyValue(item.kwh)}),price(item.price_ct),moneyOr(item.cost_eur,view.cost_partial));
    }
  } else result+=row(t('usage.self_power',{energy:energyValue(view.self_kwh)}),price(view.self_price_ct),moneyOr(view.self_cost_eur,view.cost_partial));
  if (view.unknown_kwh>.0001) result+=row(t('usage.unknown_origin',{energy:energyValue(view.unknown_kwh)}),'','—');
  if (key==='total' && balance) result+=feed()+row(t('usage.net'),'',moneyOr(balance.net_eur,approx),' sum');
  else result+=row(t('billing.costs'),'',view.cost_available ? moneyOr(view.cost_eur,view.cost_partial) : '—',' sum');
  return result+`<p class="footnote">${th('usage.price_note')}${key==='total' ? '' : ' '+th('usage.base_note')}</p>`;
}

function mixRows(key, amount, balance) {
  const item=(label,color,kwh,share,detail='')=>`<div class="row"><span><i class="source-dot" style="background:${color}"></i>${html(label)}${detail ? `<br><small>${html(detail)}</small>` : ''}</span><span class="num">${html(energyValue(kwh))} · ${valid(share) ? decimal(share) : '—'} %</span></div>`;
  if (key==='pv') {
    const flow=balance?.pv_flow;
    if (!flow) return {title:t('usage.mix_pv_title'),total:'—',html:''};
    const total=Object.values(flow).reduce((sum,value)=>sum+value,0),share=value=>total>0 ? value/total*100 : null;
    const bar=`<div class="source-bar" aria-hidden="true">${pvFlows.map(([name,color])=>`<span style="width:${share(flow[name])??0}%;background:${color}"></span>`).join('')}</div>`;
    return {title:t('usage.mix_pv_title'),total:energyValue(balance.pv_kwh),
      html:bar+`<div class="list">${pvFlows.map(([name,color])=>item(t('usage.pv_to_'+name),color,flow[name],share(flow[name]))).join('')}</div>`};
  }
  if (key==='grid') {
    const use=balance?.pv_use;
    if (!use) return {title:t('usage.mix_pv_title'),total:'—',html:''};
    const parts=[['direct','#5ab0e8'],['storage',sourceColors.battery],['export',sourceColors.pv]];
    const bar=`<div class="source-bar" aria-hidden="true">${parts.map(([part,color])=>`<span style="width:${use[part].share_percent??0}%;background:${color}"></span>`).join('')}</div>`;
    return {title:t('usage.mix_pv_title'),total:energyValue(balance.pv_kwh),
      html:bar+`<div class="list">${parts.map(([part,color])=>item(t('usage.pv_'+part),color,use[part].kwh,use[part].share_percent)).join('')}</div>`};
  }
  if (!amount) return {title:t('usage.mix_title'),total:'—',html:''};
  const rows=Object.entries(amount.sources).filter(([source,value])=>source!=='unknown'||value.kwh>.0001)
    .map(([source,value])=>item(t('usage.from_'+source),sourceColors[source],value.kwh,value.share_percent,costWithPrice(value))).join('');
  return {title:t('usage.mix_title'),total:energyValue(amount.kwh),html:sourceBar(amount)+`<div class="list">${rows}</div>`};
}

function usageDetail(key, fetch=true) {
  if(fetch)void fetchBilling();
  const data=billing.data,entry=key==='total'?data?.total:key==='grid'||key==='pv'?null:data?.consumers[key],amount=entry?.total;
  const view=data?.views?.[key],balance=data?.balance,period=billing.period,today=localDay(windowNow());
  const range=data?new Intl.DateTimeFormat(language.locale,{timeZone:'UTC',...(period==='day'?{dateStyle:'long'}:period==='month'?{year:'numeric',month:'long'}:{year:'numeric'})}).format(new Date(data.date+'T12:00:00Z')):'';
  byId('usage-nav').innerHTML=usageKeys().map(item=>`<a href="#usage/${html(item)}"${item===key?' aria-current="page"':''}>${html(item==='total'?t('billing.total'):item==='grid'?t('usage.grid_nav'):billingName(item))}</a>`).join('');
  // On narrow screens the chips scroll sideways; keep the current report visible.
  const nav=byId('usage-nav'),active=nav.querySelector?.('[aria-current]');
  if (active?.offsetWidth && nav.scrollWidth>nav.clientWidth) nav.scrollLeft=active.offsetLeft-nav.offsetLeft-(nav.clientWidth-active.offsetWidth)/2;
  byId('usage-back').href=isCarKey(key)?'#car':'#overview';
  const device=key.startsWith('car/') ? key : ['house','heat','grid','car'].includes(key) ? key : null;
  byId('usage-device').hidden=!device;
  if (device) byId('usage-device').href='#'+device;
  byId('usage-title').textContent=key==='total'?t('usage.total_title'):billingName(key);
  byId('usage-eyebrow').textContent=t(key==='grid'?'usage.eyebrow_grid':key==='pv'?'usage.eyebrow_pv':key==='total'?'usage.eyebrow_total':'usage.eyebrow_consumer')+(range?' · '+range:'');
  byId('usage-period').querySelectorAll('[data-billing-period]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.billingPeriod===period)));
  byId('billing-range').textContent=range;
  const current=!data || data.end>today;
  byId('usage').querySelector('[data-billing-move="1"]').disabled=current;
  byId('usage').querySelector('[data-billing-move="now"]').hidden=current;
  byId('billing-message').textContent=billing.error??(billing.loading?t('billing.loading'):'');
  const figures=usageFigures(key,view,amount,balance);
  byId('usage-lead').textContent=figures.lead;
  byId('usage-kpis').innerHTML=cards(figures.kpis);
  // Day view: power profile (kW), hourly energy (kWh) or hourly costs (€); month and year: kWh or €.
  // PV production has no euro view; its value appears as feed-in credit and in the consumers' costs.
  const unit=billing.unit==='kw'&&period!=='day' || billing.unit==='eur'&&key==='pv' ? 'kwh' : billing.unit;
  const cost=unit==='eur',profile=unit==='kw' ? profilePoints(key) : null;
  byId('usage-chart-unit').querySelectorAll('[data-chart-unit]').forEach(button=>{
    button.setAttribute('aria-pressed',String(button.dataset.chartUnit===unit));
    if(button.dataset.chartUnit==='kw')button.hidden=period!=='day';
    if(button.dataset.chartUnit==='eur')button.hidden=key==='pv';
  });
  byId('usage-unit').textContent=profile ? t('usage.unit_power') : t((cost?'usage.unit_eur_':'usage.unit_')+usageUnits[period]);
  const item=(name,color)=>`<span><i style="${color?'background:'+color:'border:1px dashed '+sourceColors.pv}"></i>${th(name)}</span>`;
  const present=(values,names)=>names.filter(([name])=>(values?.[name]??0)>.005);
  const pvLegend=`<span class="legend-group">${th('usage.pv_legend_flows')}</span>`+present(balance?.pv_flow,pvFlows).map(([name,color])=>item('usage.pv_to_'+name,color)).join('')
    +(present(balance?.pv_gap,pvGaps).length?`<span class="legend-group">${th('usage.pv_legend_gaps')}</span>`:'')+present(balance?.pv_gap,pvGaps).map(([name,color])=>item('usage.pv_gap_'+name,color)).join('')
    +item('usage.pv_forecast',null);
  byId('usage-legend').innerHTML=key==='pv' ? pvLegend : (key==='grid' ? [['↑','import',sourceColors.grid],['↓','feed_in',sourceColors.pv]].map(([arrow,name,color])=>`<span><i style="background:${color}"></i>${arrow} ${th('usage.'+name)}</span>`)
    : Object.entries(sourceColors).filter(([source])=>source!=='unknown'||amount?.sources?.unknown?.kwh>.0001).map(([source,color])=>`<span><i style="background:${color}"></i>${th('billing.'+source)}</span>`)).join('');
  byId('usage-charts').innerHTML=profile ? powerChart(key,profile,entry,balance,data?.pv_forecast) : key==='pv' ? pvChart(balance,data?.pv_forecast) : key==='grid' ? gridChart(balance,cost) : billingChart(entry,cost);
  const svg=byId('usage-charts').querySelector?.('svg.power-chart');
  if(svg&&powerPointer!==null)showPowerReadout({target:svg,clientX:powerPointer});
  // Older days have no minute values left; their kW view shows hourly energy instead.
  byId('usage-bin').textContent=t(period==='day' ? 'usage.bin_hint' : 'usage.bin_drill')+(unit==='kw'&&!profile&&data ? ' '+t('usage.profile_hourly') : '');
  byId('usage-price-tag').textContent=price(key==='grid' ? balance?.grid_import_price_ct : view?.grid_price_ct);
  byId('usage-prices').innerHTML=priceRows(key,view,balance);
  const mix=mixRows(key,amount,balance);
  byId('usage-mix-title').textContent=mix.title;
  byId('usage-mix-total').textContent=mix.total;
  byId('usage-table').innerHTML=mix.html+(key==='car'&&snapshot.vehicles?.length>1 ? `<div class="billing-links">${snapshot.vehicles.map(item=>`<a href="#usage/car/${html(item.id)}">${html(item.name)} →</a>`).join('')}</div>` : '');
  byId('usage-facts').innerHTML=(view?.facts ?? []).map(fact=>factRow(factText(fact))).join('') || `<p class="footnote">${th(billing.loading ? 'billing.loading' : 'billing.no_data')}</p>`;
  byId('billing-quality').textContent=(data?.historical_error?t('billing.history_error')+' ':'')+(data?.reconstructed?t('billing.reconstructed')+' ':'')+t('billing.method')+' '+t('billing.partial')+' '+estimatedAverageNote(amount)+' '+(data?.started?`${t('billing.recording_since')} ${time(data.started)}.`:'');
}

function initializeBilling() {
  window.addEventListener('resize',()=>{if(route.startsWith('usage/'))usageDetail(route.slice(6),false);});
  // Values at the pointer in the power chart, for mouse and touch alike.
  for(const type of ['pointermove','pointerdown'])byId('usage-charts').addEventListener(type,showPowerReadout);
  byId('usage-charts').addEventListener('pointerleave',hidePowerReadout);
  // On narrow screens the detail sections start collapsed.
  if (typeof document!=='undefined' && window.matchMedia?.('(max-width:640px)').matches) document.querySelectorAll('#usage details.acc').forEach(item=>{item.open=false;});
  byId('usage').addEventListener('click',event=>{
    const choice=event.target.closest('[data-billing-period]');
    if(choice){if(selectBillingPeriod(choice.dataset.billingPeriod))void fetchBilling(true);return;}
    // Switching kWh/€ only redraws; the report already carries both.
    const unit=event.target.closest('[data-chart-unit]');
    if(unit){if(selectBillingUnit(unit.dataset.chartUnit)&&route.startsWith('usage/'))usageDetail(route.slice(6),false);return;}
    const navigation=event.target.closest('[data-billing-move]'),bin=event.target.closest('[data-billing-bin]');
    if(bin&&billing.period!=='day'){billing.date=bin.dataset.billingBin;selectBillingPeriod(billing.period==='year'?'month':'day');void fetchBilling(true);return;}
    if(bin){
      bin.closest('svg')?.querySelectorAll('[data-billing-bin]').forEach(item=>item.setAttribute('aria-pressed',String(item===bin)));
      byId('usage-bin').textContent=bin.getAttribute('aria-label');
      return;
    }
    if(!navigation)return;
    const move=navigation.dataset.billingMove;
    if(move==='now')billing.date=localDay(windowNow());
    else {
      const date=new Date((billing.date??localDay(windowNow()))+'T12:00:00Z'),amount=Number(move);
      if(billing.period==='day')date.setUTCDate(date.getUTCDate()+amount);
      else if(billing.period==='month'){date.setUTCDate(1);date.setUTCMonth(date.getUTCMonth()+amount);}
      else {date.setUTCMonth(0,1);date.setUTCFullYear(date.getUTCFullYear()+amount);}
      billing.date=date.toISOString().slice(0,10);
    }
    void fetchBilling(true);
  });
  byId('usage').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.matches('[data-billing-bin]')){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
  const form=byId('cost-settings');
  form.elements.pv_price_source.addEventListener('change',()=>{form.elements.pv_price_ct.disabled=form.elements.pv_price_source.value==='eos';});
}

/* Cost settings belong to the shared settings save bar; loading fills the form from the backend. */
async function loadCostSettings() {
  const form=byId('cost-settings');
  const data=await api('accounting',{period:'day'});
  for(const [key,value] of Object.entries(data.settings))if(form.elements[key])form.elements[key].value=value??'';
  form.elements.capacity_wh.disabled=snapshot.battery_group?.battery_count>1;
  if(form.elements.capacity_wh.disabled)form.elements.capacity_wh.value=snapshot.battery_group.capacity_wh;
  form.elements.pv_price_source.value=data.settings.pv_price_source??'eos';
  form.elements.pv_price_ct.disabled=form.elements.pv_price_source.value==='eos';
  if(form.elements.pv_price_ct.disabled)form.elements.pv_price_ct.value=valid(data.pv_price_ct)?Number(data.pv_price_ct.toFixed(6)):'';
  byId('pv-cost-effective').textContent=t('billing.pv_effective')+': '+(valid(data.pv_price_ct)?price(data.pv_price_ct):t('billing.pv_missing'));
  byId('cost-effective').textContent=data.effective?`${t('billing.effective')}: ${percent(data.effective.charge_efficiency*100)} / ${percent(data.effective.discharge_efficiency*100)} · ${energyValue(data.effective.capacity_wh/1000)}`:t('billing.efficiency_missing');
  byId('cost-saved').textContent='';
}
function costSettingsValues() {
  const form=byId('cost-settings'),settings={};
  for(const key of ['pv_price_ct','charge_efficiency','discharge_efficiency','capacity_wh','base_price_eur_month'])settings[key]=Number(form.elements[key].value);
  settings.pv_price_source=form.elements.pv_price_source.value;
  settings.efficiency_source=form.elements.efficiency_source.value;
  settings.initial_price_ct=form.elements.initial_price_ct.value===''?null:Number(form.elements.initial_price_ct.value);
  return settings;
}
async function saveCostSettings() {
  await api('accounting',{settings:costSettingsValues()});
  billing.at=0;
}
