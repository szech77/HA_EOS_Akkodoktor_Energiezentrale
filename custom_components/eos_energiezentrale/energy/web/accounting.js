/* Consumption reports use measured ledger data, never display-held power. */
let dayAccounting=null;
const billing = {period:'month',date:null,data:null,key:null,loading:false,at:0,error:null};
const sourceColors = {pv:'#f2c94c',battery:'#55c7cb',grid:'#5794f2',unknown:'#8995a5'};
const money = value => {
  const tiny = value !== 0 && Math.abs(value) < .0001;
  const format = new Intl.NumberFormat(language.locale,{style:'currency',currency:'EUR',
    minimumFractionDigits:2, maximumFractionDigits:value !== 0 && Math.abs(value)<.01 ? 4 : 2});
  return tiny ? (value>0 ? '< ' : '> ')+format.format(Math.sign(value)*.0001) : format.format(value);
};
const energyValue = value => `${decimal(value,2)} kWh`;
const costValue = amount => amount && !(amount.kwh>.0001 && amount.cost_unknown_kwh>=amount.kwh-.0001) ? `${amount.cost_unknown_kwh > .0001 ? '≈ ' : ''}${money(amount.cost_eur)}${amount.cost_unknown_kwh > .0001 ? ' ('+t('billing.known_portion')+')' : ''}` : '—';
const averageCost = amount => amount?.kwh>0 && amount.cost_unknown_kwh<.0001 ? price(amount.cost_eur/amount.kwh*100) : '—';
const billingName = key => key.startsWith('car/') ? snapshot.vehicles?.find(item=>item.id===key.slice(4))?.name ?? t('device.car') : t(`device.${key}`);

function dayBalance() {
  const report=snapshot.accounting, target=byId('day-balance');
  if (!report) {target.innerHTML='';return;}
  const items=['house',...(consumerEnabled('heat')?['heat']:[]),...(consumerEnabled('car')?['car']:[])];
  const totalFor=key=>{
    const live=report.consumers[key]?.total,old=dayAccounting?.date===report.date?dayAccounting.historical_consumers?.[key]:null;
    if(!old)return live;
    const result=structuredClone(live??old);
    if(live){for(const field of ['kwh','cost_eur','cost_unknown_kwh','seconds'])result[field]+=old[field];for(const source of Object.keys(result.sources))for(const field of ['kwh','cost_eur','cost_unknown_kwh'])result.sources[source][field]+=old.sources[source][field];}
    return result;
  };
  const amounts=items.map(totalFor).filter(Boolean);
  const kwh=amounts.reduce((sum,item)=>sum+item.kwh,0),cost=amounts.reduce((sum,item)=>sum+item.cost_eur,0);
  const unknown=amounts.reduce((sum,item)=>sum+item.cost_unknown_kwh,0);
  target.innerHTML=`<div class="panel-heading"><h2>${th('billing.today')}</h2><span>${th('billing.total')}: ${html(energyValue(kwh))} · ${html(costValue({kwh,cost_eur:cost,cost_unknown_kwh:unknown}))}</span></div>
    <div class="balance-grid">${items.map(key=>{
      const value=totalFor(key);
      return `<a class="balance-card" href="#usage/${key}"><span>${html(billingName(key))}</span><strong>${html(value?energyValue(value.kwh):'—')}</strong><span>${html(costValue(value))}</span>${sourceBar(value)}<small>${value?.kwh>0?Object.entries(value.sources).filter(([,item])=>item.kwh>.0001).map(([source,item])=>`${th("billing."+source)} ${decimal(item.kwh/value.kwh*100)} %`).join(" · "):""}</small><small>${th('billing.observed')}</small></a>`;
    }).join('')}</div><p class="footnote">${th('billing.partial')} ${unknown>.0001?th('billing.unknown_cost'):''}</p>`;
}

function sourceBar(value) {
  if (!value || value.kwh<=0) return '<div class="source-bar empty"></div>';
  return `<div class="source-bar" role="img" aria-label="${html(Object.entries(value.sources).map(([key,item])=>`${t('billing.'+key)} ${decimal(item.kwh/value.kwh*100)} %`).join(', '))}">${Object.entries(value.sources).map(([key,item])=>`<span style="width:${item.kwh/value.kwh*100}%;background:${sourceColors[key]}" title="${html(t('billing.'+key))}: ${decimal(item.kwh/value.kwh*100)} %"></span>`).join('')}</div>`;
}

function billingRoute(requested) {
  if (!requested.startsWith('usage/')) return false;
  const key=requested.slice(6);
  return ['house','heat','car'].includes(key) ? consumerEnabled(key) : key.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===key.slice(4));
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
  const axis=Array.from({length:5},(_,i)=>{const value=minimum+span*i/4;return `<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--edge)"/><text x="${left-8}" y="${y(value)+4}" text-anchor="end">${html(decimal(value,1))}</text>`;}).join('');
  const bars=slots.map((slot,index)=>{
    const row=rows.find(item=>item.time===slot.key);if(!row) return '';
    const x=left+(index+.5)*(width-left-right)/slots.length;
    let positive=0,negative=0;
    const shapes=Object.entries(row.sources).map(([source,item])=>{
      const value=item[field],from=value>=0?positive:negative,to=from+value;
      if(value>=0)positive=to;else negative=to;
      return `<rect x="${x-barWidth/2}" y="${Math.min(y(from),y(to))}" width="${barWidth}" height="${Math.max(0,Math.abs(y(from)-y(to)))}" fill="${sourceColors[source]}"/>`;
    }).join('');
    const tooltip=`${slot.label} · ${energyValue(row.kwh)} · ${costValue(row)}\n${Object.entries(row.sources).map(([source,item])=>`${t('billing.'+source)}: ${energyValue(item.kwh)} · ${costValue(item)}`).join('\n')}`;
    return `<g tabindex="0" role="button" data-billing-bin="${html(slot.date)}" aria-label="${html(tooltip)}"><title>${html(tooltip)}</title>${shapes}<rect x="${x-(width-left-right)/slots.length/2}" y="${top}" width="${(width-left-right)/slots.length}" height="${plot}" fill="transparent"/></g>`;
  }).join('');
  const labels=slots.map((slot,index)=>index%Math.max(1,Math.ceil(slots.length/(window.innerWidth<600?5:10)))===0?`<text x="${left+(index+.5)*(width-left-right)/slots.length}" y="${height-12}" text-anchor="middle">${html(slot.label)}</text>`:'').join('');
  return `<svg class="billing-chart" viewBox="0 0 ${width} ${height}" role="group" aria-label="${html(t(cost?'billing.cost_chart':'billing.energy_chart'))}">${axis}${bars}${labels}</svg>`;
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

function usageDetail(key, fetch=true) {
  if(fetch)void fetchBilling();
  const data=billing.data,entry=data?.consumers[key],amount=entry?.total;
  byId('usage-title').textContent=billingName(key)+' · '+t('billing.title');
  byId('usage-back').href='#'+key;
  byId('billing-period').value=billing.period;
  byId('billing-range').textContent=data?new Intl.DateTimeFormat(language.locale,{timeZone:'UTC',...(billing.period==='day'?{dateStyle:'long'}:billing.period==='month'?{year:'numeric',month:'long'}:{year:'numeric'})}).format(new Date(data.date+'T12:00:00Z')):'';
  byId('billing-date').value=billing.date??localDay(windowNow());
  byId('billing-message').textContent=billing.error??(billing.loading?t('billing.loading'):'');
  byId('usage-kpis').innerHTML=cards([
    [t('billing.consumption'),amount?energyValue(amount.kwh):'—',t('billing.observed')],
    [t(amount?.cost_unknown_kwh>.0001?'billing.known_costs':'billing.costs'),costValue(amount),amount?.cost_unknown_kwh>.0001?t('billing.missing_costs_for',{energy:energyValue(amount.cost_unknown_kwh)}):t('billing.variable')],
    [t('billing.pv_share'),amount?.kwh>0?percent(amount.sources.pv.kwh/amount.kwh*100):'—',t('billing.direct_pv')],
    [t('billing.average'),averageCost(amount),t('billing.variable')]]);
  const legend=Object.entries(sourceColors).map(([key,color])=>`<span><i style="background:${color}"></i>${th('billing.'+key)}</span>`).join('');
  byId('usage-charts').innerHTML=`<section class="chart-panel"><h2>${th('billing.energy_chart')} · kWh</h2><div class="series-legend">${legend}</div>${billingChart(entry)}</section><section class="chart-panel"><h2>${th('billing.cost_chart')} · €</h2>${billingChart(entry,true)}</section>`;
  byId('usage-table').innerHTML=amount?`<div class="table-scroll"><table><thead><tr><th>${th('billing.source')}</th><th>kWh</th><th>€</th><th>ct/kWh</th><th>%</th></tr></thead><tbody>${Object.entries(amount.sources).map(([key,item])=>`<tr><td><i class="source-dot" style="background:${sourceColors[key]}"></i>${th('billing.'+key)}</td><td>${decimal(item.kwh,2)}</td><td>${html(costValue(item))}</td><td>${html(averageCost(item))}</td><td>${amount.kwh>0?decimal(item.kwh/amount.kwh*100):'—'}</td></tr>`).join('')}</tbody></table></div><p>${th('billing.observed')}: ${decimal(amount.seconds/3600,1)} h · ${th('billing.unknown_cost_energy')}: ${energyValue(amount.cost_unknown_kwh)}</p>`:'';
  byId('billing-quality').textContent=(data?.historical_error?t('billing.history_error')+' ':'')+(data?.reconstructed?t('billing.reconstructed')+' ':'')+t('billing.method')+' '+t('billing.partial')+' '+(data?.started?`${t('billing.recording_since')} ${time(data.started)}.`:'');
  if(key==='car'&&snapshot.vehicles?.length)byId('usage-table').innerHTML+=`<div class="billing-links">${snapshot.vehicles.map(item=>`<a href="#usage/car/${html(item.id)}">${html(item.name)} →</a>`).join('')}</div>`;
}

function initializeBilling() {
  byId('billing-period').addEventListener('change',event=>{billing.period=event.target.value;void fetchBilling(true);});
  byId('billing-date').addEventListener('change',event=>{if(event.target.value){billing.date=event.target.value;void fetchBilling(true);}});
  window.addEventListener('resize',()=>{if(route.startsWith('usage/'))usageDetail(route.slice(6),false);});
  byId('usage').addEventListener('click',event=>{
    const navigation=event.target.closest('[data-billing-move]'),bin=event.target.closest('[data-billing-bin]');
    if(bin&&billing.period!=='day'){billing.date=bin.dataset.billingBin;billing.period=billing.period==='year'?'month':'day';void fetchBilling(true);return;}
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
  let loaded=false;
  byId('cost-settings-open').addEventListener('toggle',async event=>{
    if(!event.target.open||loaded)return;
    try {
      const data=await api('accounting',{period:'day'});
      for(const [key,value] of Object.entries(data.settings))if(form.elements[key])form.elements[key].value=value??'';
      form.elements.pv_price_source.value=data.settings.pv_price_source??'eos';
      form.elements.pv_price_ct.disabled=form.elements.pv_price_source.value==='eos';
      if(form.elements.pv_price_ct.disabled)form.elements.pv_price_ct.value=valid(data.pv_price_ct)?Number(data.pv_price_ct.toFixed(6)):'';
      byId('pv-cost-effective').textContent=t('billing.pv_effective')+': '+(valid(data.pv_price_ct)?price(data.pv_price_ct):t('billing.pv_missing'));
      byId('cost-effective').textContent=data.effective?`${t('billing.effective')}: ${percent(data.effective.charge_efficiency*100)} / ${percent(data.effective.discharge_efficiency*100)} · ${energyValue(data.effective.capacity_wh/1000)}`:t('billing.efficiency_missing');
      loaded=true;
    } catch(error){byId('cost-saved').textContent=error.message;}
  });
  form.elements.pv_price_source.addEventListener('change',()=>{form.elements.pv_price_ct.disabled=form.elements.pv_price_source.value==='eos';});
  form.addEventListener('submit',async event=>{
    event.preventDefault();const settings={};
    for(const key of ['pv_price_ct','charge_efficiency','discharge_efficiency','capacity_wh'])settings[key]=Number(form.elements[key].value);
    settings.pv_price_source=form.elements.pv_price_source.value;
    settings.efficiency_source=form.elements.efficiency_source.value;
    settings.initial_price_ct=form.elements.initial_price_ct.value===''?null:Number(form.elements.initial_price_ct.value);
    try{await api('accounting',{settings});byId('cost-saved').textContent=t('settings.saved');loaded=false;billing.at=0;await refresh();}
    catch(error){byId('cost-saved').textContent=error.message;}
  });
}
