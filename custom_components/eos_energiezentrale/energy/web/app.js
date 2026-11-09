'use strict';

const byId = id => document.getElementById(id);
const html = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
let language = {locale:'en-GB', messages:{}};
const t = (key, values = {}) => {
  const context = {vehicle:snapshot.vehicle_name ?? 'E-Auto', ...values};
  return (language.messages[key] ?? key)
    .replace(/\{(\w+)\}/g, (token, name) => Object.hasOwn(context, name) ? String(context[name]) : token);
};
const th = (key, values) => html(t(key, values));
const stateLabel = (prefix, value) => value ? language.messages[`${prefix}.${value}`] ?? value : '';
const valid = Number.isFinite;
const decimal = (value, digits = 1) => new Intl.NumberFormat(language.locale, {maximumFractionDigits: digits}).format(value);
const power = value => valid(value) ? `${decimal(Math.abs(value) / 1000, 2)} ${t('unit.kw')}` : '—';
const percent = value => valid(value) ? `${decimal(value)} %` : '—';
const price = value => valid(value) ? `${decimal(value)} ${t('unit.price')}` : '—';
const time = value => value ? new Intl.DateTimeFormat(language.locale, {timeZone: snapshot.zone, dateStyle:'short', timeStyle:'short'}).format(new Date(value)) : '—';
const modes = {
  IDLE:['mode.idle','grid'], NON_EXPORT:['mode.pv','battery'], SELF_CONSUMPTION:['mode.own','house'],
  FORCED_CHARGE:['mode.grid','car'], GRID_SUPPORT_IMPORT:['mode.grid','car'],
  FORCED_DISCHARGE:['mode.discharge','heat'], GRID_SUPPORT_EXPORT:['mode.discharge','heat'],
  PEAK_SHAVING:['mode.peak','solar'], CHARGING:['mode.charging','car'], DISCONNECTED:['mode.disconnected','edge']
};
const modeLabel = mode => Object.hasOwn(modes, mode) ? t(modes[mode][0]) : mode ?? '—';
const pages = new Set(['solar','grid','battery','house','car','heat','energy']);
const day = 86_400_000;
let snapshot = {live:{}, settings:{}, errors:{}, plan:{}, forecast:[], zone:'Europe/Berlin'};
let history = {local:[], influx:[]};
let route = 'overview';
let formReady = false;
let refreshing = false;
let historyRefreshing = false;

let requestId = 0;
const pendingRequests = new Map();
window.addEventListener('message', event => {
  if (event.source !== window.parent || event.origin !== location.origin
      || event.data?.channel !== 'eos-energy-response') return;
  const pending = pendingRequests.get(event.data.id);
  if (!pending) return;
  clearTimeout(pending.timer);
  pendingRequests.delete(event.data.id);
  if (event.data.error) pending.reject(Error(language.messages[`error.${event.data.error}`] ?? t('error.request')));
  else pending.resolve(event.data.result);
});
async function api(path, body) {
  if (window.parent === window) throw Error('Open this panel from Home Assistant');
  const id = ++requestId;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pendingRequests.delete(id); reject(Error('Home Assistant timeout')); }, 30000);
    pendingRequests.set(id, {resolve, reject, timer});
    window.parent.postMessage({channel:'eos-energy-request', id, action:path.split('?')[0], values:body ?? {}}, location.origin);
  });
}

function cards(values) {
  return values.map(([title,value,context]) =>
    `<div><small>${html(title)}</small><strong>${html(value)}</strong><small>${html(context)}</small></div>`).join('');
}

function windowNow() {
  return Date.parse(snapshot.live.time) || Date.now();
}

function actualPoints(key) {
  const influx = history.influx.filter(row => valid(row[key]));
  const local = history.local.filter(row => valid(row[key]));
  const first = Date.parse(local[0]?.time ?? '');
  return [...influx.filter(row => !first || Date.parse(row.time) < first), ...local];
}

function nextPlan(key) {
  const now = windowNow();
  const current = snapshot.live[key + '_mode'];
  return (snapshot.plan[key] ?? []).find(item => Date.parse(item.time) > now && item.mode !== current);
}

const localDay = value => new Intl.DateTimeFormat('sv-SE', {timeZone:snapshot.zone}).format(new Date(value));

function solarRemaining() {
  const now = windowNow();
  const today = localDay(now);
  let wh = 0, covered = false;
  for (const row of snapshot.forecast) {
    const from = Math.max(now, Date.parse(row.time));
    const end = Date.parse(row.end);
    if (valid(row.solar) && end > from && localDay(from) === today) {
      // EOS slots are expected to end on a local planning boundary.
      if (localDay(end - 1) !== today) continue;
      wh += row.solar * (end - from) / 3600000;
      covered = true;
    }
  }
  return covered ? `${decimal(wh / 1000)} ${t('unit.kwh')}` : null;
}

function solarTodayEnergy() {
  const now = windowNow();
  const date = localDay(now);
  const points = actualPoints('solar').filter(row => localDay(row.time) === date);
  let wh = 0, covered = 0;
  for (let i = 1; i < points.length; i++) {
    const duration = Date.parse(points[i].time) - Date.parse(points[i - 1].time);
    if (duration > 0 && duration <= 360000) {
      wh += (points[i].solar + points[i - 1].solar) / 2 * duration / 3600000;
      covered += duration;
    }
  }
  return covered ? wh / 1000 : null;
}

function solarToday() {
  const energy=solarTodayEnergy();
  return valid(energy) ? `${decimal(energy)} ${t('unit.kwh')}` : '—';
}

function solarForecastCards(now) {
  const days=EosChartData.dailySolar(snapshot.forecast,now,snapshot.zone);
  const measured=solarTodayEnergy();
  return days.map((row,i)=>{
    const totalToday=i===0 && valid(measured) && valid(row.kwh);
    const value=valid(row.kwh) ? `${totalToday ? '≈ ' : ''}${decimal(row.kwh+(totalToday ? measured : 0))} ${t('unit.kwh')}` : '—';
    return [t(['metric.pv_forecast_today','metric.pv_forecast_tomorrow','metric.pv_forecast_day_after'][i]),value,
      !valid(row.kwh) ? t('metric.forecast_missing') : totalToday ? t('metric.forecast_today_total')+(row.complete ? '' : ' · '+t('metric.forecast_partial'))
      : i===0 ? t('metric.forecast_remaining_only') : row.complete ? t('metric.forecast_complete') : t('metric.forecast_partial')];
  });
}

const consumerEnabled = key => !["car","heat"].includes(key) || snapshot.features?.[key] !== false;

function vehicleCards() {
  return (snapshot.vehicles ?? []).map(vehicle=>`<a class="vehicle-card" href="#car/${html(vehicle.id)}"><small>${html(vehicle.name)}</small><strong>${html(power(vehicle.live.car))}</strong><span>${html(percent(vehicle.live.car_soc))} · ${html(modeLabel(vehicle.live.car_mode))}</span></a>`).join('');
}

function overview() {
  byId('vehicle-cards').innerHTML=vehicleCards();
  const live = snapshot.live;
  const remaining = solarRemaining();
  byId('connection').textContent = snapshot.control_waiting ? t('control.waiting') : snapshot.armed ? t('control.active') : t('control.read_only');
  byId('live-time').textContent = live.time ? time(live.time) : t('status.no_readings');
  byId('overview-kpis').innerHTML = cards([
    [t('metric.pv_today'),solarToday(),remaining ? t('metric.remaining',{energy:remaining}) : t('metric.available_intervals')],
    [t('metric.price_now'),price(live.price),t('metric.import')],
    [t('metric.grid_connection'),power(live.grid),valid(live.grid) ? live.grid < 0 ? t('metric.export') : live.grid > 0 ? t('metric.import') : t('metric.no_grid_flow') : '—']
  ]);
  const names = {solar:t('node.solar'), grid:t('node.grid'), battery:t('node.battery'), house:t('node.house'), car:t('node.car'), heat:t('device.heat')};
  Object.keys(names).forEach(key => {
    const node = document.querySelector(`[data-node="${key}"]`);
    const flow = document.querySelector(`[data-flow="${key}"]`);
    node.hidden = !consumerEnabled(key);
    flow.style.display = consumerEnabled(key) ? "" : "none";
    if (!consumerEnabled(key)) return;
    const retained = snapshot.display?.[key];
    const stale = !valid(live[key]) && valid(retained?.value);
    const value = stale ? retained.value : live[key];
    const soc = live[key + '_soc'];
    const direction = key === 'grid' ? value < 0 ? t('metric.export') : t('metric.import')
      : key === 'battery' ? value < 0 ? t('metric.discharging') : t('mode.charging') : '';
    node.querySelector('strong').textContent = (stale && retained.estimated ? '≈ ' : '') + power(value);
    let ageNote = node.querySelector('.reading-age');
    if (!ageNote) {
      ageNote = document.createElement('small');
      ageNote.className = 'reading-age';
      node.append(ageNote);
    }
    ageNote.hidden = !stale;
    ageNote.textContent = stale ? t(retained.estimated ? 'metric.estimated_heat_age' : 'metric.last_report_age',
      {minutes:Math.ceil(retained.age_s / 60)}) : '';
    node.title = ageNote.textContent;
    if (key === "car" && snapshot.vehicles?.length) names.car=t("fleet.vehicles",{count:snapshot.vehicles.length});
    node.querySelector('span:nth-child(2)').textContent = valid(soc) ? `${names[key]} · ${percent(soc)}` : names[key];
    node.setAttribute('aria-label', [names[key],power(value),value ? direction : ''].filter(Boolean).join(' · '));
    flow.classList.toggle('inactive', !valid(value) || Math.abs(value) < 10);
    flow.classList.toggle('reverse', value < 0);
    flow.style.setProperty('--speed', `${Math.max(1.4, 5 - Math.abs(value || 0) / 2200)}s`);
    // One shared power scale keeps sources and consumers visually comparable.
    // Square-root scaling preserves visibility of small residential loads.
    const magnitude = valid(value) ? Math.abs(value) : 0;
    const intensity = Math.sqrt(Math.min(1, magnitude / 11000));
    const length = 2 + 6 * intensity;
    flow.style.setProperty('--pulse-width', `${(3 + 9 * intensity).toFixed(2)}px`);
    flow.style.setProperty('--pulse-dash', `${length.toFixed(2)} ${(100 - length).toFixed(2)}`);
  });
  byId('next').innerHTML = ['battery','car'].filter(consumerEnabled).filter(key=>key!=='car' || !snapshot.vehicles?.length).map(key => {
    const item = nextPlan(key);
    return `<div><small>${th('metric.eos_mode')} · ${key === 'car' ? th('node.car') : th('device.battery')}</small><b>${html(modeLabel(live[key + '_mode']))}</b><span>${item ? html(time(item.time) + ' · ' + modeLabel(item.mode)) : th('status.no_next_mode')}</span></div>`;
  }).join('');
}

const chartModels = new Map();
let activeProbe = null;

function chart(title, key, divisor, unit, color, now, additional = []) {
  const descriptors = [{key,label:key === 'solar' && additional.length ? t('chart.solar') : title,divisor,color},...additional];
  const series = descriptors.map(item => ({...item,
    actual:item.actual === false ? [] : EosChartData.points(actualPoints(item.key),item.key,now-day,now),
    future:item.future === false ? [] : EosChartData.points(snapshot.forecast,item.key,now-day,now+day).filter(row=>row.end>now)
  }));
  const numbers = series.flatMap(item => [...item.actual,...item.future].map(row=>row.value/item.divisor));
  if (!numbers.length) return `<section><h2>${html(title)} · ${html(unit)}</h2><p class="footnote">${th('chart.no_data')}</p></section>`;
  const min = key === 'price' ? Math.floor(Math.min(...numbers)-1) : Math.min(0,...numbers);
  const max = key.endsWith('_soc') ? 100 : Math.max(min+1,Math.ceil(Math.max(...numbers)+(key === 'price' ? 1 : 0)));
  chartModels.set(key,{series,now,unit});
  const curve = (rows,item,gap,forecast) => {
    let previous;
    const path = rows.map(row => {
      const x = Math.max(0,Math.min(100,50+(row.stamp-now)*50/day));
      const y = (max-row.value/item.divisor)*100/(max-min);
      const command = previous !== undefined && row.stamp-previous <= gap ? 'L' : 'M';
      previous = row.stamp;
      return `${command}${x.toFixed(3)},${y.toFixed(3)}`;
    }).join(' ');
    return `<path class="curve${forecast ? ' forecast' : ''}" style="--series:var(--${item.color})" d="${path}"/>`;
  };
  const axis = ['−24','−12',null,'+12','+24'].map(value =>
    `<span>${value ? `${value} ${th('chart.hour')}` : th('chart.now')}</span>`).join('');
  return `<section><h2>${html(title)} · ${html(unit)}</h2>
    <div class="series-legend">${series.map(item=>`<span><i style="--series:var(--${item.color})"></i>${html(item.label)}</span>`).join('')}</div>
    <div class="chart" data-chart="${html(key)}">
      <div class="axis-y" aria-hidden="true"><span>${decimal(max)}</span><span>${decimal((max+min)/2)}</span><span>${decimal(min)}</span></div>
      <div class="interactive-plot">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" tabindex="0" role="img" aria-label="${th('chart.interactive_aria',{title})}">
          <path class="guide" d="M0 1 H100 M0 50 H100 M0 99 H100"/><line class="now" x1="50" x2="50" y1="0" y2="100"/>
          ${series.map(item=>curve(item.actual,item,360000,false)+curve(item.future,item,3600000,true)).join('')}
        </svg>
        <div class="chart-crosshair" hidden></div><div class="chart-tooltip" role="status" hidden></div>
      </div><div class="axis-x">${axis}</div>
    </div></section>`;
}

function hideProbe() {
  activeProbe = null;
  document.querySelectorAll('.chart-crosshair,.chart-tooltip').forEach(element=>{element.hidden=true;});
}

function showProbe(id, ratio) {
  const model = chartModels.get(id);
  const plot = [...byId('charts').querySelectorAll('[data-chart]')].find(element=>element.dataset.chart===id)?.querySelector('.interactive-plot');
  if (!model || !plot) return;
  activeProbe = {id,ratio:Math.max(0,Math.min(1,ratio))};
  const stamp = model.now+(activeProbe.ratio-.5)*2*day;
  const tooltip = plot.querySelector('.chart-tooltip');
  tooltip.innerHTML = `<b>${html(time(stamp))}</b><small>${th(stamp > model.now ? 'chart.forecast_values' : 'chart.measured_values')}</small>`
    + model.series.map(item=>{
      const sample = EosChartData.at(item,stamp,model.now);
      const value = sample ? `${decimal(sample.point.value/item.divisor,2)} ${model.unit}` : '—';
      return `<div class="tooltip-series"><i style="--series:var(--${item.color})"></i><span>${html(item.label)}${sample ? `<small>${html(time(sample.point.stamp))}</small>` : ''}</span><strong>${html(value)}</strong></div>`;
    }).join('');
  tooltip.hidden=false;
  const crosshair = plot.querySelector('.chart-crosshair');
  crosshair.hidden=false;
  crosshair.style.left=`${activeProbe.ratio*100}%`;
  tooltip.style.left=`${Math.max(4,Math.min(plot.clientWidth-tooltip.offsetWidth-4,activeProbe.ratio*plot.clientWidth+12))}px`;
}

function energyDetail(now) {
  byId('detail-title').textContent=t('device.energy');
  const names = {solar:t('node.solar'),grid:t('node.grid'),battery:t('node.battery'),house:t('node.house'),car:t('node.car'),heat:t('device.heat')};
  byId('detail-kpis').innerHTML=cards(Object.entries(names).filter(([key])=>consumerEnabled(key)).map(([key,label])=>{
    const retained=snapshot.display?.[key];
    const estimated=!valid(snapshot.live[key]) && valid(retained?.value);
    return [label,(estimated ? '≈ ' : '')+power(estimated ? retained.value : snapshot.live[key]),
      estimated ? t('metric.last_report_age',{minutes:Math.ceil(retained.age_s/60)}) : t('metric.measured')];
  }));
  byId('timeline').innerHTML='';
  const additional = ['grid','battery','house','car','heat'].filter(consumerEnabled).map(key=>({key,label:names[key],divisor:1000,color:key,future:key!=='house'}));
  additional.push({key:'house_total',label:t('chart.house_forecast'),divisor:1000,color:'house',actual:false});
  byId('charts').innerHTML=chart(t('chart.energy'),'solar',1000,t('unit.kw'),'solar',now,additional)
    + `<p class="footnote">${th('chart.energy_signs')}</p>`
    + chart(t('chart.price'),'price',1,t('unit.price'),'heat',now);
  byId('plan').hidden=false;
  byId('plan').innerHTML=`<h2>${th('plan.forecast')}</h2><p>${th('chart.energy_forecast_note')}</p>`;
}

const chartsRoot = byId('charts');
function pointerProbe(event) {
  const svg=event.target.closest('.interactive-plot svg');
  if (!svg) {hideProbe();return;}
  const box=svg.getBoundingClientRect();
  showProbe(svg.closest('[data-chart]').dataset.chart,(event.clientX-box.left)/box.width);
}
chartsRoot.addEventListener('pointermove',pointerProbe);
chartsRoot.addEventListener('pointerdown',pointerProbe);
chartsRoot.addEventListener('pointerleave',hideProbe);
chartsRoot.addEventListener('pointercancel',hideProbe);
chartsRoot.addEventListener('focusin',event=>{
  const chart=event.target.closest('[data-chart]');
  if (chart) showProbe(chart.dataset.chart,.5);
});
chartsRoot.addEventListener('focusout',hideProbe);
chartsRoot.addEventListener('keydown',event=>{
  const chart=event.target.closest('[data-chart]');
  if (!chart) return;
  if (event.key==='Escape') {hideProbe();return;}
  if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const current=activeProbe?.id===chart.dataset.chart ? activeProbe.ratio : .5;
  showProbe(chart.dataset.chart,event.key==='Home' ? 0 : event.key==='End' ? 1 : current+(event.key==='ArrowRight' ? 1 : -1)/576);
});
function intervals(rows, start, end, gapLimit) {
  const ordered = rows.filter(row => row.stamp < end).sort((a,b) => a.stamp - b.stamp);
  const result = [];
  let cursor = start;
  const append = (from, to, mode) => {
    if (from >= to) return;
    const prior = result.at(-1);
    if (prior?.mode === mode && prior.end === from) prior.end = to;
    else result.push({start:from,end:to,mode});
  };
  ordered.forEach(({stamp, mode}, index) => {
    const from = Math.max(start, stamp);
    const to = Math.min(end, ordered[index + 1]?.stamp ?? end, stamp + gapLimit);
    if (from >= to) return;
    append(cursor,from,null);
    append(from,to,mode);
    cursor = to;
  });
  append(cursor,end,null);
  return result;
}

function timeline(key, now) {
  const plans = snapshot.plan[key] ?? [];
  const historical = history.local.map(row => ({stamp:Date.parse(row.time),mode:row[key === 'car' ? 'car_actual_mode' : 'battery_mode']}));
  const future = plans.map(item => ({stamp:Date.parse(item.time),mode:item.mode}));
  const planEnd = snapshot.plan_end ? Math.min(now + day, Date.parse(snapshot.plan_end)) : now + day;
  const planned = planEnd > now ? intervals(future,now,planEnd,Infinity) : [];
  if (planEnd < now + day) planned.push({start:Math.max(now, planEnd),end:now + day,mode:null});
  const all = [...intervals(historical,now-day,now,120000), ...planned];
  const legend = new Map();
  const bands = all.map(({start,end,mode}) => {
    const color = Object.hasOwn(modes, mode) ? modes[mode][1] : 'edge';
    const label = mode ? modeLabel(mode) : t('timeline.no_data');
    legend.set(label,color);
    const info = t('timeline.interval', {kind:t(start < now ? 'timeline.history' : 'timeline.plan'),
      start:time(start), end:time(end), mode:label});
    return `<button type="button" class="mode-segment${start >= now ? ' future' : ''}" style="--duration:${(end-start)/day};--mode:var(--${color})" data-mode="${html(info)}" aria-label="${html(info)}"></button>`;
  }).join('');
  return `<h2>${key === 'car' ? th('timeline.car_title') : th('timeline.battery_title')}</h2>
    <div class="mode-halves"><span>${th('timeline.history_range')}</span><span>${th('timeline.plan_range')}</span></div>
    <div class="mode-track" role="group" aria-label="${th('timeline.aria')}">${bands}</div>
    <div class="mode-legend">${[...legend].map(([label,color]) => `<span><i style="--mode:var(--${color})"></i>${html(label)}</span>`).join('')}</div>
    <p class="mode-detail" id="mode-detail" aria-live="polite">${html(modeLabel(snapshot.live[key + '_mode']))}</p>`;
}

function detail(key) {
  if (key.startsWith('car/')) {
    const vehicle=snapshot.vehicles?.find(item=>item.id===key.slice(4));
    if (!vehicle) return;
    const original=snapshot, originalHistory=history;
    try {
      snapshot={...original,...vehicle,vehicles:[],vehicle_name:vehicle.name};
      history={local:originalHistory.vehicles?.[vehicle.id] ?? vehicle.history ?? [],influx:[]};
      detail('car');
      byId('detail-title').textContent=vehicle.name;
    } finally {snapshot=original;history=originalHistory;}
    return;
  }
  if (key==='car' && snapshot.vehicles?.length) {
    chartModels.clear();
    byId('detail-title').textContent=t('fleet.title');
    byId('detail-kpis').innerHTML=vehicleCards();
    byId('timeline').innerHTML='';
    byId('charts').innerHTML=chart(t('fleet.total'),'car',1000,t('unit.kw'),'car',windowNow());
    byId('plan').hidden=false;
    byId('plan').innerHTML=`<p>${th('fleet.forecast_note')}</p>`;
    return;
  }
  const now = windowNow();
  chartModels.clear();
  if (key === 'energy') {
    energyDetail(now);
    if (activeProbe) showProbe(activeProbe.id,activeProbe.ratio);
    return;
  }
  const live = snapshot.live;
  const [name,title] = [t(`device.${key}`),t(`chart.${key}`)];
  byId('detail-title').textContent = name;
  const metadata = {
    solar:[[t('metric.pv_today'),solarToday(),t('metric.available_intervals')],...solarForecastCards(now)],
    grid:[[t('metric.direction'),valid(live.grid) ? live.grid < 0 ? t('metric.export') : t('metric.import') : '—',t('metric.grid_connection')]],
    battery:[[t('chart.soc'),percent(live.battery_soc),t('metric.measured')],[t('metric.eos_mode'),modeLabel(live.battery_mode),stateLabel('mode',live.battery_control)]],
    house:[[t('metric.house_total'),power(live.house_total),t('metric.house_includes')]],
    car:[[t('chart.soc'),percent(live.car_soc),stateLabel('source',live.soc_source)],[t('metric.target'),percent(snapshot.settings.target_soc),live.departure ? time(live.departure) : t('metric.no_departure')]],
    heat:[]
  };
  byId('detail-kpis').innerHTML = cards([[t('metric.current_power'),power(live[key]),key === 'car' ? stateLabel('mode',live.car_control ?? live.car_status) : t('metric.measured')],...metadata[key]]);
  const withPlan = key === 'battery' || key === 'car';
  byId('timeline').innerHTML = withPlan ? timeline(key,now) : '';
  byId('charts').innerHTML = chart(title,key,1000,t('unit.kw'),key,now,withPlan ? [{key:'solar',label:t('chart.solar'),divisor:1000,color:'solar'}] : [])
    + (key === 'house' ? chart(t('chart.house_total'),'house_total',1000,t('unit.kw'),'house',now) : '')
    + (withPlan ? chart(t('chart.soc'),key+'_soc',1,'%',key,now) : '')
    + (['battery','car','grid','heat'].includes(key) ? chart(t('chart.price'),'price',1,t('unit.price'),'heat',now) : '');
  if (activeProbe) showProbe(activeProbe.id,activeProbe.ratio);
  const upcoming = (snapshot.plan[key] ?? []).filter(item => Date.parse(item.time) > now).slice(0,5);
  byId('plan').hidden = !withPlan && key !== 'heat' && key !== 'house';
  byId('plan').innerHTML = withPlan
    ? `<h2>${th('plan.next')}</h2>${upcoming.length ? '<dl>'+upcoming.map(item => `<dt>${html(time(item.time))}</dt><dd>${html(modeLabel(item.mode))}</dd>`).join('')+'</dl>' : `<p>${th('plan.no_valid')}</p>`}`
    : `<h2>${th('plan.forecast')}</h2><p>${key === 'heat' ? th('plan.no_heat') : th('plan.house_total')}</p>`;
}

const form = byId('daily');
function scheduleFields() {
  const selected = form.elements.schedule.value;
  form.querySelectorAll('[data-schedule]').forEach(element => { element.hidden = element.dataset.schedule !== selected; });
  form.elements.departure.required = selected === 'once' && consumerEnabled('car');
}
function fillForm() {
  const vehicle=snapshot.vehicles?.find(item=>item.id===byId("vehicle-selector").value);
  const selected={...(vehicle?.settings ?? snapshot.settings),battery_min_soc:snapshot.settings.battery_min_soc,battery_max_soc:snapshot.settings.battery_max_soc,battery_pv_support:snapshot.settings.battery_pv_support};
  for (const [key,value] of Object.entries(selected)) {
    const input = form.elements.namedItem(key);
    if (!input) continue;
    if (input.type === 'checkbox') input.checked = value;
    else if (key === 'departure') {
      const parsed = new Date(value);
      input.value = valid(parsed.getTime()) ? new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60000).toISOString().slice(0,16) : '';
    } else input.value = value;
  }
  form.querySelectorAll('[name=day]').forEach(input => { input.checked = selected.weekdays?.includes(Number(input.value)) ?? false; });
  scheduleFields();
}
function settings() {
  const selector=byId('vehicle-selector');
  byId('vehicle-selector-label').hidden=!snapshot.vehicles?.length;
  if (snapshot.vehicles?.length && selector.options.length!==snapshot.vehicles.length) {
    selector.innerHTML=snapshot.vehicles.map(vehicle=>`<option value="${html(vehicle.id)}">${html(vehicle.name)}</option>`).join('');
    formReady=false;
  }
  document.querySelectorAll("[data-optional]").forEach(element=>{element.hidden=!consumerEnabled(element.dataset.optional);});
  if (!formReady && 'schedule' in snapshot.settings) {
    fillForm();
    formReady = true;
  }
  byId('ownership').textContent = snapshot.control_waiting ? t('control.waiting') : snapshot.armed ? t('control.active') : t('control.read_only');
  byId('control').textContent = snapshot.armed || snapshot.release_pending ? t('control.release') : t('control.take');
  byId('control').disabled = !formReady;
  const limits = snapshot.battery_limits;
  byId('battery-limits-status').textContent = snapshot.errors.battery_limits ? t('settings.battery_limits_failed')
    : limits?.confirmed ? t('settings.battery_limits_confirmed', {
      minimum:snapshot.settings.battery_min_soc, maximum:snapshot.settings.battery_max_soc})
    : limits?.managed ? t('settings.battery_limits_pending') : t('settings.battery_limits_unmanaged');
  byId('connections').innerHTML = `<dt>Akkudoktor EOS</dt><dd>${snapshot.errors.eos ? th('status.fetch_failed') : snapshot.plan.battery?.length || snapshot.plan.car?.length ? th('status.plan_available') : th('status.no_plan')}</dd>
    <dt>InfluxDB</dt><dd>${!snapshot.influx_configured ? th('status.local_history') : history.influx_error ? th('status.fetch_failed') : history.influx.length ? th('status.history_available') : th('status.no_samples')}</dd>`;
}
function render() {
  const requested = location.hash.slice(1);
  if (requested !== route) hideProbe();
  const vehicleRoute=requested.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===requested.slice(4));
  route = vehicleRoute || (pages.has(requested) && consumerEnabled(requested)) || requested === 'settings' ? requested : 'overview';
  byId('overview').hidden = route !== 'overview';
  byId('settings').hidden = route !== 'settings';
  byId('detail').hidden = !pages.has(route) && !vehicleRoute;
  const errors = Object.keys(snapshot.errors);
  const errorAreas = {device_pending:'notice.device_pending',goal:'notice.goal',runtime:'control.title',forecast:'notice.forecast',
    release:'notice.release',battery_limits:'notice.battery_limits',control_persistence:'notice.control_persistence',connection:'notice.connection'};
  byId('notice').textContent = errors.length ? `${t('notice.check')} · ${errors.map(key => errorAreas[key] ? t(errorAreas[key]) : key.toUpperCase()).join(', ')}` : '';
  if (route === 'overview') overview();
  else if (route === 'settings') settings();
  else detail(route);
}
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try { snapshot = await api('snapshot'); }
  catch { snapshot = {...snapshot,errors:{...snapshot.errors,connection:true}}; }
  finally { refreshing = false; render(); }
}
async function refreshHistory() {
  if (historyRefreshing) return;
  historyRefreshing = true;
  try { history = await api('history'); }
  catch { history.influx_error = true; }
  finally { historyRefreshing = false; render(); }
}
byId('vehicle-selector').addEventListener('change',()=>{formReady=false;settings();});
form.elements.schedule.addEventListener('change',scheduleFields);
form.addEventListener('submit', async event => {
  event.preventDefault();
  const values = {};
  for (const name of ['target_soc','pv_target_soc','reserve_w','regulation_interval_s','battery_min_soc','battery_max_soc']) values[name] = Number(form.elements[name].value);
  if (values.battery_min_soc >= values.battery_max_soc) {
    byId('saved').textContent = t('settings.battery_limits_invalid');
    return;
  }
  for (const name of ['pv','fast','battery_pv_support','phase_auto']) values[name] = form.elements[name].checked;
  for (const name of ['schedule','departure_time']) values[name] = form.elements[name].value;
  values.departure = form.elements.departure.value ? new Date(form.elements.departure.value).toISOString() : '';
  values.weekdays = [...form.querySelectorAll('[name=day]:checked')].map(input => Number(input.value));
  if (snapshot.vehicles?.length) values.vehicle_id=byId('vehicle-selector').value;
  try { await api('settings',values); byId('saved').textContent = t('settings.saved'); await refresh(); }
  catch (error) { byId('saved').textContent = error.message; }
});
byId('control').addEventListener('click', async () => {
  const enabled = !snapshot.armed && !snapshot.release_pending;
  if (enabled && !confirm(t('control.confirm'))) return;
  try { await api('control',{enabled}); byId('control-result').textContent = enabled ? t('control.taken') : t('control.released'); await refresh(); }
  catch (error) { byId('control-result').textContent = error.message; await refresh(); }
});
byId('timeline').addEventListener('click',event => {
  const button = event.target.closest('[data-mode]');
  if (button) byId('mode-detail').textContent = button.dataset.mode;
});
async function start() {
  let haLanguage;
  try {
    if (window.parent !== window) {
      const parentDocument = window.parent.document;
      haLanguage = parentDocument.querySelector('home-assistant')?.hass?.locale?.language
        || parentDocument.documentElement.lang;
    }
  } catch {
    // The HA panel bridge also supplies the frontend language when access is restricted.
  }
  const query = haLanguage ? `?ha_language=${encodeURIComponent(haLanguage)}` : '';
  language = await api('language' + query);
  document.documentElement.lang = language.locale;
  document.querySelectorAll('[data-i18n]').forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-aria]').forEach(element => {
    element.setAttribute('aria-label', t(element.dataset.i18nAria));
  });
  window.addEventListener('hashchange',render);
  render();
  refresh();
  refreshHistory();
  setInterval(refresh,5000);
  setInterval(refreshHistory,60000);
}
start().catch(() => {
  byId('notice').textContent = '⚠ EOS Energiezentrale · /api/language';
  byId('overview').hidden = true;
});
