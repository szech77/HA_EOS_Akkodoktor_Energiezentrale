'use strict';

const byId = id => document.getElementById(id);
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
  if (event.data.error) pending.reject(requestError(event.data.error,pending.action));
  else pending.resolve(event.data.result);
});
function requestError(code,action) {
  const safeCode=typeof code==='string'&&/^[a-z_]{1,64}$/.test(code)?code:'request_failed';
  const error=Error(`${t(`action.${action}`)}: ${language.messages[`error.${safeCode}`]??t('error.request')}`);
  error.code=safeCode;error.action=action;return error;
}

function showStartupError(stage,error) {
  byId('notice').textContent=`${t(`startup.${stage}`)}. ${error?.code?error.message:t('startup.unexpected')}`;
  const retry=byId('startup-retry');if(retry){retry.textContent=t('startup.retry');retry.hidden=false;}
  if(byId('startup-details'))byId('startup-details').hidden=false;
  if(byId('startup-details-title'))byId('startup-details-title').textContent=t('startup.details');
  if(byId('startup-detail'))byId('startup-detail').textContent=[stage,error?.code??error?.name??'Error',error?.asset??'',error?.code?'':String(error?.message??'').slice(0,200)].filter(Boolean).join(' · ');
  for(const id of ['overview','detail','settings','usage'])if(byId(id))byId(id).hidden=true;
  console.error('EOS UI failed during '+stage,error);
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

function nextPlan(key) {
  const now = windowNow();
  const current = snapshot.live[key + '_mode'];
  return (snapshot.plan[key] ?? []).find(item => Date.parse(item.time) > now && item.mode !== current);
}

const localDay = value => new Intl.DateTimeFormat('sv-SE', {timeZone:snapshot.zone}).format(new Date(value));

function solarRemaining() {
  const energy = (snapshot.pv_daily_forecast ?? EosChartData.dailySolar(snapshot.forecast,windowNow(),snapshot.zone))[0]?.kwh;
  return valid(energy) ? `${decimal(energy)} ${t('unit.kwh')}` : null;
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
  const days=snapshot.pv_daily_forecast ?? EosChartData.dailySolar(snapshot.forecast,now,snapshot.zone);
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

function vehicleActive(vehicle) {
  if (vehicle.vehicles?.length) return vehicle.vehicles.some(vehicleActive);
  return vehicle.live?.car_connected !== false;
}

function vehicleStatus(vehicle) {
  return t(vehicle.live?.car_available === false ? 'vehicle.unavailable' : 'vehicle.disconnected');
}

function carIcon(soc) {
  const known=valid(soc) && soc>=0 && soc<=100;
  return `<svg class="vehicle-soc-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m5 9 1.5-4h11L19 9M4 17v3m16-3v3"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M6 13h2m8 0h2"/>${known ? `<rect class="car-soc-track" x="7.5" y="6.2" width="9" height="1.8" rx=".4"/><rect class="car-soc-fill" x="7.5" y="6.2" width="${(9*soc/100).toFixed(3)}" height="1.8" rx=".4"/>` : ''}</svg>`;
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

function updatePowerRing(node,key,value) {
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
  const reference=snapshot.power_reference??{};
  const fraction=key==='heat'?(valid(snapshot.live.heat_load)?Math.max(0,Math.min(1,snapshot.live.heat_load)):null)
    :EosChartData.powerFraction(value,reference[key==='battery'?(value<0?'battery_discharge':'battery_charge'):key]);
  ring.querySelector('.ring-value').setAttribute('stroke-dasharray',`${fraction===null?0:fraction*100} 100`);
  ring.dataset.fraction=fraction===null?'':String(fraction);
  const label=fraction===null?t('ring.unknown'):t('ring.load',{percent:decimal(fraction*100)});
  node.title=[node.title,label].filter(Boolean).join(' · ');
  node.setAttribute('aria-label',node.getAttribute('aria-label')+' · '+label);
}

function overview() {
  dayBalance();
  byId('vehicle-cards').innerHTML=vehicleCards();
  const live = snapshot.live;
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
    weatherNode.setAttribute('aria-label', description);
    weatherNode.title = description;
  }
  byId('connection').textContent = snapshot.control_waiting ? t('control.waiting') : snapshot.armed ? Object.keys(snapshot.eos_cache ?? {}).length ? t('control.cached_eos') : t('control.active') : t('control.read_only');
  const flowAge=Math.max(0,...['solar','grid','car','battery'].map(key=>snapshot.flow_display?.[key]?.age_s ?? 0));
  byId('live-time').textContent = live.time ? time(Date.parse(live.time)-flowAge*1000) : t('status.no_readings');
  byId('overview-kpis').innerHTML = cards([
    [t('metric.pv_today'),solarToday(),remaining ? t('metric.remaining',{energy:remaining}) : t('metric.available_intervals')],
    [t('metric.price_now'),price(displayed('price')),t('metric.import')],
    [t('metric.grid_connection'),displayedPower('grid'),valid(displayed('grid')) ? displayed('grid') < 0 ? t('metric.export') : displayed('grid') > 0 ? t('metric.import') : t('metric.no_grid_flow') : '—']
  ]);
  const names = {solar:t('node.solar'), grid:t('node.grid'), battery:t('node.battery'), house:t('node.house'), car:t('node.car'), heat:t('device.heat')};
  Object.keys(names).forEach(key => {
    const node = document.querySelector(`[data-node="${key}"]`);
    const flow = document.querySelector(`[data-flow="${key}"]`);
    node.hidden = !consumerEnabled(key);
    flow.style.display = consumerEnabled(key) ? "" : "none";
    if (!consumerEnabled(key)) return;
    const inactiveCar = key === 'car' && !vehicleActive(snapshot);
    node.classList.toggle('vehicle-inactive', inactiveCar);
    const retained = snapshot.flow_display?.[key] ?? snapshot.display?.[key];
    const stale = valid(retained?.value) && (retained.transition_held || retained.aligned || !valid(live[key]));
    const value = inactiveCar ? null : stale ? retained.value : live[key];
    const soc = key === 'car' && snapshot.vehicles?.length ? undefined : displayed(key + '_soc');
    if (key === 'car') {
      const knownSoc=valid(soc) && soc>=0 && soc<=100;
      node.querySelector('.car-soc')?.toggleAttribute('hidden',!knownSoc);
      node.querySelector('.car-soc-fill')?.setAttribute('width',knownSoc ? String(9*soc/100) : '0');
    }
    if (key === 'battery') {
      const knownSoc=valid(soc) && soc>=0 && soc<=100;
      const minimum=snapshot.settings.battery_min_soc;
      const low=knownSoc && valid(minimum) && soc<=minimum;
      const filled=knownSoc ? Math.ceil(soc/20) : 0;
      node.classList.toggle('battery-low',low);
      node.querySelectorAll('.battery-bar').forEach((bar,index)=>bar.classList.toggle('filled',index<filled));
    }
    const direction = key === 'grid' ? value < 0 ? t('metric.export') : t('metric.import')
      : key === 'battery' ? value < 0 ? t('metric.discharging') : t('mode.charging') : '';
    node.querySelector('strong').textContent = inactiveCar ? vehicleStatus(snapshot) : (stale && retained.estimated ? '≈ ' : '') + power(value);
    let ageNote = node.querySelector('.reading-age');
    if (!ageNote) {
      ageNote = document.createElement('small');
      ageNote.className = 'reading-age';
      node.append(ageNote);
    }
    ageNote.hidden = inactiveCar || !stale || (retained.aligned && retained.age_s<10);
    ageNote.textContent = stale ? t(retained.transition_held ? 'metric.waiting_car_power' : retained.aligned ? 'metric.aligned_age' : retained.estimated ? 'metric.estimated_age' : 'metric.last_report_age',
      {minutes:Math.ceil(retained.age_s / 60)}) : '';
    node.title = ageNote.textContent;
    if (key === "car" && snapshot.vehicles?.length) names.car=t("fleet.vehicles",{count:snapshot.vehicles.length});
    node.querySelector('span:nth-child(2)').textContent = valid(soc) ? `${names[key]} · ${percent(soc)}` : names[key];
    node.setAttribute('aria-label', [names[key],power(value),value ? direction : ''].filter(Boolean).join(' · '));
    if (['battery','car'].includes(key) && valid(soc)) {
      const warning=node.classList.contains('battery-low') ? t('battery.minimum_reached') : '';
      node.setAttribute('aria-label',[node.getAttribute('aria-label'),t('chart.soc')+' '+percent(soc),warning].filter(Boolean).join(' · '));
    }
    updatePowerRing(node,key,value);
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
    grid:[[t('metric.direction'),valid(displayed('grid')) ? displayed('grid') < 0 ? t('metric.export') : t('metric.import') : '—',t('metric.grid_connection')]],
    battery:[[t('chart.soc'),percent(displayed("battery_soc")),t('metric.measured')],[t('metric.eos_mode'),modeLabel(live.battery_mode),stateLabel('mode',live.battery_control)]],
    house:[[t('metric.house_total'),displayedPower("house_total"),t('metric.house_includes')]],
    car:[[t('chart.soc'),percent(displayed("car_soc")),stateLabel('source',live.soc_source)],[t('metric.target'),percent(snapshot.settings.target_soc),live.departure ? time(live.departure) : t('metric.no_departure')]],
    heat:[]
  };
  const inactiveCar = key === 'car' && !vehicleActive(snapshot);
  byId('detail-kpis').innerHTML = cards([[t('metric.current_power'),inactiveCar ? vehicleStatus(snapshot) : displayedPower(key),inactiveCar ? '' : displayAge(key) ?? (key === 'car' ? stateLabel('mode',live.car_control ?? live.car_status) : t('metric.measured'))],...metadata[key]]);
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
  byId('ownership').textContent = snapshot.control_waiting ? t('control.waiting') : snapshot.armed ? Object.keys(snapshot.eos_cache ?? {}).length ? t('control.cached_eos') : t('control.active') : t('control.read_only');
  byId('control').textContent = snapshot.armed || snapshot.release_pending ? t('control.release') : t('control.take');
  byId('control').disabled = !formReady;
  const limits = snapshot.battery_limits;
  byId('battery-limits-status').textContent = snapshot.errors.battery_limits ? t('settings.battery_limits_failed')
    : limits?.confirmed ? t('settings.battery_limits_confirmed', {
      minimum:snapshot.settings.battery_min_soc, maximum:snapshot.settings.battery_max_soc})
    : limits?.managed ? t('settings.battery_limits_pending') : t('settings.battery_limits_unmanaged');
  byId('connections').innerHTML = `<dt>Akkudoktor EOS</dt><dd>${snapshot.errors.eos ? th('status.fetch_failed') : snapshot.plan.battery?.length || snapshot.plan.car?.length ? th('status.plan_available') : th('status.no_plan')}</dd>
    <dt>InfluxDB</dt><dd>${!snapshot.influx_configured ? th('status.local_history') : history.influx_error ? th('status.fetch_failed') : history.influx.length ? th('status.history_available') : th('status.no_samples')}</dd>`;
  for(const [kind,plugin] of Object.entries(snapshot.plugins??{})){if(plugin)byId('connections').innerHTML+=`<dt>${html(plugin.name)}</dt><dd>${Object.entries(plugin.features).map(([feature,enabled])=>`${th(`plugin.feature.${feature}`)}: ${th(enabled?'plugin.yes':'plugin.no')}`).join(' · ')}${(plugin.measurements??[]).length?' · '+plugin.measurements.map(key=>th(`measurement.${key}`)).join(', '):''}</dd>`;}
  const wallbox=snapshot.vehicles?.find(item=>item.id===selector.value)?.plugins?.wallbox??snapshot.plugins?.wallbox;
  form.elements.phase_auto.disabled=wallbox?.features?.phase_switching===false;
  if(form.elements.phase_auto.disabled)form.elements.phase_auto.checked=false;
}
function render() {
  try {
    renderView();byId('startup-retry').hidden=true;byId('startup-details').hidden=true;return true;
  }catch(error){showStartupError('view',error);return false;}
}

function sourceConfigurationNotice(configuration, translate) {
  const notices = [];
  for (const kind of ['missing','unavailable']) {
    const names = (configuration?.[kind] ?? []).map(key => translate(`measurement.${key}`));
    if (names.length) notices.push(translate(`notice.sources_${kind}`,{values:names.join(', ')}));
  }
  return notices.join(' · ');
}

function renderView() {
  const requested = location.hash.slice(1);
  if (requested !== route) hideProbe();
  const vehicleRoute=requested.startsWith('car/') && snapshot.vehicles?.some(item=>item.id===requested.slice(4));
  const usageRoute=billingRoute(requested);
  route = usageRoute || vehicleRoute || (pages.has(requested) && consumerEnabled(requested)) || requested === 'settings' ? requested : 'overview';
  byId('usage').hidden=!usageRoute;
  byId('overview').hidden = route !== 'overview';
  byId('settings').hidden = route !== 'settings';
  byId('detail').hidden = !pages.has(route) && !vehicleRoute;
  const errors = Object.keys(snapshot.errors);
  const errorAreas = {eos:Object.keys(snapshot.eos_cache??{}).length?'notice.eos_cached':'notice.eos',accounting:'notice.accounting',device_pending:'notice.device_pending',goal:'notice.goal',runtime:'notice.runtime',forecast:'notice.forecast',
    release:'notice.release',battery_limits:'notice.battery_limits',vehicle_limits:'notice.vehicle_limits',wallbox:'notice.wallbox',wallbox_stop:'notice.wallbox_stop',control_persistence:'notice.control_persistence',connection:'notice.connection'};
  const vehicleWarnings = (snapshot.vehicles ?? []).slice(1).flatMap(vehicle =>
    Object.keys(vehicle.errors ?? {}).filter(key => ['wallbox','wallbox_stop','vehicle_limits','goal'].includes(key))
      .map(key => `${vehicle.name}: ${t(errorAreas[key])}`));
  const warnings = [...errors.map(key => errorAreas[key] ? t(errorAreas[key]) : key.toUpperCase()), ...vehicleWarnings];
  byId('notice').textContent = warnings.length ? `${t('notice.check')} · ${warnings.join(', ')}` : '';
  const sourceNotice = sourceConfigurationNotice(snapshot.source_configuration,t);
  if (sourceNotice) byId('notice').textContent += `${warnings.length?' · ':''}${sourceNotice}`;
  if (usageRoute) usageDetail(route.slice(6));
  else if (route === 'overview') overview();
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
  try { history = await api('history'); dayAccounting=await api('accounting',{period:'day',date:localDay(windowNow())}); }
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
  if(typeof globalThis.EosChartData?.powerFraction!=='function'||typeof initializeBilling!=='function'||!byId('cost-settings')?.elements.pv_price_source){
    const error=requestError('asset_mismatch','interface');error.asset=typeof globalThis.EosChartData?.powerFraction!=='function'?'chart-data.js':typeof initializeBilling!=='function'?'accounting.js':'index.html';throw error;
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
