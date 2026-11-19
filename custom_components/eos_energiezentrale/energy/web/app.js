'use strict';

const byId = id => document.getElementById(id);
const appScriptUrl=document.currentScript?.src||location.href;
const html = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const startupLanguage=(new URL(location.href).searchParams.get('lang')||navigator.language||'en').startsWith('de')?'de':'en';
const startupMessages={
  "en": {
    "error.bridge_not_ready": "Home Assistant is still connecting. Please wait briefly.",
    "error.not_ready": "The integration is still loading or is not active. Wait briefly; if this persists, check the integration in Devices & services.",
    "error.timeout": "Home Assistant did not respond within 30 seconds. Check the connection and retry.",
    "error.unauthorized": "Access denied. Open this panel with a Home Assistant administrator account.",
    "error.unknown_command": "The integration API is unavailable. Reload the integration or restart Home Assistant after updating.",
    "error.language_invalid": "The language pack is incomplete or invalid. Update the complete integration, including the i18n folder.",
    "error.language_unavailable": "The language pack could not be read. Check that the integration files were copied completely.",
    "error.history_unavailable": "History could not be loaded. Current readings can still be available; check the history/database connection.",
    "error.history_invalid": "The history response could not be processed. Check the integration log.",
    "error.invalid_report": "The report request is invalid. Check the period, date and cost settings.",
    "error.report_unavailable": "Consumption and cost data are temporarily unavailable. Device control is independent of this report.",
    "error.internal_error": "An internal integration error occurred. Check the Home Assistant log for the affected action.",
    "error.asset_mismatch": "UI files have different versions. Update the complete integration and retry to reload all UI files.",
    "startup.language": "Language could not be loaded",
    "startup.view": "The interface could not be displayed",
    "startup.retry": "Retry",
    "startup.details": "Technical details",
    "startup.unexpected": "An unexpected browser error occurred. Reload the UI; if it persists, check the technical details.",
    "action.language": "Language",
    "action.snapshot": "Current values",
    "action.history": "History",
    "action.settings": "Save settings",
    "action.control": "Change device control",
    "action.accounting": "Consumption & cost report",
    "notice.eos": "EOS plan unavailable; check EOS readiness and its connection.",
    "notice.eos_cached": "EOS temporarily unavailable; the last valid plan is being used for up to five minutes.",
    "notice.accounting": "Consumption/cost accounting is temporarily unavailable.",
    "notice.runtime": "A device command failed; check the integration diagnostics and log.",
    "error.request": "Request failed",
    "error.ingress_only": "Open the panel from Home Assistant",
    "error.not_found": "Page or action not found",
    "error.data_unavailable": "Data temporarily unavailable",
    "error.browser_request": "Invalid browser request",
    "error.invalid_json": "Invalid JSON",
    "error.invalid_settings": "Invalid settings. Check the ranges, departure date and selected weekdays.",
    "error.control_rejected": "Control request rejected",
    "error.change_unconfirmed": "The change could not be confirmed",
    "action.interface": "UI files"
  },
  "de": {
    "error.bridge_not_ready": "Die Verbindung zu Home Assistant wird noch aufgebaut. Bitte kurz warten.",
    "error.not_ready": "Die Integration wird noch geladen oder ist nicht aktiv. Kurz warten; bei dauerhaftem Fehler die Integration unter Geräte & Dienste prüfen.",
    "error.timeout": "Home Assistant hat innerhalb von 30 Sekunden nicht geantwortet. Verbindung prüfen und erneut versuchen.",
    "error.unauthorized": "Zugriff verweigert. Dieses Panel mit einem Home-Assistant-Administratorkonto öffnen.",
    "error.unknown_command": "Die Schnittstelle der Integration ist nicht verfügbar. Nach dem Update die Integration neu laden oder Home Assistant neu starten.",
    "error.language_invalid": "Das Sprachpaket ist unvollständig oder ungültig. Die vollständige Integration einschließlich i18n-Ordner aktualisieren.",
    "error.language_unavailable": "Das Sprachpaket konnte nicht gelesen werden. Prüfen, ob alle Integrationsdateien vollständig übertragen wurden.",
    "error.history_unavailable": "Der Verlauf konnte nicht geladen werden. Aktuelle Messwerte können weiter verfügbar sein; Verlauf und Datenbankverbindung prüfen.",
    "error.history_invalid": "Die Verlaufsdaten konnten nicht verarbeitet werden. Das Protokoll der Integration prüfen.",
    "error.invalid_report": "Die Bilanzanfrage ist ungültig. Zeitraum, Datum und Kosteneinstellungen prüfen.",
    "error.report_unavailable": "Verbrauchs- und Kostendaten sind vorübergehend nicht verfügbar. Die Gerätesteuerung läuft unabhängig von dieser Auswertung.",
    "error.internal_error": "Ein interner Fehler der Integration ist aufgetreten. Für die betroffene Aktion das Home-Assistant-Protokoll prüfen.",
    "error.asset_mismatch": "Die UI-Dateien haben unterschiedliche Versionen. Die Integration vollständig aktualisieren und mit Erneut versuchen alle UI-Dateien neu laden.",
    "startup.language": "Sprachpaket konnte nicht geladen werden",
    "startup.view": "Die Oberfläche konnte nicht dargestellt werden",
    "startup.retry": "Erneut versuchen",
    "startup.details": "Technische Details",
    "startup.unexpected": "Im Browser ist ein unerwarteter Fehler aufgetreten. Oberfläche neu laden; bei erneutem Fehler die technischen Details prüfen.",
    "action.language": "Sprachpaket",
    "action.snapshot": "Aktuelle Werte",
    "action.history": "Verlauf",
    "action.settings": "Einstellungen speichern",
    "action.control": "Steuerfreigabe ändern",
    "action.accounting": "Verbrauchs- und Kostenbilanz",
    "notice.eos": "EOS-Plan nicht verfügbar; Bereitschaft von EOS und die Verbindung prüfen.",
    "notice.eos_cached": "EOS vorübergehend nicht verfügbar; der letzte gültige Plan wird bis zu fünf Minuten weiterverwendet.",
    "notice.accounting": "Verbrauchs- und Kostenbilanz vorübergehend nicht verfügbar.",
    "notice.runtime": "Ein Gerätebefehl ist fehlgeschlagen; Integrationsdiagnosen und Protokoll prüfen.",
    "error.request": "Anfrage fehlgeschlagen",
    "error.ingress_only": "Panel über Home Assistant öffnen",
    "error.not_found": "Seite oder Aktion nicht gefunden",
    "error.data_unavailable": "Daten vorübergehend nicht verfügbar",
    "error.browser_request": "Ungültige Browseranfrage",
    "error.invalid_json": "Ungültiges JSON",
    "error.invalid_settings": "Ungültige Einstellungen. Prüfe Wertebereiche, Abfahrtstermin und Wochentage.",
    "error.control_rejected": "Steuerfreigabe abgelehnt",
    "error.change_unconfirmed": "Änderung konnte nicht bestätigt werden",
    "action.interface": "UI-Dateien"
  }
};
let language = {locale:startupLanguage==='de'?'de-DE':'en-GB', messages:startupMessages[startupLanguage]};
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
// Same local day: clock time; within six days: weekday and time; otherwise date and time.
const when = value => {
  if (!value) return '—';
  const stamp=new Date(value).getTime(), today=windowNow(), dayOf=ms=>new Intl.DateTimeFormat('sv-SE',{timeZone:snapshot.zone}).format(new Date(ms));
  const options={timeZone:snapshot.zone,hour:'2-digit',minute:'2-digit'};
  if (dayOf(stamp)===dayOf(today)) return new Intl.DateTimeFormat(language.locale,options).format(stamp);
  return Math.abs(stamp-today)<6*day ? new Intl.DateTimeFormat(language.locale,{...options,weekday:'short'}).format(stamp) : time(value);
};
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

const clientId=globalThis.crypto?.randomUUID?.()??`${Date.now()}-${Math.random()}`;
let requestId = 0;
const pendingRequests = new Map();
window.addEventListener('message', event => {
  if (event.source !== window.parent || event.origin !== location.origin
      || event.data?.channel !== 'eos-energy-response'
      || (event.data.client!==undefined&&event.data.client!==clientId)) return;
  const pending = pendingRequests.get(event.data.id);
  if (!pending) return;
  clearTimeout(pending.timer);
  pendingRequests.delete(event.data.id);
  if (event.data.error) pending.reject(requestError(event.data.error,pending.action,event.data));
  else pending.resolve(event.data.result);
});
function requestError(code,action,details={}) {
  const safeCode=typeof code==='string'&&/^[a-z_]{1,64}$/.test(code)?code:'request_failed';
  const error=Error(`${t(`action.${action}`)}: ${language.messages[`error.${safeCode}`]??t('error.request')}`);
  error.code=safeCode;error.action=action;
  error.reason=typeof details.reason==='string'&&/^[a-z_]{1,40}$/.test(details.reason)?details.reason:null;
  error.fields=Array.isArray(details.fields)?details.fields.filter(field=>typeof field==='string'&&/^[a-z_]{1,40}$/.test(field)):[];
  return error;
}

function showStartupError(stage,error) {
  console.error('EOS UI failed during '+stage,error?.code??error?.name??'Error');
  byId('notice').textContent=`${t(`startup.${stage}`)}. ${error?.code?error.message:t('startup.unexpected')}`;
  const retry=byId('startup-retry');if(retry){retry.textContent=t('startup.retry');retry.hidden=false;}
  if(byId('startup-details'))byId('startup-details').hidden=false;
  if(byId('startup-details-title'))byId('startup-details-title').textContent=t('startup.details');
  if(byId('startup-detail'))byId('startup-detail').textContent=[stage,error?.code??error?.name??'Error',error?.asset??'',error?.code?'':String(error?.message??'').slice(0,200)].filter(Boolean).join(' · ');
  for(const id of ['overview','detail','settings','usage','notices','status-band','top-notices','notice-pill'])if(byId(id))byId(id).hidden=true;
}

async function api(path, body) {
  if (window.parent === window) throw requestError('ingress_only',path.split('?')[0]);
  const id = ++requestId,action=path.split('?')[0];
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pendingRequests.delete(id); reject(requestError('timeout',action)); }, 30000);
    pendingRequests.set(id, {resolve, reject, timer, action});
    window.parent.postMessage({channel:'eos-energy-request', id, client:clientId, action:path.split('?')[0], values:body ?? {}}, location.origin);
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

const localDay = value => new Intl.DateTimeFormat('sv-SE', {timeZone:snapshot.zone}).format(new Date(value));

function solarRemaining() {
  const energy = snapshot.pv_daily_forecast?.[0]?.kwh;
  return valid(energy) ? `${decimal(energy)} ${t('unit.kwh')}` : null;
}

function solarTodayEnergy() {
  return snapshot.pv_today_kwh ?? null;
}

function solarToday() {
  const energy=solarTodayEnergy();
  return valid(energy) ? `${decimal(energy)} ${t('unit.kwh')}` : '—';
}

function solarForecastCards(now) {
  const days=snapshot.pv_forecast_totals ?? [];
  return days.map((row,i)=>{
    const totalToday=row.includes_measured;
    const value=valid(row.total_kwh) ? `${totalToday ? '≈ ' : ''}${decimal(row.total_kwh)} ${t('unit.kwh')}` : '—';
    return [t(['metric.pv_forecast_today','metric.pv_forecast_tomorrow','metric.pv_forecast_day_after'][i]),value,
      !valid(row.kwh) ? t('metric.forecast_missing') : totalToday ? t('metric.forecast_today_total')+(row.complete ? '' : ' · '+t('metric.forecast_partial'))
      : i===0 ? t('metric.forecast_remaining_only') : row.complete ? t('metric.forecast_complete') : t('metric.forecast_partial')];
  });
}

const consumerEnabled = key => !["car","heat"].includes(key) || snapshot.features?.[key] !== false;

function vehicleActive(vehicle) {
  if (vehicle.vehicles?.length) return vehicle.vehicles.some(vehicleActive);
  return vehicle.live?.car_connected !== false;
}

function vehicleStatus(vehicle) {
  return t(vehicle.live?.car_available === false ? 'vehicle.unavailable' : 'vehicle.disconnected');
}

function socBarCount(soc) {
  return valid(soc) && soc>=0 && soc<=100 ? Math.ceil(soc/20) : null;
}

function carIcon(soc) {
  const filled=socBarCount(soc);
  const bars=Array.from({length:5},(_,index)=>`<rect class="car-soc-bar${filled!==null && index<filled ? ' filled' : ''}" x="${(6.4+index*2.2).toFixed(1)}" y="10.8" width="1.5" height="4.4" rx=".35"/>`).join('');
  return `<svg class="vehicle-soc-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 18H2v-6l3-2 2.5-5h6.8L18 10l3 1.5a1.5 1.5 0 0 1 1 1.4V18h-2M8 18h8M5 10h13M11.5 5v5"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="18" r="2"/><g class="car-soc"${filled===null ? ' hidden' : ''}>${bars}</g></svg>`;
}

function vehicleCards() {
  return (snapshot.vehicles ?? []).map(vehicle=>`<a class="vehicle-card${vehicleActive(vehicle) ? '' : ' vehicle-inactive'}" href="#car/${html(vehicle.id)}"><small class="vehicle-heading">${carIcon(valid(vehicle.live.car_soc) ? vehicle.live.car_soc : vehicle.display?.car_soc?.value)}${html(vehicle.name)}</small><strong>${html(vehicleActive(vehicle) ? ((!valid(vehicle.live.car) && vehicle.display?.car ? "≈ " : "")+power(valid(vehicle.live.car) ? vehicle.live.car : vehicle.display?.car?.value)) : vehicleStatus(vehicle))}</strong><span>${html(percent(vehicle.live.car_soc))} · ${html(modeLabel(vehicle.live.car_mode))}</span></a>`).join('');
}

const displayed = key => snapshot.flow_display?.[key]?.value ?? (valid(snapshot.live[key]) ? snapshot.live[key] : snapshot.display?.[key]?.value);
const displayedPower = key => (snapshot.flow_display?.[key] || (snapshot.display?.[key] && !valid(snapshot.live[key])) ? '≈ ' : '')+power(displayed(key));
const displayAge = key => {
  const retained=snapshot.flow_display?.[key] ?? snapshot.display?.[key];
  return retained && (retained.transition_held || retained.aligned || !valid(snapshot.live[key])) ? t(retained.transition_held ? 'metric.waiting_car_power' : retained.aligned ? 'metric.aligned_age' : 'metric.last_report_age',{minutes:Math.ceil(retained.age_s/60)}) : null;
};

// Reuse nodes between polls so keyboard focus and animations stay stable.
function layoutFlow() {
  const vehicles=consumerEnabled('car') ? snapshot.vehicles ?? [] : [];
  const container=byId('vehicle-nodes'), paths=byId('vehicle-flows');
  const signature=JSON.stringify(vehicles.map(vehicle=>vehicle.id));
  if (container.dataset.vehicles!==signature) {
    container.replaceChildren();paths.replaceChildren();
    vehicles.forEach(vehicle=>{
      const node=document.createElement('a');
      node.className='node car r';node.href='#car/'+encodeURIComponent(vehicle.id);
      node.innerHTML=`<span class="orb" aria-hidden="true">${carIcon(null)}</span><span></span><strong></strong>`;
      container.append(node);
      const path=document.createElementNS('http://www.w3.org/2000/svg','path');
      path.setAttribute('class','pulse car');path.setAttribute('pathLength','100');paths.append(path);
    });
    container.dataset.vehicles=signature;
  }
  const keys=['solar','grid','battery','house','car','heat'];
  const entries=keys.map(key=>({key,node:document.querySelector(`[data-node="${key}"]`),
    flow:document.querySelector(`[data-flow="${key}"]`),enabled:consumerEnabled(key) && !(key==='car' && vehicles.length)}));
  entries.forEach(({node,flow,enabled})=>{node.hidden=!enabled;flow.style.display=enabled ? '' : 'none';});
  const cars=vehicles.map((vehicle,index)=>({key:'car',vehicle,node:container.children[index],flow:paths.children[index],enabled:true}));
  const right=[entries[3],...(vehicles.length ? cars : [entries[4]]),entries[5]].filter(entry=>entry.enabled);
  const height=Math.max(360,right.length*144);
  byId('energy-flow').style.height=height+'px';
  right.forEach((entry,index)=>{
    const y=(index+.5)*100/right.length;
    entry.node.style.setProperty('--x','70%');entry.node.style.setProperty('--y',y+'%');
    entry.flow.setAttribute('d',`M56 50 Q62 ${y} 70 ${y}`);
  });
  byId('flow-wires').setAttribute('d',[...entries.slice(0,3).filter(entry=>entry.enabled),...right]
    .map(entry=>entry.flow.getAttribute('d')).join(' '));
  return [...entries,...cars].filter(entry=>entry.enabled);
}

function updatePowerRing(node,key,value,source=snapshot) {
  const orb=node.querySelector('.orb');
  const enabled=['solar','battery','car'].includes(key)||(key==='heat'&&snapshot.heat_load_configured);
  orb.classList.toggle('power-ring-enabled',enabled);
  let ring=orb.querySelector('.power-ring');
  if(!enabled){ring?.remove();return;}
  if(!ring){
    ring=document.createElementNS('http://www.w3.org/2000/svg','svg');
    ring.setAttribute('class','power-ring');ring.setAttribute('viewBox','0 0 56 56');ring.setAttribute('aria-hidden','true');
    ring.innerHTML='<circle class="ring-track" cx="28" cy="28" r="26"/><circle class="ring-value" cx="28" cy="28" r="26" pathLength="100" transform="rotate(-90 28 28)"/>';
    orb.prepend(ring);
  }
  const reference=source.power_reference??{};
  const fraction=key==='heat'?(valid(snapshot.live.heat_load)?Math.max(0,Math.min(1,snapshot.live.heat_load)):null)
    :EosChartData.powerFraction(value,reference[key==='battery'?(value<0?'battery_discharge':'battery_charge'):key]);
  ring.querySelector('.ring-value').setAttribute('stroke-dasharray',`${fraction===null?0:fraction*100} 100`);
  ring.dataset.fraction=fraction===null?'':String(fraction);
  const label=fraction===null?t('ring.unknown'):t('ring.load',{percent:decimal(fraction*100)});
  node.title=[node.title,label].filter(Boolean).join(' · ');
  node.setAttribute('aria-label',node.getAttribute('aria-label')+' · '+label);
}

function renderFlow() {
  const names = {solar:t('node.solar'), grid:t('node.grid'), battery:t('node.battery'), house:t('node.house'), car:t('node.car'), heat:t('device.heat')};
  layoutFlow().forEach(({key,node,flow,vehicle}) => {
    const source=vehicle ?? snapshot, live=source.live;
    const name=vehicle ? vehicle.name : names[key];
    const inactiveCar = key === 'car' && !vehicleActive(source);
    const inactiveGrid = key === 'grid' && snapshot.power_supply?.grid_active === false;
    node.classList.toggle('vehicle-inactive', inactiveCar);
    node.classList.toggle('grid-disconnected', inactiveGrid);
    if (key === 'grid') {
      let indicator = node.querySelector('.backup-indicator');
      if (!indicator) {
        indicator = document.createElement('span');
        indicator.className = 'backup-indicator';
        indicator.setAttribute('aria-hidden','true');
        indicator.innerHTML = '<svg viewBox="0 0 24 24"><path d="m3 11 9-8 9 8M5 10v11h14V10"/><path class="backup-bolt" d="m13 8-5 7h4l-1 5 6-8h-4z"/></svg>';
        node.append(indicator);
      }
      indicator.hidden = !inactiveGrid;
      indicator.title = t('power_supply.backup');
    }
    const retained = source.flow_display?.[key] ?? source.display?.[key];
    const stale = !inactiveGrid && valid(retained?.value) && (retained.transition_held || retained.aligned || !valid(live[key]));
    const value = inactiveCar || inactiveGrid ? null : stale ? retained.value : live[key];
    const soc = source.flow_display?.[key+'_soc']?.value ?? (valid(live[key+'_soc']) ? live[key+'_soc'] : source.display?.[key+'_soc']?.value);
    if (key === 'car') {
      const filled=socBarCount(soc);
      node.querySelector('.car-soc')?.toggleAttribute('hidden',filled===null);
      node.querySelectorAll('.car-soc-bar').forEach((bar,index)=>bar.classList.toggle('filled',filled!==null && index<filled));
    }
    if (key === 'battery') {
      const knownSoc=valid(soc) && soc>=0 && soc<=100;
      const low=snapshot.battery_low===true;
      const filled=knownSoc ? Math.ceil(soc/20) : 0;
      node.classList.toggle('battery-low',low);
      node.querySelectorAll('.battery-bar').forEach((bar,index)=>bar.classList.toggle('filled',index<filled));
    }
    const direction = key === 'grid' ? value < 0 ? t('metric.export') : t('metric.import')
      : key === 'battery' ? value < 0 ? t('metric.discharging') : t('mode.charging') : '';
    node.querySelector('strong').hidden=inactiveCar;
    node.querySelector('strong').textContent = inactiveCar ? '' : (stale && retained.estimated ? '≈ ' : '') + power(value);
    let ageNote = node.querySelector('.reading-age');
    if (!ageNote) {
      ageNote = document.createElement('small');
      ageNote.className = 'reading-age';
      node.append(ageNote);
    }
    ageNote.hidden = inactiveCar || (!inactiveGrid && (!stale || (retained.aligned && retained.age_s<10)));
    ageNote.textContent = inactiveGrid ? t('power_supply.backup') : stale ? t(retained.transition_held ? 'metric.waiting_car_power' : retained.aligned ? 'metric.aligned_age' : retained.estimated ? 'metric.estimated_age' : 'metric.last_report_age',
      {minutes:Math.ceil(retained.age_s / 60)}) : '';
    node.title = [vehicle?.name,inactiveCar ? vehicleStatus(source) : '',ageNote.textContent].filter(Boolean).join(' · ');
    node.querySelector('span:nth-child(2)').textContent = socBarCount(soc)!==null ? `${name} · ${percent(soc)}` : name;
    node.setAttribute('aria-label', [name,inactiveGrid ? t('power_supply.backup') : inactiveCar ? vehicleStatus(source) : power(value),value ? direction : ''].filter(Boolean).join(' · '));
    if (['battery','car'].includes(key) && valid(soc)) {
      const warning=node.classList.contains('battery-low') ? t('battery.minimum_reached') : '';
      node.setAttribute('aria-label',[node.getAttribute('aria-label'),t('chart.soc')+' '+percent(soc),warning].filter(Boolean).join(' · '));
    }
    updatePowerRing(node,key,value,source);
    // The backend maps open notices to flow nodes; the browser only marks them.
    const problem=snapshot.node_problems?.[vehicle ? 'car/'+vehicle.id : key];
    node.classList.toggle('problem-error',problem==='error');
    node.classList.toggle('problem-warning',problem==='warning');
    const orb=node.querySelector('.orb');
    let flag=orb.querySelector('.flag');
    if (problem && !flag) {
      flag=document.createElement('span');flag.className='flag';flag.setAttribute('aria-hidden','true');flag.textContent='!';orb.append(flag);
    }
    if (flag) flag.hidden=!problem;
    if (problem) node.setAttribute('aria-label',node.getAttribute('aria-label')+' · '+t('flow.problem_'+problem));
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
}

const planWindow = {before:3*3_600_000, after:12*3_600_000};
const clock = value => new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,hour:'2-digit',minute:'2-digit'}).format(new Date(value));
function overviewTrack(now) {
  const start=now-planWindow.before, end=now+planWindow.after, span=end-start;
  const rows=(snapshot.mode_timeline?.battery??[]).map(row=>({...row,start:Math.max(start,row.start),end:Math.min(end,row.end)}))
    .filter(row=>row.end>row.start);
  if (!rows.some(row=>row.kind==='plan'&&row.mode)) return `<p class="footnote">${th('plan.no_valid')}</p>`;
  const legend=new Map();
  const segments=rows.map(row=>{
    const color=Object.hasOwn(modes,row.mode) ? modes[row.mode][1] : 'edge';
    const label=row.mode ? modeLabel(row.mode) : t('timeline.no_data');
    legend.set(label,color);
    const info=t('timeline.interval',{kind:t(`timeline.${row.kind}`),start:when(row.start),end:when(row.end),mode:label});
    return `<button type="button" class="mode-segment${row.kind==='plan' ? ' future' : ''}" style="--start:${(row.start-start)/span};--duration:${(row.end-row.start)/span};--mode:var(--${color})" data-mode="${html(info)}" aria-label="${html(info)}" aria-pressed="false">${row.end-row.start>=5_400_000 ? `<span>${html(label)}</span>` : ''}</button>`;
  }).join('');
  const at=stamp=>`${((stamp-start)*100/span).toFixed(2)}%`;
  return `<div class="plan-track-wrap"><div class="plan-track" role="group" aria-label="${th('timeline.aria')}">${segments}</div><span class="plan-now" style="left:${at(now)}" aria-hidden="true"></span></div>
    <div class="plan-axis" aria-hidden="true"><span style="left:0">${html(clock(start))}</span><span style="left:${at(now)}">${th('chart.now')}</span><span style="left:${at(now+6*3_600_000)}">${html(clock(now+6*3_600_000))}</span><span style="left:100%">${html(clock(end))}</span></div>
    <div class="mode-legend">${[...legend].map(([label,color])=>`<span><i style="--mode:var(--${color})"></i>${html(label)}</span>`).join('')}</div>`;
}
function planEventText(event) {
  const vehicle=event.vehicle_name ?? snapshot.vehicle_name ?? t('node.car');
  if (event.kind==='battery_full') return t('plan_event.battery_full',{soc:decimal(event.soc,0)});
  if (event.kind==='car_target') return t('plan_event.car_target',{vehicle,soc:decimal(event.soc,0)});
  if (event.device==='battery') {
    // The backend derives what the battery does from the forecast; the EOS mode name alone can mislead at night.
    if (event.effect) return t('plan_event.effect_'+event.effect);
    const key='plan_event.battery_'+event.mode;
    return Object.hasOwn(language.messages,key) ? t(key) : t('plan_event.battery',{mode:modeLabel(event.mode)});
  }
  return t('plan_event.car',{vehicle,mode:modeLabel(event.mode)});
}
function nextEvents() {
  const events=snapshot.plan_events ?? [];
  if (!events.length) return `<p class="footnote">${th('status.no_next_mode')}</p>`;
  return events.map(event=>{
    const details=[event.effect ? t('plan_event.eos_mode',{mode:modeLabel(event.mode)}) : '',valid(event.price_ct) ? t('plan_event.price',{price:price(event.price_ct)}) : ''].filter(Boolean).join(' · ');
    return `<div class="row"><span><b>${html(planEventText(event))}</b>${details ? `<br><small>${html(details)}</small>` : ''}</span><span class="tag">${html(when(event.time))}</span></div>`;
  }).join('');
}

// The expanded state of the event list is a per-viewer convenience only.
const nextDetailsKey='eos-energiezentrale.next-events-open';
function restoreNextDetails() {
  try { const saved=localStorage.getItem(nextDetailsKey); if(saved!==null)byId('next-details').open=saved==='1'; } catch { /* storage unavailable */ }
  byId('next-details').addEventListener('toggle',()=>{try { localStorage.setItem(nextDetailsKey,byId('next-details').open?'1':'0'); } catch { /* storage unavailable */ }});
}

function overview() {
  dayBalance();
  const live = snapshot.live;
  const backup = snapshot.power_supply?.grid_active === false;
  const remaining = solarRemaining();
  const weather = live.weather;
  const weatherNode = byId('flow-weather');
  weatherNode.hidden = !weather;
  if (weather) {
    const condition = weather.condition;
    const sun = '<circle cx="16" cy="13" r="6"/><path d="M16 2v2m0 18v2M5 13H3m26 0h-2M7 4l2 2m14 14 2 2M25 4l-2 2M9 20l-2 2"/>';
    const cloud = '<path d="M8 23h16a6 6 0 0 0 0-12 8 8 0 0 0-15-1 6.5 6.5 0 0 0-1 13Z"/>';
    let shape = condition === 'sunny' ? sun : condition === 'clear-night' ? '<path d="M24 23A12 12 0 0 1 11 3a12 12 0 1 0 13 20Z"/>' : cloud;
    if (condition === 'partlycloudy') shape = '<circle cx="9" cy="8" r="5"/>' + cloud;
    if (['rainy','pouring','lightning-rainy','snowy-rainy'].includes(condition)) shape += '<path d="m9 26-1 3m8-3-1 3m8-3-1 3"/>';
    if (['lightning','lightning-rainy'].includes(condition)) shape += '<path d="m17 17-4 7h5l-3 6"/>';
    if (['snowy','snowy-rainy','hail'].includes(condition)) shape += '<path d="M8 27h3m-1.5-1.5v3M22 27h3m-1.5-1.5v3"/>';
    if (condition === 'fog') shape += '<path d="M4 26h24M7 30h18"/>';
    if (['windy','windy-variant'].includes(condition)) shape = '<path d="M3 11h20a4 4 0 1 0-4-4M3 17h24M3 23h15a4 4 0 1 1-4 4"/>';
    if (['unknown','exceptional'].includes(condition)) shape = '<circle cx="16" cy="16" r="12"/><path d="M16 8v10m0 5v1"/>';
    byId('weather-shape').innerHTML = shape;
    const temperature = valid(weather.temperature) ? decimal(weather.temperature) + ' ' + weather.unit : '—';
    byId('weather-temperature').textContent = temperature;
    const description = stateLabel('weather', condition) + ' · ' + temperature;
    weatherNode.setAttribute('aria-label', description+' · '+t('forecast.open'));
    weatherNode.title = description+' · '+t('forecast.open');
  }
  const flowAge=Math.max(0,...['solar','grid','car','battery'].map(key=>snapshot.flow_display?.[key]?.age_s ?? 0));
  byId('live-time').textContent = live.time ? t('flow.as_of',{time:when(Date.parse(live.time)-flowAge*1000)}) : t('status.no_readings');
  byId('overview-kpis').innerHTML = cards([
    [t('metric.pv_today'),solarToday(),remaining ? t('metric.remaining',{energy:remaining}) : t('metric.available_intervals')],
    [t('metric.price_now'),price(displayed('price')),t('metric.import')],
    [t('metric.grid_connection'),backup ? t('power_supply.backup') : displayedPower('grid'),
      backup ? t('power_supply.grid_disconnected') : snapshot.power_supply?.state === 'unknown' ? t('power_supply.unknown')
      : valid(displayed('grid')) ? displayed('grid') < 0 ? t('metric.export') : displayed('grid') > 0 ? t('metric.import') : t('metric.no_grid_flow') : '—'],
    [t('node.battery'),percent(displayed('battery_soc')),valid(displayed('battery')) && Math.abs(displayed('battery'))>=10
      ? `${displayed('battery') < 0 ? t('metric.discharging') : t('mode.charging')} · ${displayedPower('battery')}` : t('metric.battery_idle')]
  ]);
  renderFlow();
  byId('overview-track').innerHTML=overviewTrack(windowNow());
  byId('next-events').innerHTML=nextEvents();
  const count=(snapshot.plan_events??[]).length;
  byId('next-count').hidden=!count;byId('next-count').textContent=count;
}

const chartModels = new Map();
let activeProbe = null;

function chart(title, key, divisor, unit, color, now, additional = [], chartId = key) {
  const descriptors = [{key,label:key === 'solar' && additional.length ? t('chart.solar') : title,divisor,color},...additional];
  const series = descriptors.map(item => ({...item,
    actual:item.actual === false ? [] : EosChartData.points(actualPoints(item.key),item.key,now-day,now),
    future:item.future === false ? [] : EosChartData.points(snapshot.forecast,item.key,now-day,now+day).filter(row=>row.end>now)
  }));
  const numbers = series.flatMap(item => [...item.actual,...item.future].map(row=>row.value/item.divisor));
  if (!numbers.length) return `<section><h2>${html(title)} · ${html(unit)}</h2><p class="footnote">${th('chart.no_data')}</p></section>`;
  const min = key === 'price' ? Math.floor(Math.min(...numbers)-1) : Math.min(0,...numbers);
  const max = key.endsWith('_soc') ? 100 : Math.max(min+1,Math.ceil(Math.max(...numbers)+(key === 'price' ? 1 : 0)));
  chartModels.set(chartId,{series,now,unit});
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
    <div class="chart" data-chart="${html(chartId)}">
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
    return [label,displayedPower(key),displayAge(key) ?? t("metric.measured")];
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
function timeline(key, now) {
  const all = snapshot.mode_timeline?.[key] ?? [];
  const legend = new Map();
  const bands = all.map(({start,end,mode,kind}) => {
    const color = Object.hasOwn(modes, mode) ? modes[mode][1] : 'edge';
    const label = mode ? modeLabel(mode) : t('timeline.no_data');
    legend.set(label,color);
    const info = t('timeline.interval', {kind:t(`timeline.${kind}`),
      start:time(start), end:time(end), mode:label});
    // Segments are placed by time, so the centre line is "now" however many segments EOS sends.
    const first=Math.max(start,now-day), last=Math.min(end,now+day);
    if (last<=first) return '';
    return `<button type="button" class="mode-segment${kind==='plan' ? ' future' : ''}" style="--start:${(first-now+day)/(2*day)};--duration:${(last-first)/(2*day)};--mode:var(--${color})" data-mode="${html(info)}" aria-label="${html(info)}"></button>`;
  }).join('');
  return `<h2>${key === 'car' ? th('timeline.car_title') : th('timeline.battery_title')}</h2>
    <div class="mode-halves"><span>${th('timeline.history_range')}</span><span>${th('timeline.plan_range')}</span></div>
    <div class="mode-track" role="group" aria-label="${th('timeline.aria')}">${bands}</div>
    <div class="mode-legend">${[...legend].map(([label,color]) => `<span><i style="--mode:var(--${color})"></i>${html(label)}</span>`).join('')}</div>
    <p class="mode-detail" id="mode-detail" aria-live="polite">${html(modeLabel(snapshot.live[key + '_mode']))}</p>`;
}

function vehicleSocChart(vehicle, now) {
  const original=snapshot, originalHistory=history;
  try {
    snapshot=vehicle;
    history={local:originalHistory.vehicles?.[vehicle.id] ?? vehicle.history ?? [],influx:[]};
    return chart(vehicle.name+' · '+t('chart.soc'),'car_soc',1,'%','car',now,[],'vehicle_soc_'+vehicle.id)
      + vehicleForecastNote(vehicle);
  } finally {snapshot=original;history=originalHistory;}
}
function vehicleForecastNote(vehicle) {
  const source=vehicle.vehicle_forecast_source;
  return ['eos','pv_estimate','fast_estimate','constant','unavailable'].includes(source)
    ? `<p class="footnote">${th(`forecast.vehicle_${source}`)}</p>` : '';
}
function detail(key) {
  const carPage=key==='car'||key.startsWith('car/');
  byId('car-view').hidden=!carPage;
  byId('vehicle-goals').hidden=!carPage;
  byId('detail-kpis').hidden=false;
  byId('detail-kpis').classList.toggle('vehicle-inactive', (key === 'car' || key.startsWith('car/')) && !vehicleActive(snapshot));
  const usageLink=byId('usage-link');
  usageLink.hidden=!['house','car','heat'].includes(key)&&!key.startsWith('car/');
  usageLink.href='#usage/'+key;
  if (key.startsWith('car/')) {
    const vehicle=snapshot.vehicles?.find(item=>item.id===key.slice(4));
    if (!vehicle) return;
    const original=snapshot, originalHistory=history;
    try {
      snapshot={...original,...vehicle,vehicles:[],vehicle_name:vehicle.name,display:vehicle.display ?? {},flow_display:vehicle.flow_display ?? {}};
      history={local:originalHistory.vehicles?.[vehicle.id] ?? vehicle.history ?? [],influx:[]};
      detail('car');
      byId('usage-link').href='#usage/'+key;
      byId('detail-title').textContent=vehicle.name;
    } finally {snapshot=original;history=originalHistory;}
    return;
  }
  if (key==='car') {vehicleSettings();carView();}
  if (key==='car' && snapshot.vehicles?.length) {
    chartModels.clear();
    byId('detail-title').textContent=t('fleet.title');
    byId('detail-kpis').innerHTML=vehicleCards();
    byId('timeline').innerHTML='';
    byId('charts').innerHTML=chart(t('fleet.total'),'car',1000,t('unit.kw'),'car',windowNow())
      + snapshot.vehicles.map(vehicle=>vehicleSocChart(vehicle,windowNow())).join('');
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
    grid:[[t('metric.direction'),valid(displayed('grid')) ? displayed('grid') < 0 ? t('metric.export') : t('metric.import') : '—',t('metric.grid_connection')]],
    battery:[[t('chart.soc'),percent(displayed("battery_soc")),t('metric.measured')],[t('metric.eos_mode'),modeLabel(live.battery_mode),stateLabel('mode',live.battery_control)]],
    house:[[t('metric.house_total'),displayedPower("house_total"),t('metric.house_includes')]],
    car:[[t('chart.soc'),percent(displayed("car_soc")),stateLabel('source',live.soc_source)],[t('metric.target'),percent(snapshot.charge_target_soc ?? snapshot.settings.target_soc),live.departure ? time(live.departure) : t('metric.no_departure')]],
    heat:[]
  };
  const inactiveCar = key === 'car' && !vehicleActive(snapshot);
  byId('detail-kpis').innerHTML = cards([[t('metric.current_power'),inactiveCar ? vehicleStatus(snapshot) : displayedPower(key),inactiveCar ? '' : displayAge(key) ?? (key === 'car' ? stateLabel('mode',live.car_control ?? live.car_status) : t('metric.measured'))],...metadata[key]]);
  const withPlan = key === 'battery' || key === 'car';
  byId('timeline').innerHTML = withPlan ? timeline(key,now) : '';
  byId('charts').innerHTML = chart(title,key,1000,t('unit.kw'),key,now,withPlan ? [{key:'solar',label:t('chart.solar'),divisor:1000,color:'solar'}] : [])
    + (key === 'house' ? chart(t('chart.house_total'),'house_total',1000,t('unit.kw'),'house',now) : '')
    + (withPlan ? chart(t('chart.soc'),key+'_soc',1,'%',key,now)+(key==='car'?vehicleForecastNote(snapshot):'') : '')
    + (['battery','car','grid','heat'].includes(key) ? chart(t('chart.price'),'price',1,t('unit.price'),'heat',now) : '');
  if (activeProbe) showProbe(activeProbe.id,activeProbe.ratio);
  const upcoming = snapshot.upcoming_plan?.[key] ?? [];
  // The car page answers goal and plan above; its raw KPIs and mode list would repeat them.
  if (key === 'car' && snapshot.charge_plan) {byId('detail-kpis').hidden=true;byId('plan').hidden=true;return;}
  byId('plan').hidden = !withPlan && key !== 'heat' && key !== 'house';
  byId('plan').innerHTML = withPlan
    ? `<h2>${th('plan.next')}</h2>${upcoming.length ? '<dl>'+upcoming.map(item => `<dt>${html(time(item.time))}</dt><dd>${html(modeLabel(item.mode))}</dd>`).join('')+'</dl>' : `<p>${th('plan.no_valid')}</p>`}`
    : `<h2>${th('plan.forecast')}</h2><p>${key === 'heat' ? th('plan.no_heat') : th('plan.house_total')}</p>`;
}

const form = byId('daily');
function fillForm() {
  for (const [key,value] of Object.entries(snapshot.settings)) {
    const input=form.elements.namedItem(key);
    if (!input) continue;
    if(input.type==='checkbox') input.checked=value;
    else input.value=value;
  }
  holidayFields();
}
function holidayFields() {
  const state=form.elements.holiday_state.value;
  const locality=form.elements.holiday_locality;
  locality.disabled=state!=='BY';
  if(locality.disabled) locality.value='';
  const catholic=form.elements.holiday_catholic;
  catholic.disabled=!['BY','SN','TH'].includes(state);
  if(catholic.disabled) catholic.checked=false;
}
const vehicleForm=byId('vehicle-daily');
const goalForm=byId('vehicle-goals');
let vehicleFormKey=null;
let chargePlanCounter=0;
let vehicleSaving=false;
let planScrollPending=false;
function selectedVehicle() {
  const selector=byId('vehicle-selector'), vehicles=snapshot.vehicles??[];
  return vehicles.find(item=>item.id===selector.value)??snapshot;
}
function vehicleSettings() {
  const selector=byId('vehicle-selector'), vehicles=snapshot.vehicles??[];
  byId('vehicle-selector-label').hidden=!vehicles.length;
  if(vehicles.map(item=>item.id).join(',')!==selector.dataset.vehicles) {
    selector.innerHTML=vehicles.map(item=>`<option value="${html(item.id)}">${html(item.name)}</option>`).join('');
    selector.dataset.vehicles=vehicles.map(item=>item.id).join(',');
  }
  const selected=selectedVehicle();
  const identity=selected.id??'primary';
  const key=(location.hash??'')+':'+identity;
  vehicleForm.dataset.vehicleId=selected.id??'';
  goalForm.dataset.vehicleId=selected.id??'';
  // Switches follow the backend on every refresh; a running save keeps the user's choice visible.
  if(!vehicleSaving) for(const name of ['pv','fast','phase_auto']) vehicleForm.elements[name].checked=selected.settings[name];
  vehicleForm.elements.phase_auto.disabled=selected.plugins?.wallbox?.features?.phase_switching===false;
  if(vehicleForm.elements.phase_auto.disabled)vehicleForm.elements.phase_auto.checked=false;
  const hint=byId('car-pv-hint'), fastHint=byId('car-fast-hint');
  if(hint) hint.textContent=t('car.pv_hint',{soc:decimal(selected.settings.pv_target_soc,0)});
  if(fastHint) fastHint.textContent=t('car.fast_hint',{soc:decimal(selected.settings.target_soc,0)});
  // Before the first snapshot there are no goals yet; do not lock the editor to that empty state.
  if(vehicleFormKey===key || !selected.charge_plan_view) return;
  vehicleFormKey=key;
  vehicleForm.elements.pv_target_soc.value=selected.settings.pv_target_soc;
  vehicleForm.elements.fast_target_soc.value=selected.settings.target_soc;
  byId('charge-plans').innerHTML='';
  for(const row of selected.charge_plan_view??[]) appendChargePlan(row);
  byId('vehicle-saved').textContent='';
}
const weekdayKeys=['mon','tue','wed','thu','fri','sat','sun'];
function weekdayText(days) {
  const sorted=[...new Set(days)].sort((a,b)=>a-b), label=index=>t(`weekday.${weekdayKeys[index]}`);
  if(sorted.length===7) return t('car.goal_daily');
  const runs=[];
  for(const value of sorted) {
    const run=runs.at(-1);
    if(run && value===run[1]+1) run[1]=value; else runs.push([value,value]);
  }
  return runs.map(([first,last])=>last-first>=2 ? `${label(first)}–${label(last)}` : first===last ? label(first) : `${label(first)}, ${label(last)}`).join(', ');
}
function goalSummary(row) {
  const schedule=row.schedule==='weekly'
    ? `${weekdayText(row.weekdays??[])} ${row.departure_time??''}`.trim()
    : row.next_departure ? when(row.next_departure) : (row.departure_local??'').replace('T',' ');
  const next=row.next_departure===undefined ? t('car.goal_unsaved') : row.next_departure ? t('plans.next',{date:when(row.next_departure)}) : t('plans.no_next');
  const tags=[row.selected ? `<span class="tag accent">${th('car.goal_next')}</span>` : '',
    row.active===false ? `<span class="tag">${th('car.goal_inactive')}</span>` : '',
    row.schedule==='weekly' && row.holidays ? `<span class="tag">${th('car.goal_holidays')}</span>` : ''].join('');
  return `<span class="goal-when"><b>${html(decimal(row.target_soc,0))} %</b></span>
    <span class="goal-text"><b>${html(schedule||t('plans.no_next'))}</b><small>${html(next)}</small></span>
    <span class="goal-tags">${tags}<button type="button" class="btn goal-edit" aria-expanded="false">${th('car.goal_edit')}</button></span>`;
}
function appendChargePlan(row, open=false) {
  const card=document.createElement('fieldset');
  card.className='charge-goal'+(row.selected?' selected':'');card.dataset.id=row.id;
  card.innerHTML=`<legend class="sr-only">${th('plans.goal')}</legend><div class="goal-summary">${goalSummary(row)}</div><div class="goal-editor"${open?'':' hidden'}><div class="goal-header">
    <label class="check"><input name="active" type="checkbox" ${row.active?'checked':''}>${th('plans.active')}</label>
    <button type="button" class="delete-goal">${th('plans.delete')}</button></div>
    <div class="fields"><label>${th('settings.schedule')}<select name="schedule"><option value="once">${th('settings.once')}</option><option value="weekly">${th('settings.weekly')}</option></select></label>
    <label>${th('settings.target_soc')}<input name="target_soc" type="number" min="1" max="100" required value="${html(row.target_soc)}"></label>
    <label data-goal-schedule="once">${th('settings.departure')}<input name="departure_local" type="datetime-local" value="${html(row.departure_local??'')}"></label>
    <label data-goal-schedule="weekly">${th('settings.departure_time')}<input name="departure_time" type="time" value="${html(row.departure_time??'07:30')}"></label></div>
    <div data-goal-schedule="weekly" class="checks">${weekdayKeys.map((day,i)=>`<label><input name="day" type="checkbox" value="${i}" ${(row.weekdays??[]).includes(i)?'checked':''}>${th(`weekday.${day}`)}</label>`).join('')}
    <label><input name="holidays" type="checkbox" ${row.holidays?'checked':''}>${th('plans.holidays')}</label></div></div>`;
  card.querySelector('[name=schedule]').value=row.schedule;
  const update=()=>{
    const mode=card.querySelector('[name=schedule]').value;
    card.querySelectorAll('[data-goal-schedule]').forEach(item=>{item.hidden=item.dataset.goalSchedule!==mode;});
    card.querySelector('[name=departure_local]').required=mode==='once';
    card.querySelector('[name=departure_time]').required=mode==='weekly';
  };
  card.querySelector('[name=schedule]').addEventListener('change',update);
  card.querySelector('.delete-goal').addEventListener('click',()=>{if(confirm(t('plans.delete_confirm')))card.remove();});
  const edit=card.querySelector('.goal-edit'), editor=card.querySelector('.goal-editor');
  if(edit && editor) {
    edit.setAttribute?.('aria-expanded',String(open));
    edit.addEventListener('click',()=>{editor.hidden=!editor.hidden;edit.setAttribute?.('aria-expanded',String(!editor.hidden));
      edit.textContent=t(editor.hidden?'car.goal_edit':'car.goal_close');});
    if(open) edit.textContent=t('car.goal_close');
  }
  update();byId('charge-plans').append(card);
}
function chargePlanValues() {
  return [...byId('charge-plans').querySelectorAll('.charge-goal')].map(card=>{
    const value=name=>card.querySelector('[name='+name+']');
    return {id:card.dataset.id,active:value('active').checked,schedule:value('schedule').value,
      target_soc:Number(value('target_soc').value),departure_local:value('departure_local').value,
      departure_time:value('departure_time').value,holidays:value('holidays').checked,
      weekdays:[...card.querySelectorAll('[name=day]:checked')].map(input=>Number(input.value))};
  });
}
async function saveVehicleSwitch(input) {
  const output=byId('vehicle-switch-saved'), values={};
  if(input.type==='checkbox') values[input.name]=input.checked;
  else {
    const value=Number(input.value);
    if(input.value===''||!Number.isFinite(value)||value<1||value>100) {output.textContent=t('car.invalid');return;}
    values[input.name==='fast_target_soc' ? 'target_soc' : input.name]=value;
  }
  if(vehicleForm.dataset.vehicleId) values.vehicle_id=vehicleForm.dataset.vehicleId;
  vehicleSaving=true;output.textContent=t('car.saving');
  try {await api('settings',values);output.textContent=t('settings.saved');}
  catch(error) {
    if(input.type==='checkbox') input.checked=!input.checked;
    output.textContent=error.message;
  } finally {vehicleSaving=false;}
  await refresh();
}

const kwhText=value=>`${decimal(value,1)} kWh`;
const euro=value=>new Intl.NumberFormat(language.locale,{style:'currency',currency:'EUR'}).format(value);
const chargeKinds={pv:'solar',grid:'grid',pause:'edge',ready:'car'};
function durationText(seconds) {
  const minutes=Math.round(seconds/60), hours=Math.floor(minutes/60);
  return hours ? t('car.duration',{h:hours,m:minutes%60}) : t('car.duration_min',{m:minutes});
}
function phaseText(phases) {
  return phases===1||phases===3 ? t('car.phases_'+phases) : '';
}
function chargePowerText(segment) {
  return [`${decimal(segment.power_w/1000,1)} ${t('unit.kw')}`,phaseText(segment.phases)].filter(Boolean).join(' ');
}
function chargeSummary(plan) {
  if(plan.state==='disconnected') return t('car.summary_disconnected');
  if(plan.state==='reached') return t('car.summary_reached');
  if(!plan.segments?.length) return t('car.summary_no_plan');
  const parts=[];
  if(plan.pv_kwh>=.05) parts.push(t('car.summary_pv',{kwh:kwhText(plan.pv_kwh),time:when(plan.pv_until)}));
  if(plan.grid_kwh>=.05) parts.push(t('car.summary_grid',{kwh:kwhText(plan.grid_kwh),time:when(plan.grid_from),price:price(plan.grid_price_ct)}));
  const text=[valid(plan.remaining_kwh) ? t('car.remaining',{kwh:kwhText(plan.remaining_kwh)}) : '',
    parts.length ? t('car.summary_plan',{parts:parts.join(t('car.summary_and'))}) : t('car.summary_none')];
  const late=plan.departure && (!plan.reached_at || Date.parse(plan.reached_at)>Date.parse(plan.departure));
  if(late) text.push(t('car.summary_late'));
  return text.filter(Boolean).join(' ');
}
function socRing(soc, target) {
  const circle=301.6, value=valid(soc) ? Math.max(0,Math.min(100,soc)) : 0;
  const goal=valid(target) ? `<circle class="goal" cx="60" cy="60" r="48" stroke-dasharray="2 ${circle}" stroke-dashoffset="${(-target/100*circle).toFixed(1)}" transform="rotate(-90 60 60)"/>` : '';
  const label=t('car.ring',{soc:percent(soc),target:percent(target)});
  return `<svg class="soc-ring" viewBox="0 0 120 120" role="img" aria-label="${html(label)}"><circle class="t" cx="60" cy="60" r="48"/>
    <circle class="v" cx="60" cy="60" r="48" stroke-dasharray="${(value/100*circle).toFixed(1)} ${circle}" transform="rotate(-90 60 60)"/>${goal}
    <text x="60" y="62" text-anchor="middle">${html(valid(soc) ? decimal(soc,0)+' %' : '—')}</text>${valid(target) ? `<text class="sub" x="60" y="80" text-anchor="middle">${html(t('car.ring_target',{soc:decimal(target,0)}))}</text>` : ''}</svg>`;
}
function carGoal(plan) {
  const live=snapshot.live??{}, target=plan.target_soc;
  const title=plan.departure ? t('car.goal_until',{when:when(plan.departure),soc:decimal(target,0)}) : t('car.goal_open',{soc:decimal(target,0)});
  const charging=valid(live.car) && live.car>=100;
  const tags=[charging ? `<span class="tag">${html([power(live.car),phaseText(live.phases)].filter(Boolean).join(' · '))}</span>` : '',
    `<span class="tag">${html(modeLabel(live.car_mode))}</span>`,
    live.soc_source ? `<span class="tag">${html(t('car.soc_source',{source:stateLabel('source',live.soc_source)}))}</span>` : ''].join('');
  return `<div class="soc-goal-head">${socRing(plan.soc,target)}<div class="goal-copy"><h2>${html(title)}</h2>
    <p class="dim">${html(chargeSummary(plan))}${plan.segments?.length ? ` <a href="#car-plan" class="to-plan">${th('car.to_plan')}</a>` : ''}</p>
    <div class="goal-tags">${tags}</div></div></div>`;
}
const chargeAlerts={suspended:['crit','error'],overridden:['warn','override'],read_only:['info','info'],disconnected:['off','info']};
function chargeAlert(plan) {
  const alert=chargeAlerts[plan.state];
  if(!alert) return '';
  const immediate=plan.immediate_cost?.reached_at;
  const meta=plan.state==='overridden' && immediate ? t('car.alert_overridden_at',{soc:decimal(plan.target_soc,0),time:when(immediate)}) : t(`car.alert_${plan.state}`);
  const link=plan.state==='suspended' ? `<a href="#notices">${th('car.alert_diagnose')}</a>` : '<span></span>';
  return `<div class="notice-card tone-${alert[0]}" role="${alert[0]==='crit'?'alert':'status'}"><span class="sev">${th('car.sev_'+alert[1])}</span>
    <div><b>${th(`car.alert_${plan.state}_title`)}</b><small>${html(meta)}</small></div>${link}</div>`;
}
function socPlot(plan, start, span) {
  const points=(plan.curve??[]).map(point=>({x:Math.max(0,Math.min(100,(Date.parse(point.time)-start)*100/span)),y:100-Math.max(0,Math.min(100,point.soc))}));
  if(!points.length) return '';
  points.push({x:100,y:points.at(-1).y});
  const line=points.map(point=>`${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
  const target=valid(plan.target_soc) ? 100-plan.target_soc : null;
  const reached=plan.reached_at ? t('car.plot_target_at',{soc:decimal(plan.target_soc,0),time:when(plan.reached_at)}) : valid(plan.target_soc) ? t('car.ring_target',{soc:decimal(plan.target_soc,0)}) : '';
  return `<div class="socplot" aria-hidden="true"><svg viewBox="0 0 100 100" preserveAspectRatio="none">
    <polygon class="soc-area" points="${line} 100,100 0,100"/>${target===null ? '' : `<line class="soc-target" x1="0" y1="${target}" x2="100" y2="${target}"/>`}
    <polyline class="soc-line" points="${line}"/></svg>
    <span class="soclbl" style="left:0;top:calc(${points[0].y.toFixed(1)}% - 20px)">${html(decimal(plan.soc,0))} %</span>
    ${target===null ? '' : `<span class="soclbl" style="right:0;top:calc(${Math.max(0,target).toFixed(1)}% - 20px)">${html(reached)}</span>`}</div>`;
}
function segmentText(segment) {
  const parts=[`${clock(segment.start)}–${clock(segment.end)}`,t('car.kind_'+segment.kind)];
  if(segment.kwh>=.05) {
    parts.push(chargePowerText(segment));
    parts.push(t('car.seg_energy',{kwh:kwhText(segment.kwh),from:decimal(segment.soc_start,0),to:decimal(segment.soc_end,0)}));
    parts.push(segment.kind==='pv' && valid(segment.value_ct) ? t('car.seg_valued',{price:price(segment.value_ct)}) : price(segment.price_ct));
  } else if(segment.kind==='pause' && valid(segment.price_ct)) parts.push(t('car.row_pause_price',{price:price(segment.price_ct)}));
  return parts.filter(Boolean).join(' · ');
}
function segmentRow(segment, plan) {
  let title, detail, stamp=when(segment.start);
  if(segment.kind==='pv') {
    title=t('car.row_pv');stamp=t('car.row_until',{time:when(segment.end)});
    detail=[t('car.row_charge',{kwh:kwhText(segment.kwh),soc:decimal(segment.soc_end,0)}),valid(segment.cost_eur) ? euro(segment.cost_eur) : ''];
  } else if(segment.kind==='grid') {
    title=t(segment.phases ? 'car.row_grid_phases' : 'car.row_grid',{power:`${decimal(segment.power_w/1000,1)} ${t('unit.kw')}`,phases:phaseText(segment.phases)});
    detail=[t('car.row_charge',{kwh:kwhText(segment.kwh),soc:decimal(segment.soc_end,0)}),price(segment.price_ct),valid(segment.cost_eur) ? euro(segment.cost_eur) : ''];
  } else if(segment.kind==='ready') {
    title=t('car.row_ready',{soc:decimal(plan.target_soc,0)});
    detail=[plan.buffer_s && plan.departure ? t('car.row_buffer',{duration:durationText(plan.buffer_s),when:when(plan.departure)}) : ''];
  } else {
    title=t('car.row_pause');detail=[valid(segment.price_ct) ? t('car.row_pause_price',{price:price(segment.price_ct)}) : ''];
  }
  detail=detail.filter(Boolean).join(' · ');
  return `<div class="row"><span><b>${html(title)}</b>${detail ? `<br><small>${html(detail)}</small>` : ''}</span><span class="tag">${html(stamp)}</span></div>`;
}
function chargeCompare(plan) {
  const planned=plan.plan_cost, now=plan.immediate_cost, fast=plan.state==='overridden';
  if(!planned && !now) return '';
  const box=(label,cost,approximate,win)=>`<div class="${win ? 'win' : ''}"><small>${html(label)}</small><strong>${cost ? html((approximate ? '≈ ' : '')+euro(cost.eur)) : '—'}</strong>
    <small>${cost ? html([valid(cost.price_ct) ? t('car.compare_avg',{price:price(cost.price_ct)}) : '',
      cost.reached_at ? t(approximate ? 'car.compare_at_estimated' : 'car.compare_at',{soc:decimal(plan.target_soc,0),time:when(cost.reached_at)}) : ''].filter(Boolean).join(' · ')) : html(t('car.compare_none'))}</small></div>`;
  const cheaper=planned && now ? planned.eur<=now.eur : Boolean(planned);
  const note=valid(plan.pv_price_ct) ? t('car.compare_note',{price:price(plan.pv_price_ct)}) : t('car.compare_note_free');
  return `<div class="cp-compare">${box(t('car.compare_plan'),planned,false,!fast&&cheaper)}${box(t(fast ? 'car.compare_now_active' : 'car.compare_now'),now,true,fast)}</div>
    <p class="footnote">${html(note)}</p>`;
}
function carPlanPanel(plan) {
  const start=windowNow(), end=Math.max(start+3_600_000,Date.parse(plan.end)), span=end-start;
  const title=plan.departure ? t('car.plan_title',{when:when(plan.departure)}) : t('car.plan_title_open');
  const tag=chargeAlerts[plan.state] ? t('car.state_'+plan.state)
    : plan.generated_at ? t('car.plan_from',{time:when(plan.generated_at)}) : '';
  const segments=plan.segments??[];
  const track=segments.map((segment,index)=>{
    const from=Math.max(start,Date.parse(segment.start)), to=Math.min(end,Date.parse(segment.end)), share=(to-from)/span;
    const info=segmentText(segment);
    if (share<=0) return '';
    return `<button type="button" class="mode-segment" style="--start:${((from-start)/span).toFixed(4)};--duration:${share.toFixed(4)};--mode:var(--${chargeKinds[segment.kind]})" data-charge="${index}" data-mode="${html(info)}" aria-label="${html(info)}" aria-pressed="false">${share>=.12 ? `<span>${th('car.short_'+segment.kind)}</span>` : ''}</button>`;
  }).join('');
  const at=stamp=>`${((stamp-start)*100/span).toFixed(2)}%`;
  const step=span>12*3_600_000 ? 4*3_600_000 : span>4*3_600_000 ? 2*3_600_000 : 3_600_000;
  const ticks=[];
  for(let stamp=Math.ceil((start+step/2)/step)*step;stamp<end-step/2;stamp+=step) ticks.push(stamp);
  const legend=[...new Set(segments.map(segment=>segment.kind))].map(kind=>`<span><i style="--mode:var(--${chargeKinds[kind]})"></i>${th('car.kind_'+kind)}</span>`).join('');
  const body=segments.length ? `<div class="plan-track-wrap"><div class="plan-track charge-track" role="group" aria-label="${th('car.track_aria')}">${track}</div></div>
    <div class="plan-axis" aria-hidden="true"><span style="left:0">${th('chart.now')}</span>${ticks.map(stamp=>`<span style="left:${at(stamp)}">${html(clock(stamp))}</span>`).join('')}<span style="left:100%">${html(when(end))}</span></div>
    <div class="mode-legend">${legend}</div>
    <p class="mode-detail" id="car-plan-detail" aria-live="polite">${th('car.track_hint')}</p>
    <div class="list">${segments.filter(segment=>Date.parse(segment.end)-Date.parse(segment.start)>=(segment.kind==='pause' ? 1_800_000 : 600_000)||segment.kwh>=.5).map(segment=>segmentRow(segment,plan)).join('')}</div>
    ${chargeCompare(plan)}` : `<p class="footnote">${th(plan.state==='disconnected' ? 'car.summary_disconnected' : 'car.no_plan')}</p>`;
  return `<div class="panel-heading"><h2>${html(title)}</h2>${tag ? `<span class="tag">${html(tag)}</span>` : ''}</div>
    ${chargeAlert(plan)}${socPlot(plan,start,span)}${body}`;
}
function carView() {
  const plan=snapshot.charge_plan;
  const fleet=Boolean(snapshot.vehicles?.length);
  byId('car-goal').hidden=fleet||!plan;
  byId('car-plan').hidden=fleet||!plan;
  if(fleet||!plan) {planScrollPending=false;return;}
  byId('car-goal').innerHTML=carGoal(plan);
  byId('car-plan').innerHTML=carPlanPanel(plan);
  byId('car-plan').classList.toggle('overridden',plan.state==='overridden'||plan.state==='read_only');
  if(planScrollPending) {
    planScrollPending=false;
    requestAnimationFrame(()=>byId('car-plan').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}));
  }
}
function batteryGroupDetails(group) {
  if(!group)return '';
  return `<dt>${th('plugin.fronius_site')}</dt><dd>${th('plugin.site_summary',{inverters:group.inverter_count,batteries:group.battery_count})}${valid(group.capacity_wh)?' · '+th('plugin.site_capacity',{capacity:decimal(group.capacity_wh/1000,2)+' '+t('unit.kwh')}):''}</dd>`+
    (group.devices??[]).map(device=>{
      const measurements=device.measurements??{solar:device.solar,inverter_ac:device.ac};
      const labels={solar:th('measurement.solar'),inverter_ac:th('measurement.inverter_ac'),house_total:th('measurement.house_total'),grid:th('measurement.grid')};
      const values=Object.entries(measurements).map(([key,value])=>`<span>${labels[key]??html(key)}: <strong>${valid(value)&&value<0?'− ':''}${html(power(value))}</strong></span>`);
      if(device.battery)values.push(`<span>${th('measurement.battery_soc')}: <strong>${html(percent(device.soc))}</strong></span>`);
      const firmware=device.read_diagnostics?.firmware;
      const firmwareDetails=firmware?`<div>${th('plugin.firmware')}: <strong>${html(firmware.version??t('plugin.firmware_unknown'))}</strong> (${th('plugin.firmware_source_'+firmware.source)}) · ${th('plugin.firmware_register')}: ${th('plugin.firmware_register_'+firmware.register_status)}${Array.isArray(firmware.raw_words)?' ['+html(firmware.raw_words.map(word=>'0x'+word.toString(16).toUpperCase().padStart(4,'0')).join(' '))+']':''}</div>`:'';
      return `<dt>${html(device.name==='primary'?t('plugin.primary_inverter'):device.name)}</dt><dd><div>${device.plugin?html(device.plugin.name)+' · ':''}${th(device.battery?'plugin.site_storage':'plugin.site_pv')} · ${th(device.available?'plugin.site_available':'plugin.site_unavailable')}</div><div class="device-measurements">${values.join('')}</div>${firmwareDetails}</dd>`;
    }).join('')+
    (group.approximate?`<dt>${th('plugin.pool_approximation')}</dt><dd>${th('plugin.pool_limitations')}</dd>`:'')+
    (group.battery_count===0?`<dd>${th('plugin.no_storage')}</dd>`:'');
}

/* Settings: one save bar for all sections; field errors come from the backend's allow-listed field names. */
const settingsUi = {section:'battery', baseline:null, costBaseline:null, costLoading:null, saving:false};
const costForm = byId('cost-settings');
function formState(target) {
  const values={};
  for (const element of target.elements) if (element.name) values[element.name]=element.type==='checkbox' ? element.checked : element.value;
  return values;
}
function dirtySettings() {
  const result=[];
  for (const [target,baseline,group] of [[form,settingsUi.baseline,'daily'],[costForm,settingsUi.costBaseline,'cost']]) {
    if (!baseline) continue;
    const now=formState(target);
    for (const key of Object.keys(now)) if (now[key]!==baseline[key]) result.push({group,key});
  }
  return result;
}
function updateSavebar() {
  const dirty=dirtySettings();
  byId('savebar').hidden=route!=='settings' || !dirty.length;
  byId('dirty-count').textContent=dirty.length===1 ? t('settings.one_change') : t('settings.changes',{count:dirty.length});
  byId('save-settings').disabled=settingsUi.saving;
  byId('discard-settings').disabled=settingsUi.saving;
}
function showSettingsSection(name) {
  const links=[...byId('settings-side').querySelectorAll('[data-section]')];
  const target=links.some(link=>link.dataset.section===name && !link.hidden) ? name : 'battery';
  settingsUi.section=target;
  links.forEach(link=>link.setAttribute('aria-current',String(link.dataset.section===target)));
  document.querySelectorAll('[data-settings-section]').forEach(section=>{section.hidden=section.dataset.settingsSection!==target;});
  if (target==='costs') void ensureCostSettings();
}
function ensureCostSettings() {
  if (settingsUi.costBaseline || settingsUi.costLoading) return settingsUi.costLoading ?? Promise.resolve();
  settingsUi.costLoading=loadCostSettings().then(()=>{settingsUi.costBaseline=formState(costForm);})
    .catch(error=>{byId('cost-saved').textContent=error.message;})
    .finally(()=>{settingsUi.costLoading=null;updateSavebar();});
  return settingsUi.costLoading;
}
const fieldLabel = name => [form,costForm].map(target=>target.elements.namedItem(name)).find(Boolean)?.closest('label') ?? null;
function clearFieldError(label) {
  label.classList.remove('invalid');
  const message=label.querySelector('.field-error');
  if (message) {message.hidden=true;message.textContent='';}
}
function showFieldErrors(fields,reason) {
  let first=null;
  for (const name of fields) {
    const label=fieldLabel(name);
    if (!label) continue;
    label.classList.add('invalid');
    let message=label.querySelector('.field-error');
    if (!message) {message=document.createElement('span');message.className='field-error';label.append(message);}
    const key='settings.error_'+reason;
    message.textContent=Object.hasOwn(language.messages,key) ? t(key) : t('settings.error_field');
    message.hidden=false;
    first??=label;
  }
  if (first) {
    showSettingsSection(first.closest('[data-settings-section]')?.dataset.settingsSection);
    first.closest('details')?.setAttribute('open','');
    first.querySelector('input,select')?.focus();
  }
  return first!==null;
}
function dailyValues() {
  const values = {};
  for (const name of ['reserve_w','regulation_interval_s','battery_min_soc','battery_max_soc','battery_pv_min_soc','battery_pv_wait_s','battery_pv_surplus_w']) values[name] = Number(form.elements[name].value);
  for (const name of ['battery_pv_support','battery_pv_start','holiday_catholic']) values[name] = form.elements[name].checked;
  for (const name of ['holiday_state','holiday_locality']) values[name] = form.elements[name].value;
  return values;
}
let toastTimer=null;
function toast(message) {
  const node=byId('toast');
  node.textContent=message;node.hidden=false;
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>{node.hidden=true;},3500);
}
async function saveSettings() {
  if (settingsUi.saving) return;
  document.querySelectorAll('#settings label.invalid').forEach(clearFieldError);
  const dirty=dirtySettings();
  if (!dirty.length) return;
  // Browser input constraints only catch unparsable or empty numbers; the backend validates the values.
  const unreadable=dirty.map(item=>(item.group==='daily' ? form : costForm).elements.namedItem(item.key))
    .filter(element=>element && !element.disabled && !element.checkValidity());
  if (unreadable.length) {showFieldErrors(unreadable.map(element=>element.name),'input');toast(t('settings.fix_fields'));return;}
  settingsUi.saving=true;updateSavebar();
  try {
    if (dirty.some(item=>item.group==='daily')) {await api('settings',dailyValues());settingsUi.baseline=formState(form);vehicleFormKey=null;}
    if (dirty.some(item=>item.group==='cost')) {await saveCostSettings();settingsUi.costBaseline=null;await ensureCostSettings();}
    toast(t('settings.saved'));
  } catch (error) {
    toast(showFieldErrors(error.fields ?? [],error.reason) ? t('settings.fix_fields') : error.message);
  } finally {
    settingsUi.saving=false;updateSavebar();
  }
  await refresh();
}
function discardSettings() {
  for (const [target,baseline] of [[form,settingsUi.baseline],[costForm,settingsUi.costBaseline]]) {
    if (!baseline) continue;
    for (const element of target.elements) {
      if (!element.name || !Object.hasOwn(baseline,element.name)) continue;
      if (element.type==='checkbox') element.checked=baseline[element.name]; else element.value=baseline[element.name];
    }
  }
  holidayFields();
  costForm.elements.pv_price_ct.disabled=costForm.elements.pv_price_source.value==='eos';
  document.querySelectorAll('#settings label.invalid').forEach(clearFieldError);
  updateSavebar();toast(t('settings.discarded'));
}

/* Storage and vehicle charging control are enabled separately; the backend reports which areas have a matching device. */
const areaControl={confirming:null,busy:false,result:''};
function controlAreas() {
  for (const area of document.querySelectorAll('[data-control-area]')) {
    const key=area.dataset.controlArea, view=snapshot.control?.[key] ?? {};
    const held=Boolean(view.enabled || view.release_pending), confirming=areaControl.confirming===key;
    const button=area.querySelector('[data-area-action="toggle"]');
    button.hidden=!view.available;
    button.disabled=!formReady || areaControl.busy || Boolean(areaControl.confirming);
    button.className='btn'+(held?'':' primary');
    button.textContent=t(held ? 'control.release' : 'control.take');
    area.querySelector('.control-area-state').textContent=!view.available ? t(`control.area_unavailable.${key}`)
      : t(view.release_pending ? 'control.area_releasing' : view.enabled ? 'control.area_on' : 'control.area_off');
    const box=area.querySelector('.control-area-confirm');
    box.hidden=!confirming || !view.available;
    if (box.hidden) continue;
    box.querySelector('p').textContent=t(held ? `control.area_release_confirm.${key}` : `control.area_confirm.${key}`);
    const confirmButton=box.querySelector('[data-area-action="confirm"]');
    confirmButton.className='btn '+(held?'danger':'primary');
    confirmButton.textContent=t(held ? 'control.release_confirm' : 'control.take_confirm');
    confirmButton.disabled=areaControl.busy;
    box.querySelector('[data-area-action="cancel"]').disabled=areaControl.busy;
  }
  byId('control-result').textContent=areaControl.result;
}

// Numeric source diagnostics: the backend supplies values and the balance rule.
function diagnosticNumber(value,unit) {
  if(!valid(value))return '—';
  const digits=unit==='W'?0:unit==='ct/kWh'?2:1;
  return `${value<0?'−':''}${decimal(Math.abs(value),digits)} ${html(unit)}`;
}
function diagnosticTable(head,rows,numeric=[1]) {
  return `<div class="diagnostics-scroll"><table class="diagnostics"><thead><tr>${head.map((label,index)=>`<th${numeric.includes(index)?' class="num"':''}>${label}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
function diagnosticSource(row) {
  if(!row.source)return '—';
  const kind=row.source_type?th(`diagnostics.source_${row.source_type}`)+': ':'';
  return kind+(row.source_type==='sensor'?`<code>${html(row.source)}</code>`:html(row.source));
}
function diagnosticStatus(row) {
  return row.available?th('diagnostics.ok'):th(`diagnostics.reason.${row.reason??'state_unavailable'}`,{age:row.max_age_s??'—'});
}
// Derived values in display order; shared by the table and the text export.
function diagnosticDerived(view) {
  const derived=view.derived??{},balance=view.balance;
  const rows=[['diagnostics.house_total',derived.house_total,false],['diagnostics.minus_car',derived.car,false],
    ['diagnostics.minus_heat',derived.heat,false],['diagnostics.house',derived.house,true],
    ['diagnostics.house_total_measured',derived.house_total_measured,false],
    ['diagnostics.residual',balance?.residual_w,true],['diagnostics.tolerance',balance?.tolerance_w,false]];
  const state=view.complete===false?'incomplete':!balance?'measured_missing':balance.balanced?'balanced':'unbalanced';
  const estimates=(view.estimates??[]).map(item=>[item.key==='house'?'diagnostics.house_label':`measurement.${item.key}`,`diagnostics.estimate.${item.reason}`]);
  return {rows,state,estimates};
}
function sourceDiagnostics(view) {
  if(!view)return `<p>${th('diagnostics.empty')}</p>`;
  const W='W',sources=diagnosticTable([th('diagnostics.measurement'),th('diagnostics.source'),th('diagnostics.value'),th('diagnostics.age'),th('diagnostics.status')],
    (view.sources??[]).map(row=>`<tr class="${row.available?'':'warn'}"><td>${th(`measurement.${row.key}`)}</td><td>${diagnosticSource(row)}</td><td class="num">${diagnosticNumber(row.value,row.unit)}</td><td class="num">${valid(row.age_s)?decimal(row.age_s,0)+' s':'—'}</td><td>${diagnosticStatus(row)}</td></tr>`),[2,3]);
  const {rows:derivedValues,state,estimates}=diagnosticDerived(view);
  const derivedRows=[...derivedValues.map(([key,value,strong])=>`<tr><td>${strong?`<strong>${th(key)}</strong>`:th(key)}</td><td class="num">${diagnosticNumber(value,W)}</td></tr>`),
    `<tr class="${state==='balanced'?'':'warn'}"><td colspan="2"><strong>${th(`diagnostics.${state}`)}</strong></td></tr>`];
  const estimateTable=estimates.length?`<h3>${th('diagnostics.estimates')}</h3>`+diagnosticTable([th('diagnostics.measurement'),th('diagnostics.reason')],
    estimates.map(([key,reason])=>`<tr><td>${th(key)}</td><td>${th(reason)}</td></tr>`),[]):'';
  const devices=(view.devices??[]).map(device=>`<h3>${html(device.name)}${device.plugin?' · '+html(device.plugin):''}</h3>
    <p class="footnote">${th(device.available?'diagnostics.device_ok':'diagnostics.device_incomplete')}${device.read_error?' · '+th('diagnostics.read_error',{error:device.read_error}):''}</p>`+
    diagnosticTable([th('diagnostics.measurement'),th('diagnostics.value')],Object.entries(device.values??{}).map(([key,value])=>
      `<tr><td>${th(`measurement.${key}`)}</td><td class="num">${diagnosticNumber(value,key==='battery_soc'?'%':W)}</td></tr>`))).join('');
  const vehicles=(view.vehicles??[]).length?`<h3>${th('diagnostics.vehicles')}</h3>`+diagnosticTable([th('source.vehicle'),th('measurement.car'),th('measurement.car_soc')],
    view.vehicles.map(item=>`<tr><td>${html(item.name)} · ${th(item.connected===false?'diagnostics.disconnected':'diagnostics.connected')}</td><td class="num">${diagnosticNumber(item.car,W)}</td><td class="num">${diagnosticNumber(item.car_soc,'%')}${item.soc_source==='estimate'?' ('+th('source.estimate')+')':''}</td></tr>`),[1,2]):'';
  return `<p class="footnote">${th('diagnostics.time',{time:view.time?new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,timeStyle:'medium'}).format(new Date(view.time)):'—'})}</p>${sources}
    <h3>${th('diagnostics.derived')}</h3>${diagnosticTable([th('diagnostics.measurement'),th('diagnostics.value')],derivedRows)}${estimateTable}
    ${devices?`<h3>${th('diagnostics.devices')}</h3>${devices}`:''}${vehicles}`;
}

// Plain-text copy of the same backend diagnostics for analysis outside the panel.
function diagnosticsText(view) {
  const plain=value=>String(value??'').replace(/[\r\n\t]+/g,' ').trim();
  const columns=(rows,right=[1])=>{
    const widths=rows[0].map((_,index)=>Math.max(...rows.map(row=>plain(row[index]).length)));
    return rows.map(row=>row.map((cell,index)=>right.includes(index)?plain(cell).padStart(widths[index]):plain(cell).padEnd(widths[index])).join('  ').trimEnd());
  };
  const number=(value,unit)=>valid(value)?`${decimal(value,unit==='W'?0:unit==='ct/kWh'?2:1)} ${unit}`:'—';
  const stamp=view?.time?new Intl.DateTimeFormat(language.locale,{timeZone:snapshot.zone,dateStyle:'short',timeStyle:'medium'}).format(new Date(view.time)):'—';
  const lines=[`EOS Energiezentrale · ${t('diagnostics.title')}`,`${t('diagnostics.time',{time:stamp})} (${view?.time??'—'})`,''];
  if(!view)return [...lines,t('diagnostics.empty')].join('\n')+'\n';
  const source=row=>row.source?(row.source_type?t(`diagnostics.source_${row.source_type}`)+': ':'')+row.source:'—';
  const status=row=>row.available?t('diagnostics.ok'):t(`diagnostics.reason.${row.reason??'state_unavailable'}`,{age:row.max_age_s??'—'});
  lines.push(...columns([[t('diagnostics.measurement'),t('diagnostics.source'),t('diagnostics.value'),t('diagnostics.age'),t('diagnostics.status')],
    ...(view.sources??[]).map(row=>[t(`measurement.${row.key}`),source(row),number(row.value,row.unit),valid(row.age_s)?decimal(row.age_s,0)+' s':'—',status(row)])],[2,3]));
  const {rows:derivedValues,state,estimates}=diagnosticDerived(view);
  lines.push('',t('diagnostics.derived'),...columns(derivedValues.map(([key,value])=>[t(key),number(value,'W')])),t(`diagnostics.${state}`));
  if(estimates.length)lines.push('',t('diagnostics.estimates'),...columns(estimates.map(([key,reason])=>[t(key),t(reason)]),[]));
  for(const device of view.devices??[]){
    lines.push('',`${t('diagnostics.devices')}: ${plain(device.name)}${device.plugin?' · '+plain(device.plugin):''} · ${t(device.available?'diagnostics.device_ok':'diagnostics.device_incomplete')}${device.read_error?' · '+t('diagnostics.read_error',{error:device.read_error}):''}`,
      ...columns(Object.entries(device.values??{}).map(([key,value])=>[t(`measurement.${key}`),number(value,key==='battery_soc'?'%':'W')])));
  }
  if((view.vehicles??[]).length)lines.push('',t('diagnostics.vehicles'),...columns(view.vehicles.map(item=>[`${plain(item.name)} · ${t(item.connected===false?'diagnostics.disconnected':'diagnostics.connected')}`,
    number(item.car,'W'),number(item.car_soc,'%')+(item.soc_source==='estimate'?' ('+t('source.estimate')+')':'')]),[1,2]));
  return lines.join('\n')+'\n';
}
async function copyDiagnostics() {
  const text=diagnosticsText(snapshot.source_diagnostics);
  try { await navigator.clipboard.writeText(text); }
  catch {
    // Fallback where the async clipboard is unavailable (e.g. plain HTTP).
    const area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');
    area.style.cssText='position:fixed;left:-9999px;top:0;';document.body.append(area);area.select();
    const copied=document.execCommand?.('copy');area.remove();
    if(!copied){byId('diagnostics-result').textContent=t('diagnostics.copy_failed');return;}
  }
  byId('diagnostics-result').textContent=t('diagnostics.copied');
}
function exportDiagnostics() {
  const view=snapshot.source_diagnostics;
  const stamp=(view?.time??new Date().toISOString()).slice(0,19).replace(/[:T]/g,'-');
  const link=document.createElement('a');
  link.href=URL.createObjectURL(new Blob([diagnosticsText(view)],{type:'text/plain;charset=utf-8'}));
  link.download=`eos-messwerte-${stamp}.txt`;document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  byId('diagnostics-result').textContent=t('diagnostics.exported',{file:link.download});
}

function settings() {
  // Without local edits the form follows backend changes, e.g. from native HA entities.
  if ('schedule' in snapshot.settings && (!formReady || !dirtySettings().some(item=>item.group==='daily'))) {
    fillForm();
    settingsUi.baseline=formState(form);
    formReady = true;
  }
  showSettingsSection(settingsUi.section);
  updateSavebar();
  controlAreas();
  byId('battery-limits-status').textContent = t(`settings.battery_limits_${snapshot.battery_limits_status??'unmanaged'}`, {
      minimum:snapshot.settings.battery_min_soc, maximum:snapshot.settings.battery_max_soc});
  byId('connections').innerHTML = `<dt>Akkudoktor EOS</dt><dd>${th(`status.${snapshot.eos_status??'connecting'}`)}</dd>
    <dt>InfluxDB</dt><dd>${th(`status.${history.status??'connecting'}`)}</dd>`;
  for(const [kind,plugin] of Object.entries(snapshot.plugins??{})){if(plugin)byId('connections').innerHTML+=`<dt>${html(plugin.name)}</dt><dd>${Object.entries(plugin.features).map(([feature,enabled])=>`${th(`plugin.feature.${feature}`)}: ${th(enabled?'plugin.yes':'plugin.no')}`).join(' · ')}${(plugin.measurements??[]).length?' · '+plugin.measurements.map(key=>th(`measurement.${key}`)).join(', '):''}</dd>`;}
  byId('connections').innerHTML+=batteryGroupDetails(snapshot.battery_group);
  byId('source-diagnostics').innerHTML=sourceDiagnostics(snapshot.source_diagnostics);

}
function render() {
  try {
    renderView();byId('startup-retry').hidden=true;byId('startup-details').hidden=true;return true;
  }catch(error){showStartupError('view',error);return false;}
}

function noticeText(notice, translate=t) {
  const values=(notice.measurements??[]).map(key=>translate('measurement.'+key)).join(', ');
  const message=translate(notice.message,{values});
  return (notice.vehicle_name?notice.vehicle_name+': ':'')+message;
}

let shownRoute=null;
const control={confirming:null,busy:false,result:''};
const statusContext=()=>({t,html,time:when,modeLabel,text:notice=>noticeText(notice)});
function browserNotices() {
  // Browser-side failures stay in the browser; they are shown, never reported to the backend.
  return [...(connectionFailure?[{severity:'warning',message:'notice.connection',browser:true}]:[]),
    ...(forecastOpenFailure?[{severity:'warning',message:'forecast.open_failed',browser:true}]:[])];
}
function resolvedText(item) {
  const key=item.code?.startsWith('sources_')?'notice_card.sources_resolved':'notice.'+item.code;
  return Object.hasOwn(language.messages,key)?t(key,{values:''}):t('notice.unknown');
}
const toneOf=severity=>({error:'crit',info:'info'}[severity]??'warn');
function renderStatus(route) {
  const ctx=statusContext(), ready='control_status' in snapshot;
  const notices=EosStatus.sortNotices([...(snapshot.notices??[]),...browserNotices()]);
  const bandNode=byId('status-band');
  bandNode.hidden=!ready;
  if(ready){
    const view=EosStatus.band(snapshot,ctx,{...control,ready:'schedule' in (snapshot.settings??{}),car:consumerEnabled('car')});
    bandNode.className='status-band tone-'+view.tone;
    bandNode.innerHTML=view.html;
  }
  const top=byId('top-notices'), pill=byId('notice-pill');
  top.hidden=route==='notices';
  top.innerHTML=route==='notices'?'':notices.slice(0,2).map(notice=>EosStatus.noticeCard(notice,ctx,{compact:true})).join('');
  pill.hidden=route==='notices'||!notices.length;
  if(notices.length){
    pill.className='notice-pill tone-'+toneOf(notices[0].severity);
    pill.innerHTML='<span class="sev">'+th('notice_card.'+(notices[0].severity??'warning'))+'</span><span class="txt">'+html(noticeText(notices[0]))
      +(notices.length>1?' · '+th('notice_card.more',{count:notices.length-1}):'')+'</span><span aria-hidden="true">→</span>';
  }
  const badge=byId('nav-badge');
  badge.hidden=!notices.length;badge.textContent=String(notices.length);
  badge.className='badge tone-'+toneOf(notices[0]?.severity);
  if(route!=='notices')return;
  byId('notice-count').textContent=notices.length?t('notice_card.open_count',{count:notices.length}):t('notice_card.none_open');
  byId('all-notices').innerHTML=notices.length?notices.map(notice=>EosStatus.noticeCard(notice,ctx)).join('')
    :'<div class="plan-panel"><b>'+th('notice_card.all_clear')+'</b><p class="footnote">'+th('notice_card.all_clear_text')+'</p></div>';
  const resolved=snapshot.resolved_notices??[];
  byId('resolved-panel').hidden=!resolved.length;
  byId('resolved-notices').innerHTML=resolved.map(item=>EosStatus.resolvedRow(item,{...ctx,text:resolvedText})).join('');
}
function renderView() {
  const requested = location.hash.slice(1);
  if (requested !== route) hideProbe();
  const vehicleRoute=requested.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===requested.slice(4));
  const usageRoute=billingRoute(requested);
  route = usageRoute || vehicleRoute || (pages.has(requested) && consumerEnabled(requested)) || ['settings','notices','pv'].includes(requested) ? requested : 'overview';
  document.querySelectorAll('[data-optional]').forEach(element=>{element.hidden=!consumerEnabled(element.dataset.optional);});
  const section=route.startsWith('car')?'car':['settings','notices'].includes(route)?route:'overview';
  document.querySelectorAll('nav a[data-route]').forEach(link=>{if(link.dataset.route===section)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  byId('usage').hidden=!usageRoute;
  byId('overview').hidden = route !== 'overview';
  byId('settings').hidden = route !== 'settings';
  byId('notices').hidden = route !== 'notices';
  byId('pv').hidden = route !== 'pv';
  updateSavebar();
  byId('detail').hidden = !pages.has(route) && !vehicleRoute;
  renderStatus(route);
  const entered = route !== shownRoute;
  // Routes share their names with section ids; keep the status band in view after navigation.
  if (route !== shownRoute) { if (shownRoute !== null) window.scrollTo(0,0); else requestAnimationFrame(()=>window.scrollTo(0,0)); shownRoute = route; }
  if (usageRoute) usageDetail(route.slice(6));
  else if (route === 'overview') overview();
  else if (route === 'settings') settings();
  else if (route === 'pv') {if (entered || (!forecastView && !forecastOpenFailure)) openPvView(); else forecastView?.update();}
  else if (route !== 'notices') detail(route);
}
let connectionFailure=false;
async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try { snapshot = await api('snapshot'); connectionFailure=false; }
  catch { connectionFailure=true; }
  finally { refreshing = false; render(); }
}
async function refreshHistory() {
  if (historyRefreshing) return;
  historyRefreshing = true;
  try { history = await api('history'); snapshot.accounting=await api('accounting',{period:'day',date:localDay(windowNow())}); }
  catch { /* API failures are reported by the authenticated bridge. */ }
  finally { historyRefreshing = false; render(); }
}
let forecastView=null;
let forecastOpenFailure=false;
const moduleLoading=new Map();
// bootstrap.js itself is requested without a build version, so a browser may run a cached older
// bootstrap that does not know newer modules. Load such a module with this app's build version.
function ensureModule(file,ready){
  if(ready())return Promise.resolve(ready());
  if(!moduleLoading.has(file)){
    const url=new URL('./'+file,location.href);
    url.searchParams.set('v',new URL(appScriptUrl).searchParams.get('v')||String(Date.now()));
    moduleLoading.set(file,new Promise((resolve,reject)=>{
      const script=document.createElement('script');let finished=false;
      const finish=error=>{
        if(finished)return;finished=true;clearTimeout(timer);script.remove();
        if(error){const failure=requestError('asset_mismatch','interface');failure.asset=file;reject(failure);}else resolve(ready());
      };
      const timer=setTimeout(()=>finish(true),10000);
      script.src=url.href;
      script.onload=()=>finish(!ready());
      script.onerror=()=>finish(true);
      document.head.append(script);
    }).catch(error=>{moduleLoading.delete(file);throw error;}));
  }
  return moduleLoading.get(file);
}
function ensureForecastModule(){
  return ensureModule('forecast.js',()=>typeof globalThis.EosForecast?.create==='function'?globalThis.EosForecast:null);
}
let pvViewLoading=false;
// The PV & weather page replaces the former weather dialog; failures stay a browser notice.
async function openPvView(){
  if(pvViewLoading)return;
  pvViewLoading=true;forecastOpenFailure=false;
  try{
    const module=await ensureForecastModule();
    if(!byId('pv-strip')||!byId('pv-days')||!byId('pv-effects'))throw requestError('asset_mismatch','interface');
    forecastView??=module.create({document,request:api,getSnapshot:()=>snapshot,t,html,decimal,getLocale:()=>language.locale,now:windowNow});
    forecastView.open();
  }catch{
    forecastOpenFailure=true;
  }finally{
    pvViewLoading=false;
    if(forecastOpenFailure)render();
  }
}
byId('flow-weather').addEventListener('click',()=>{location.hash='#pv';});
byId('vehicle-selector').addEventListener('change',()=>{vehicleFormKey=null;vehicleSettings();});
form.elements.holiday_state.addEventListener('change',holidayFields);
byId('add-charge-plan').addEventListener('click',()=>{
  if(byId('charge-plans').querySelectorAll('.charge-goal').length>=32)return;
  appendChargePlan({id:'plan_'+Date.now()+'_'+(++chargePlanCounter),active:true,schedule:'weekly',
    target_soc:80,departure_time:'07:30',weekdays:[0,1,2,3,4],holidays:false},true);
});
// Switches and limits save immediately; goals are edited together and saved with one button.
vehicleForm.addEventListener('change',event=>{
  const input=event.target;
  if(input?.name && ['pv','fast','phase_auto','pv_target_soc','fast_target_soc'].includes(input.name)) saveVehicleSwitch(input);
});
vehicleForm.addEventListener('submit',event=>{event.preventDefault();document.activeElement?.blur?.();});
goalForm.addEventListener('submit',async event=>{
  event.preventDefault();
  const values={charge_plans:chargePlanValues()};
  if(goalForm.dataset.vehicleId)values.vehicle_id=goalForm.dataset.vehicleId;
  try{await api('settings',values);vehicleFormKey=null;await refresh();byId('vehicle-saved').textContent=t('settings.saved');}
  catch(error){byId('vehicle-saved').textContent=error.message;}
});
byId('status-band').addEventListener('click', async event => {
  const action=event.target.closest('[data-control]')?.dataset.control;
  if(!action||control.busy)return;
  if(action==='take'||action==='release'){control.confirming=action;control.result='';}
  else if(action==='cancel')control.confirming=null;
  else if(action==='confirm'&&control.confirming){
    // The confirmation sends an explicit boolean; the backend confirms the device release.
    const enabled=control.confirming==='take';
    control.busy=true;render();
    try{await api('control',{enabled});control.result=t(enabled?'control.taken':'control.released');}
    catch(error){control.result=error.message;}
    control.busy=false;control.confirming=null;
    await refresh();
    return;
  }
  render();
  if(action==='take'||action==='release')byId('status-band').querySelector('[data-control="confirm"]')?.focus();
});
for (const target of [form,costForm]) {
  target.addEventListener('submit',event=>{event.preventDefault();void saveSettings();});
  for (const type of ['input','change']) target.addEventListener(type,event=>{
    const label=event.target.closest?.('label');
    if (label) clearFieldError(label);
    updateSavebar();
  });
}
byId('save-settings').addEventListener('click',()=>void saveSettings());
byId('discard-settings').addEventListener('click',discardSettings);
byId('settings-side').addEventListener('click',event=>{
  const link=event.target.closest('[data-section]');
  if (!link) return;
  event.preventDefault();
  showSettingsSection(link.dataset.section);
});
byId('overview-track').addEventListener('click',event => {
  const button = event.target.closest('[data-mode]');
  if (!button) return;
  byId('overview-track').querySelectorAll('[data-mode]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  byId('overview-track-detail').textContent = button.dataset.mode;
});
restoreNextDetails();
byId('car-plan').addEventListener('click',event => {
  const button = event.target.closest('[data-charge]');
  if (!button) return;
  byId('car-plan').querySelectorAll('[data-charge]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
  byId('car-plan-detail').textContent = button.dataset.mode;
});
document.addEventListener('click',event => {
  const link = event.target.closest('.to-plan, .plan-link[href="#car"]');
  if (!link) return;
  planScrollPending = true;
  if (link.classList.contains('to-plan')) {event.preventDefault();carView();}
});
byId('control-areas').addEventListener('click', async event => {
  const action=event.target.closest('[data-area-action]')?.dataset.areaAction;
  const key=event.target.closest('[data-control-area]')?.dataset.controlArea;
  if (!action || !key || areaControl.busy) return;
  if (action==='toggle') {areaControl.confirming=key;areaControl.result='';}
  else if (action==='cancel') areaControl.confirming=null;
  else if (action==='confirm' && areaControl.confirming===key) {
    // Only this area changes; the backend rejects an area without a matching device.
    const view=snapshot.control?.[key] ?? {}, enabled=!view.enabled && !view.release_pending;
    areaControl.busy=true;controlAreas();
    try {await api('control',{[key]:enabled});areaControl.result=t(enabled ? `control.area_taken.${key}` : `control.area_released.${key}`);}
    catch (error) {areaControl.result=error.message;}
    areaControl.busy=false;areaControl.confirming=null;
    await refresh();
    return;
  }
  controlAreas();
  if (action==='toggle') document.querySelector(`[data-control-area="${key}"] [data-area-action="confirm"]`)?.focus();
});
byId('diagnostics-copy').addEventListener('click',copyDiagnostics);
byId('diagnostics-export').addEventListener('click',exportDiagnostics);
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
  let loaded;
  for(let attempt=0;attempt<4;attempt++){
    try {loaded=await api('language'+query);break;}
    catch(error){
      if(!['not_ready','bridge_not_ready'].includes(error.code)||attempt===3)throw error;
      await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)));
    }
  }
  if(!loaded||typeof loaded.locale!=='string'||!loaded.messages||typeof loaded.messages!=='object')throw requestError('language_invalid','language');
  language={locale:loaded.locale,messages:{...startupMessages[startupLanguage],...loaded.messages}};
  startupStage='view';
  await ensureModule('status.js',()=>typeof globalThis.EosStatus?.band==='function'?globalThis.EosStatus:null);
  if(typeof globalThis.EosChartData?.powerFraction!=='function'||typeof globalThis.EosStatus?.band!=='function'||typeof initializeBilling!=='function'||!byId('cost-settings')?.elements.pv_price_source){
    const error=requestError('asset_mismatch','interface');error.asset=typeof globalThis.EosChartData?.powerFraction!=='function'?'chart-data.js':typeof globalThis.EosStatus?.band!=='function'?'status.js':typeof initializeBilling!=='function'?'accounting.js':'index.html';throw error;
  }
  document.documentElement.lang = language.locale;
  document.querySelectorAll('[data-i18n]').forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-aria]').forEach(element => {
    element.setAttribute('aria-label', t(element.dataset.i18nAria));
  });
  initializeBilling();
  window.addEventListener('hashchange',render);
  if(!render())return;
  refresh();
  refreshHistory();
  setInterval(refresh,5000);
  setInterval(refreshHistory,60000);
}
let startupStage='language';
start().catch(error=>showStartupError(startupStage,error));
