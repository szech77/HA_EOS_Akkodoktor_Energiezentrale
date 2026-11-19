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
// The report charts show energy (kWh) or money (€); the choice is a per-viewer convenience.
const billingUnits = ['kwh','eur'];
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
const billingName = key => key==='total' ? t('billing.total_consumption') : key==='grid' ? t('usage.grid_title') : key.startsWith('car/') ? snapshot.vehicles?.find(item=>item.id===key.slice(4))?.name ?? t('device.car') : t(`device.${key}`);
const isCarKey = key => key==='car' || key.startsWith('car/');
const usageEnabled = key => key==='house' || (typeof consumerEnabled==='function' && consumerEnabled(key));
// Report pages in the order of the sub navigation; single vehicles stay on the car page.
function usageKeys() {
  const cars=usageEnabled('car') ? ['car',...(snapshot.vehicles?.length>1 ? snapshot.vehicles.map(item=>'car/'+item.id) : [])] : [];
  return ['house',...cars,...(usageEnabled('heat') ? ['heat'] : []),'grid','total'];
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
  return key==='total' || key==='grid' || (['house','heat','car'].includes(key) ? usageEnabled(key) : key.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===key.slice(4)));
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
  const bars=slots.map((slot,index)=>{
    const row=rows.find(item=>item.time===slot.key);if(!row) return '';
    const x=left+(index+.5)*(width-left-right)/slots.length;
    let positive=0,negative=0;
    const shapes=Object.entries(row.sources).map(([source,item])=>{
      const value=item[field],from=value>=0?positive:negative,to=from+value;
      if(value>=0)positive=to;else negative=to;
      return `<rect x="${x-barWidth/2}" y="${Math.min(y(from),y(to))}" width="${barWidth}" height="${Math.max(0,Math.abs(y(from)-y(to)))}" fill="${sourceColors[source]}"/>`;
    }).join('');
    const tooltip=`${slot.label} · ${energyValue(row.kwh)} · ${costWithPrice(row)}\n${Object.entries(row.sources).map(([source,item])=>`${t('billing.'+source)}: ${energyValue(item.kwh)} · ${costWithPrice(item)}`).join('\n')}`;
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
    const amounts=valid(row.grid_import_eur) ? ` (${money(row.grid_import_eur)}${row.cost_partial?' '+t('billing.known_portion'):''})` : '';
    const credit=valid(row.export_eur) ? ` (+${money(row.export_eur)})` : '';
    const tooltip=`${slot.label} · ${t('usage.import')} ${energyValue(row.grid_import_kwh)}${amounts} · ${t('usage.feed_in')} ${energyValue(row.export_kwh)}${credit}`;
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
  const data=billing.data,entry=key==='total'?data?.total:key==='grid'?null:data?.consumers[key],amount=entry?.total;
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
  byId('usage-eyebrow').textContent=t(key==='grid'?'usage.eyebrow_grid':key==='total'?'usage.eyebrow_total':'usage.eyebrow_consumer')+(range?' · '+range:'');
  byId('usage-period').querySelectorAll('[data-billing-period]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.billingPeriod===period)));
  byId('billing-range').textContent=range;
  const current=!data || data.end>today;
  byId('usage').querySelector('[data-billing-move="1"]').disabled=current;
  byId('usage').querySelector('[data-billing-move="now"]').hidden=current;
  byId('billing-message').textContent=billing.error??(billing.loading?t('billing.loading'):'');
  const figures=usageFigures(key,view,amount,balance);
  byId('usage-lead').textContent=figures.lead;
  byId('usage-kpis').innerHTML=cards(figures.kpis);
  const cost=billing.unit==='eur';
  byId('usage-chart-unit').querySelectorAll('[data-chart-unit]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.chartUnit===billing.unit)));
  byId('usage-unit').textContent=t((cost?'usage.unit_eur_':'usage.unit_')+usageUnits[period]);
  byId('usage-legend').innerHTML=(key==='grid' ? [['↑','import',sourceColors.grid],['↓','feed_in',sourceColors.pv]].map(([arrow,name,color])=>`<span><i style="background:${color}"></i>${arrow} ${th('usage.'+name)}</span>`)
    : Object.entries(sourceColors).filter(([source])=>source!=='unknown'||amount?.sources?.unknown?.kwh>.0001).map(([source,color])=>`<span><i style="background:${color}"></i>${th('billing.'+source)}</span>`)).join('');
  byId('usage-charts').innerHTML=key==='grid' ? gridChart(balance,cost) : billingChart(entry,cost);
  byId('usage-bin').textContent=t(period==='day' ? 'usage.bin_hint' : 'usage.bin_drill');
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
