<script setup lang="ts">
import { ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useEOSSetup } from '@/composables/useEOSSetup'

defineProps<{ controlActive: boolean }>()
const { host } = useSettingsStore()
const { t } = host
const wizard = useEOSSetup(host)
const { loaded, draft, preview, step, busy, message, done, confirmed, locating, locationMessage } = wizard
const form = ref<HTMLFormElement | null>(null)
const steps = ['intro', 'location', 'pv', 'hardware', 'prices', 'planning', 'review']
const fields = {
  location: [['latitude', -90, 90, 'any'], ['longitude', -180, 180, 'any']],
  planning: [['horizon_hours', 1, 48, 1], ['prediction_hours', 24, 168, 1], ['interval_seconds', 60, 3600, 1]],
  plane: [['peakpower', .01, 1000, 'any'], ['surface_tilt', 0, 90, 'any'], ['surface_azimuth', 0, 360, 'any'],
    ['inverter_paco', 1, 1000000, 1], ['loss', 0, 100, 'any']],
} as const
function set(key: string, event: Event, text = false) {
  if (!draft.value) return
  const value = (event.target as HTMLInputElement).value
  draft.value[key] = text || value === '' ? value : Number(value)
}
function next() {
  if (!form.value?.reportValidity()) return
  if (step.value === 5) void wizard.review()
  else step.value++
}
function providerOptions(kind: string) { return loaded.value?.providers[kind] ?? [] }
function keep(kind: string) {
  return t('wizard.keep', { provider: loaded.value?.current_providers[kind] ?? t('wizard.none') })
}
function addPlane() {
  if (draft.value && draft.value['pv_provider'] === 'keep' && !loaded.value?.current_providers['pvforecast']) draft.value['pv_provider'] = providerOptions('pvforecast')[0] ?? 'keep'
  draft.value?.planes.push({ source: '', name: `PV ${(draft.value?.planes.length ?? 0) + 1}`, peakpower: 5,
    surface_tilt: 30, surface_azimuth: 180, inverter_paco: 5000, loss: 14 })
}
const MAX_PRICE_ZONES = 12
function addPriceZone() {
  const zones = draft.value?.price_zones
  if (!zones || zones.length >= MAX_PRICE_ZONES) return
  const last = zones.at(-1)
  const hour = last ? (Number(last.start.slice(0, 2)) + 1) % 24 : 0
  zones.push({ start: `${String(hour).padStart(2, '0')}:00`, price_ct: last?.price_ct ?? 30 })
}
function label(path: string) {
  const parts = path.split('/')
  const last = parts.at(-1) ?? ''
  const key = last === 'provider' ? parts[0] : last === 'windows' ? parts.at(-2) : last === 'hours' ? 'prediction_hours' : last
  const resource = parts[0] === 'devices' ? ` · ${parts[2]}` : ''
  return (host.lookup(`wizard.change_${key}`) ?? host.lookup(`wizard.field_${key}`) ?? t('wizard.setting')) + resource
}
function display(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return host.decimal(value, 6)
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return t(value ? 'wizard.yes' : 'wizard.no')
  if (Array.isArray(value)) return value.length ? value.map(item => {
    if (typeof item === 'object' && item !== null && 'start' in item && 'end' in item && 'value' in item) {
      return item.start === '00:00' && item.end === '24:00' ? `${display(item.value)} ${t('wizard.all_day')}` : `${String(item.start)}–${String(item.end)}: ${display(item.value)}`
    }
    if (typeof item === 'object' && item !== null && 'value' in item) return display(item.value)
    if (typeof item === 'object' && item !== null && 'peakpower' in item) return `${'name' in item ? String(item.name) : 'PV'}: ${display(item.peakpower)} kWp · ${'surface_azimuth' in item ? display(item.surface_azimuth) : '—'}° · ${'surface_tilt' in item ? display(item.surface_tilt) : '—'}°`
    return display(item)
  }).join('; ') : t('wizard.none')
  return t('wizard.setting')
}
</script>

<template>
  <section class="eos-wizard" data-eos-wizard>
    <h2>{{ t('wizard.title') }}</h2>
    <p>{{ t('wizard.intro') }}</p>
    <p class="footnote">{{ t('wizard.hardware_note') }}</p>
    <div v-if="controlActive" class="wizard-warning" role="status">
      <p>{{ t('wizard.pause_note') }}</p>
      <button type="button" class="btn" :disabled="busy" @click="wizard.release()">{{ t('wizard.release') }}</button>
    </div>
    <p v-if="message" class="field-error" role="alert">{{ message }}</p>
    <div v-if="done" role="status" class="wizard-success">
      <h3>{{ t('wizard.success') }}</h3><p>{{ t('wizard.success_note') }}</p>
      <button type="button" class="btn" :disabled="busy || controlActive" @click="wizard.load()">{{ t('wizard.restart') }}</button>
    </div>
    <template v-else>
      <ol class="wizard-progress" :aria-label="t('wizard.steps')">
        <li v-for="(name, index) in steps.slice(1)" :key="name" :aria-current="step === index + 1 ? 'step' : undefined" :class="{ current: step === index + 1 }">{{ t(`wizard.step_${name}`) }}</li>
      </ol>
      <button v-if="step === 0" type="button" class="btn primary" :disabled="busy || controlActive" @click="wizard.load()">{{ t(busy ? 'wizard.loading' : 'wizard.start') }}</button>
      <form v-else-if="draft && loaded" ref="form" @submit.prevent="next">
        <fieldset :disabled="busy || controlActive">
          <legend>{{ t(`wizard.step_${steps[step]}`) }}</legend>
          <template v-if="step === 1">
            <p class="footnote">{{ t('wizard.location_note') }}</p>
            <div class="wizard-actions"><button type="button" class="btn ghost" :disabled="locating" @click="wizard.locate()">{{ t(locating ? 'wizard.locating' : 'wizard.locate') }}</button><button type="button" class="btn ghost" @click="wizard.useHomeLocation()">{{ t('wizard.location_home') }}</button></div>
            <p class="footnote" role="status">{{ locationMessage }}</p>
            <div class="fields">
              <label v-for="[key, min, max, increment] in fields.location" :key="key">{{ t(`wizard.field_${key}`) }}<input :name="key" :value="draft[key]" type="number" :min="min" :max="max" :step="increment" required @input="set(key, $event)"></label>
              <label>{{ t('wizard.field_timezone') }}<input name="timezone" :value="draft['timezone']" type="text" required maxlength="64" @input="set('timezone', $event, true)"></label>
            </div>
          </template>
          <template v-if="step === 2">
            <p class="footnote">{{ t('wizard.pv_note') }}</p>
            <div class="fields">
              <label>{{ t('wizard.field_pv_provider') }}<select v-model="draft['pv_provider']"><option value="keep">{{ keep('pvforecast') }}</option><option v-for="provider in providerOptions('pvforecast')" :key="provider" :value="provider">{{ provider }}</option></select></label>
              <label>{{ t('wizard.field_weather_provider') }}<select v-model="draft['weather_provider']"><option value="keep">{{ keep('weather') }}</option><option v-for="provider in providerOptions('weather')" :key="provider" :value="provider">{{ provider }}</option></select></label>
            </div>
            <fieldset v-for="(plane, index) in draft.planes" :key="index" class="wizard-device">
              <legend>{{ plane.name }}</legend>
              <div class="fields"><label>{{ t('wizard.name') }}<input v-model="plane.name" required maxlength="60"></label>
                <label v-for="[key, min, max, increment] in fields.plane" :key="key">{{ t(`wizard.field_${key}`) }}<input v-model.number="plane[key]" type="number" :min="min" :max="max" :step="increment" required></label>
              </div><button type="button" class="btn ghost" @click="draft.planes.splice(index, 1)">{{ t('wizard.remove_plane') }}</button>
            </fieldset>
            <button type="button" class="btn ghost" :disabled="draft.planes.length >= 20" @click="addPlane">{{ t('wizard.add_plane') }}</button>
          </template>
          <template v-if="step === 3">
            <p class="footnote">{{ t('wizard.device_note') }}</p>
            <p v-if="!draft.devices.length">{{ t('wizard.no_devices') }}</p>
            <fieldset v-for="device in draft.devices" :key="`${device.kind}/${device.resource}`" class="wizard-device">
              <legend>{{ device.name === 'battery' ? t('device.battery') : device.name }} · {{ device.resource }}</legend>
              <div class="fields">
                <label>{{ t('wizard.field_profile') }}<select v-model="device.profile"><option :value="device.profile">{{ device.profile }}</option><option v-for="profile in loaded.profiles.battery.filter(name => name !== device.profile)" :key="profile" :value="profile">{{ profile }}</option></select></label>
                <label>{{ t('wizard.field_capacity_wh') }}<input v-model.number="device.capacity_wh" :readonly="device.locked?.includes('capacity_wh')" type="number" min="100" max="1000000" step="1" required></label>
                <label>{{ t('wizard.field_max_charge_power_w') }}<input v-model.number="device.charge_w" :readonly="device.locked?.includes('charge_w')" type="number" min="1" max="1000000" step="any" required></label>
                <label v-if="device.kind === 'batteries'">{{ t('wizard.field_max_discharge_power_w') }}<input v-model.number="device.discharge_w" :readonly="device.locked?.includes('discharge_w')" type="number" min="1" max="1000000" step="any" required></label>
              </div>
              <p v-if="device.kind === 'batteries'" class="footnote">{{ t('wizard.bounds', { min: device.min_soc, max: device.max_soc }) }}</p>
            </fieldset>
            <div v-if="draft.devices.some(device => device.kind === 'batteries') || draft.planes.length" class="fields">
              <label>{{ t('wizard.field_inverter_id') }}<input v-model="draft['inverter_id']" pattern="[A-Za-z0-9_.\-]{1,64}" required></label>
              <label>{{ t('wizard.field_inverter_profile') }}<select v-model="draft['inverter_profile']"><option :value="String(draft['inverter_profile'])">{{ draft['inverter_profile'] }}</option><option v-for="profile in loaded.profiles.inverter.filter(name => name !== draft?.['inverter_profile'])" :key="profile" :value="profile">{{ profile }}</option></select></label>
              <label>{{ t('wizard.field_inverter_power_w') }}<input name="inverter_power_w" :value="draft['inverter_power_w']" type="number" min="1" max="1000000" step="1" required @input="set('inverter_power_w', $event)"></label>
            </div>
          </template>
          <template v-if="step === 4">
            <p class="footnote">{{ t('wizard.prices_note') }}</p>
            <div class="fields">
              <label>{{ t('wizard.field_price_provider') }}<select v-model="draft['price_provider']"><option value="keep">{{ keep('elecprice') }}</option><option v-for="provider in providerOptions('elecprice')" :key="provider" :value="provider">{{ provider }}</option></select></label>
              <template v-if="draft['price_provider'] !== 'keep' && draft['price_provider'] !== 'ElecPriceFixed'">
                <label>{{ t('wizard.field_fee_ct') }}<input :value="draft['fee_ct']" type="number" min="0" max="1000" step="any" required @input="set('fee_ct', $event)"></label>
                <label>{{ t('wizard.field_vat_percent') }}<input :value="draft['vat_percent']" type="number" min="0" max="100" step="any" required @input="set('vat_percent', $event)"></label>
                <label v-if="draft['price_provider'] === 'ElecPriceEnergyCharts'">{{ t('wizard.field_bidding_zone') }}<select v-model="draft['bidding_zone']"><option v-for="zone in ['DE-LU', 'AT', 'CH', 'FR', 'NL', 'BE', 'DK1', 'DK2', 'PL', 'CZ']" :key="zone">{{ zone }}</option></select></label>
              </template>
            </div>
            <template v-if="draft['price_provider'] === 'ElecPriceFixed'">
              <p class="footnote">{{ t('wizard.price_zones_note') }}</p>
              <fieldset v-for="(zone, index) in draft.price_zones" :key="index" class="wizard-device" data-price-zone>
                <legend>{{ t('wizard.price_zone', { number: index + 1 }) }}</legend>
                <div class="fields">
                  <label>{{ t('wizard.field_zone_start') }}<input v-model="zone.start" :name="`zone_start_${index}`" type="time" step="60" required></label>
                  <label>{{ t('wizard.field_price_ct') }}<input v-model.number="zone.price_ct" :name="`zone_price_${index}`" type="number" min="0" max="1000" step="any" required></label>
                </div>
                <button v-if="draft.price_zones.length > 1" type="button" class="btn ghost" @click="draft.price_zones.splice(index, 1)">{{ t('wizard.remove_price_zone') }}</button>
              </fieldset>
              <button type="button" class="btn ghost" :disabled="draft.price_zones.length >= MAX_PRICE_ZONES" @click="addPriceZone">{{ t('wizard.add_price_zone') }}</button>
            </template>
            <div class="fields">
              <label>{{ t('wizard.field_feedin_ct') }}<select v-model="draft['feedin_provider']"><option value="keep">{{ keep('feedintariff') }}</option><option value="FeedInTariffFixed">{{ t('wizard.fixed_feedin') }}</option></select></label>
              <label v-if="draft['feedin_provider'] === 'FeedInTariffFixed'">{{ t('wizard.field_feedin_ct') }}<input :value="draft['feedin_ct']" type="number" min="0" max="1000" step="any" required @input="set('feedin_ct', $event)"></label>
              <label>{{ t('wizard.field_load_provider') }}<select v-model="draft['load_provider']"><option value="keep">{{ keep('load') }}</option><option v-for="provider in providerOptions('load')" :key="provider" :value="provider">{{ provider }}</option></select></label>
              <label v-if="draft['load_provider'] !== 'keep'">{{ t('wizard.field_annual_kwh') }}<input :value="draft['annual_kwh']" type="number" min="1" max="1000000" step="any" required @input="set('annual_kwh', $event)"></label>
            </div>
          </template>
          <template v-if="step === 5">
            <p class="footnote">{{ t('wizard.planning_note') }}</p>
            <div class="fields"><label v-for="[key, min, max, increment] in fields.planning" :key="key">{{ t(`wizard.field_${key}`) }}<input :name="key" :value="draft[key]" type="number" :min="min" :max="max" :step="increment" required @input="set(key, $event)"></label></div>
          </template>
          <template v-if="step === 6">
            <p>{{ t('wizard.review_note') }}</p>
            <div v-if="preview" class="wizard-review">
              <table><thead><tr><th>{{ t('wizard.setting') }}</th><th>{{ t('wizard.before') }}</th><th>{{ t('wizard.after') }}</th></tr></thead><tbody>
                <tr v-for="change in preview.changes" :key="change.path"><th scope="row">{{ label(change.path) }}</th><td>{{ display(change.before) }}</td><td>{{ display(change.after) }}</td></tr>
              </tbody></table>
              <p v-if="!preview.changes.length">{{ t('wizard.no_changes') }}</p>
              <label class="switch"><input v-model="confirmed" type="checkbox"><span>{{ t('wizard.confirm') }}</span></label>
              <button type="button" class="btn primary" :disabled="!confirmed" @click="wizard.apply()">{{ t('wizard.apply') }}</button>
            </div>
            <button v-else type="button" class="btn" @click="wizard.review()">{{ t('wizard.review_again') }}</button>
          </template>
          <div class="wizard-actions"><button type="button" class="btn ghost" @click="step = Math.max(1, step - 1)">{{ t('wizard.back') }}</button><button v-if="step < 6" type="submit" class="btn primary" :disabled="locating">{{ t(step === 5 ? 'wizard.review' : 'wizard.next') }}</button></div>
        </fieldset>
      </form>
      <p v-if="busy" role="status">{{ t('wizard.loading') }}</p>
    </template>
  </section>
</template>

