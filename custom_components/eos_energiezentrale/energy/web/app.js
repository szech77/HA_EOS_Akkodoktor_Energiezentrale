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
const valid = Number.isFinite;
const decimal = (value, digits = 1) => new Intl.NumberFormat(language.locale, {maximumFractionDigits: digits}).format(value);
const power = value => valid(value) ? `${decimal(Math.abs(value) / 1000, 2)} ${t('unit.kw')}` : '—';
const percent = value => valid(value) ? `${decimal(value)} %` : '—';
const price = value => valid(value) ? `${decimal(value)} ${t('unit.price')}` : '—';
const time = value => value ? new Intl.DateTimeFormat(language.locale, {timeZone: snapshot.zone, dateStyle:'short', timeStyle:'short'}).format(new Date(value)) : '—';
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

const localDay = value => new Intl.DateTimeFormat('sv-SE', {timeZone:snapshot.zone}).format(new Date(value));

const consumerEnabled = key => !["car","heat"].includes(key) || snapshot.features?.[key] !== false;

// Overview: the day balance stays in accounting.js; figures, flow and EOS plan are a Vue view (EosOverview).
let overviewView=null;
function overview() {
  dayBalance();
  overviewView??=globalThis.EosOverview.create({document,request:api,getSnapshot:()=>snapshot,t,decimal,
    getLocale:()=>language.locale,now:windowNow,lookup:name=>language.messages[name],refresh});
  overviewView.show();
}

// Vehicle pages are #car/<encoded id>; the energy flow and the fleet cards link there.
function routeVehicleId(key) {
  if (!key.startsWith('car/')) return null;
  try {return decodeURIComponent(key.slice(4));} catch {return null;}
}
// With one vehicle the Auto page is that vehicle's page, the same as from the energy flow.
function singleVehicleRoute(requested, vehicles) {
  return requested==='car' && vehicles.length===1 ? 'car/'+encodeURIComponent(vehicles[0].id) : null;
}
// The device pages (PV, grid, battery, house, heat pump, energy and car) are a Vue view (EosDevice).
let deviceView=null, deviceOpenFailure=false, deviceLoading=false;
function deviceModule() {
  return typeof globalThis.EosDevice?.create==='function' ? globalThis.EosDevice : null;
}
function showDeviceView(key) {
  const module=deviceModule();
  if (!module) {
    // A cached bootstrap may have omitted the bundle; load it once and render again.
    if (!deviceLoading && !deviceOpenFailure) {
      deviceLoading=true;
      ensureModule('vue/eos-vue.js',deviceModule).catch(()=>{deviceOpenFailure=true;}).finally(()=>{deviceLoading=false;render();});
    }
    return;
  }
  try {
    deviceView??=module.create({document,request:api,getSnapshot:()=>snapshot,getHistory:()=>history,t,decimal,
      getLocale:()=>language.locale,now:windowNow,lookup:name=>language.messages[name],refresh});
    deviceView.show(key,{scrollToPlan:planScrollPending});
    planScrollPending=false;
  } catch {
    // Failures stay a browser notice; the rest of the panel keeps working.
    deviceOpenFailure=true;
  }
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
// Set by "To the charging plan" links outside the car page; the car view scrolls once shown.
let planScrollPending=false;
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
    if (dirty.some(item=>item.group==='daily')) {await api('settings',dailyValues());settingsUi.baseline=formState(form);}
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
    view.vehicles.map(item=>`<tr><td>${html(item.name)} · ${th(item.connected===false?'diagnostics.disconnected':'diagnostics.connected')}</td><td class="num">${diagnosticNumber(item.car,W)}</td><td class="num">${diagnosticNumber(item.car_soc,'%')}${item.soc_source==='estimate'?' ('+th('source.estimate')+')':''}${valid(item.car_range)?' · '+diagnosticNumber(item.car_range,'km'):''}</td></tr>`),[1,2]):'';
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

let shownRoute=null;
function browserNotices() {
  // Browser-side failures stay in the browser; they are shown, never reported to the backend.
  return [...(connectionFailure?[{severity:'warning',message:'notice.connection',browser:true}]:[]),
    ...(forecastOpenFailure?[{severity:'warning',message:'forecast.open_failed',browser:true}]:[]),
    ...(deviceOpenFailure?[{severity:'warning',message:'device.open_failed',browser:true}]:[])];
}
// Status band, notices and the notices page (EosStatus); loaded with the Vue bundle before start.
let statusView=null;
function renderStatus(route) {
  statusView??=globalThis.EosStatus.create({document,request:api,getSnapshot:()=>snapshot,getBrowserNotices:browserNotices,
    t,decimal,getLocale:()=>language.locale,now:windowNow,lookup:name=>language.messages[name],refresh});
  statusView.show(route);
}
function renderView() {
  const requested = location.hash.slice(1);
  const vehicles=consumerEnabled('car') ? snapshot.vehicles ?? [] : [];
  const single=singleVehicleRoute(requested,vehicles);
  // replace keeps the back button on the previous page; the hash change renders again.
  if (single) {location.replace('#'+single);return;}
  const vehicleId=routeVehicleId(requested);
  const vehicleRoute=vehicleId!==null && vehicles.some(item=>item.id===vehicleId);
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
  // A new visit may retry a device view that failed to open.
  if (entered) deviceOpenFailure=false;
  // Routes share their names with section ids; keep the status band in view after navigation.
  if (route !== shownRoute) { if (shownRoute !== null) window.scrollTo(0,0); else requestAnimationFrame(()=>window.scrollTo(0,0)); shownRoute = route; }
  if (usageRoute) usageDetail(route.slice(6));
  else if (route === 'overview') overview();
  else if (route === 'settings') settings();
  else if (route === 'pv') {if (entered || (!forecastView && !forecastOpenFailure)) openPvView(); else forecastView?.update();}
  else if (route !== 'notices') showDeviceView(route);
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
  // The PV & weather view is a Vue page (frontend/src/views/PvWeatherView.vue).
  return ensureModule('vue/eos-vue.js',()=>typeof globalThis.EosForecast?.create==='function'?globalThis.EosForecast:null);
}
let pvViewLoading=false;
// The PV & weather page replaces the former weather dialog; failures stay a browser notice.
async function openPvView(){
  if(pvViewLoading)return;
  pvViewLoading=true;forecastOpenFailure=false;
  try{
    const module=await ensureForecastModule();
    if(!byId('pv-view'))throw requestError('asset_mismatch','interface');
    forecastView??=module.create({document,request:api,getSnapshot:()=>snapshot,t,html,decimal,getLocale:()=>language.locale,now:windowNow});
    forecastView.open();
  }catch{
    forecastOpenFailure=true;
  }finally{
    pvViewLoading=false;
    if(forecastOpenFailure)render();
  }
}
form.elements.holiday_state.addEventListener('change',holidayFields);
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
document.addEventListener('click',event => {
  if (event.target.closest('.plan-link[href="#car"]')) planScrollPending = true;
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
  // The Vue bundle renders status, overview and device pages; a cached bootstrap may have omitted it.
  const vueReady=()=>typeof globalThis.EosStatus?.create==='function'&&typeof globalThis.EosOverview?.create==='function'?globalThis.EosStatus:null;
  await ensureModule('vue/eos-vue.js',vueReady);
  if(!vueReady()||typeof initializeBilling!=='function'||!byId('cost-settings')?.elements.pv_price_source){
    const error=requestError('asset_mismatch','interface');error.asset=!vueReady()?'vue/eos-vue.js':typeof initializeBilling!=='function'?'accounting.js':'index.html';throw error;
  }
  document.documentElement.lang = language.locale;
  document.querySelectorAll('[data-i18n]').forEach(element => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-aria]').forEach(element => {
    element.setAttribute('aria-label', t(element.dataset.i18nAria));
  });
  initializeBilling();
  // The title bar stays at the top; sticky panels and jump targets keep clear of its height.
  const header=document.querySelector('header');
  const headerHeight=()=>document.documentElement.style.setProperty('--header-h',header.offsetHeight+'px');
  headerHeight();
  if(typeof ResizeObserver==='function')new ResizeObserver(headerHeight).observe(header);
  window.addEventListener('hashchange',render);
  if(!render())return;
  refresh();
  refreshHistory();
  setInterval(refresh,5000);
  setInterval(refreshHistory,60000);
}
let startupStage='language';
start().catch(error=>showStartupError(startupStage,error));
