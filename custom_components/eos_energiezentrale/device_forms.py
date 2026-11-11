"""Native HA device management: choose a device, then its own plugin schema."""
import json
import probatio as vol
from homeassistant.helpers import selector

from .energy.devices import DeviceSite, REGISTRIES, device_rows
from .plugin_forms import configured, plugin_choices, plugin_object
from .flow_menus import show_menu


def choice(options):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=options))


class DeviceFormMixin:
    def _device_values(self):
        return self.values if hasattr(self,'values') else self._vehicle_values()

    async def _save_devices(self,rows):
        values={**self._device_values(),'devices':json.dumps(rows)}
        if hasattr(self,'values'):
            self.values=values
            return await self.async_step_devices()
        return self.async_create_entry(title='',data=values)

    async def async_step_device_done(self,user_input=None):
        if not hasattr(self,'values'): return self.async_abort(reason='invalid_plugin')
        return await self._step('hardware',{'devices':self.values['devices']})

    async def async_step_devices(self,user_input=None):
        return await show_menu(self,'config' if hasattr(self,'values') else 'options','devices',
                               ['device_add','device_edit','device_remove']+
                               (['device_done'] if hasattr(self,'values') else []))

    async def async_step_device_add(self,user_input=None):
        if user_input is not None:
            kind=user_input.get('kind')
            if kind=='wallbox' and not hasattr(self,'values'): return await self.async_step_vehicle_add()
            if kind not in REGISTRIES: return self.async_abort(reason='invalid_plugin')
            self._editing_device=None
            self._device_kind=kind
            return await self.async_step_device_plugin()
        return self.async_show_form(step_id='device_add',data_schema=vol.Schema({
            vol.Required('kind'):selector.SelectSelector(selector.SelectSelectorConfig(
                options=['battery','inverter']+([] if hasattr(self,'values') else ['wallbox']),
                translation_key='device_kind'))}))

    async def _choose_device(self,step_id,user_input):
        rows=device_rows(self._device_values())
        vehicles=self._vehicle_rows() if not hasattr(self,'values') else []
        if not rows and not vehicles: return self.async_abort(reason='no_devices')
        if user_input is None:
            return self.async_show_form(step_id=step_id,data_schema=vol.Schema({vol.Required('device_id'):choice(
                [{'value':row['id'],'label':row['name']} for row in rows]+
                [{'value':'vehicle:'+row['id'],'label':row.get('name',row['id'])+' (Wallbox)'} for row in vehicles])}))
        identity=user_input.get('device_id')
        if not any(row['id']==identity for row in rows) and not any('vehicle:'+row['id']==identity for row in vehicles):
            return self.async_abort(reason='no_devices')
        return identity

    async def async_step_device_edit(self,user_input=None):
        selected=await self._choose_device('device_edit',user_input)
        if not isinstance(selected,str): return selected
        if selected.startswith('vehicle:'):
            return await self.async_step_vehicle_edit({'vehicle_id':selected[8:]})
        old=next(row for row in device_rows(self._device_values()) if row['id']==selected)
        self._editing_device=selected
        self._device_kind=old['kind']
        return await self.async_step_device_plugin()

    async def async_step_device_remove(self,user_input=None):
        selected=await self._choose_device('device_remove',user_input)
        if not isinstance(selected,str): return selected
        if selected.startswith('vehicle:'):
            return await self.async_step_vehicle_remove({'vehicle_id':selected[8:]})
        values=self._device_values()
        rows=[row for row in device_rows(values) if row['id']!=selected]
        try: DeviceSite(None,rows)
        except (ValueError,TypeError,KeyError):
            return self.async_show_form(step_id='device_remove',data_schema=vol.Schema({
                vol.Required('device_id'):choice([{'value':row['id'],'label':row['name']} for row in device_rows(values)])}),
                errors={'base':'invalid_config'})
        return await self._save_devices(rows)

    async def async_step_device_plugin(self,user_input=None):
        registry=REGISTRIES[self._device_kind]
        old=next((row for row in device_rows(self._device_values()) if row['id']==self._editing_device),{})
        if user_input is not None:
            plugin=user_input.get('plugin')
            if plugin not in registry: return self.async_abort(reason='invalid_plugin')
            self._device_plugin=plugin
            return await self.async_step_device_parameters()
        default=old.get('plugin',next(iter(registry)))
        return self.async_show_form(step_id='device_plugin',data_schema=vol.Schema({
            vol.Required('plugin',default=default):choice(plugin_choices(registry))}))

    async def async_step_device_parameters(self,user_input=None):
        values=self._device_values();rows=device_rows(values)
        old=next((row for row in rows if row['id']==self._editing_device),{})
        identity=self._editing_device
        index=1
        while any(row['id']==f'device{index}' for row in rows): index+=1
        defaults={'id':identity or f'device{index}','name':old.get('name',''),
            'grid_source':old.get('grid_source',False),'capacity_wh':old.get('capacity_wh',0),
            'charge_w':old.get('charge_w',values['battery_charge_w']),
            'discharge_w':old.get('discharge_w',values['battery_discharge_w'])}
        factory=REGISTRIES[self._device_kind][self._device_plugin]
        old_parameters=old.get('parameters',{}) if old.get('plugin')==self._device_plugin else {}
        errors={}
        if user_input is not None:
            try:
                row={key:user_input[key] for key in ('id','name','grid_source')}
                if identity and row['id']!=identity: raise ValueError('Keep stable device ID')
                if not identity and any(item['id']==row['id'] for item in rows): raise ValueError('Duplicate device ID')
                row.update(kind=self._device_kind,plugin=self._device_plugin,
                           parameters=configured(factory,user_input.get('parameters',{})))
                if self._device_kind=='battery':
                    row.update({key:user_input[key] for key in ('capacity_wh','charge_w','discharge_w')})
                updated=[row if item['id']==identity else item for item in rows]+([] if identity else [row])
                DeviceSite(None,updated)
                return await self._save_devices(updated)
            except (ValueError,TypeError,KeyError): errors={'base':'invalid_config'}
        displayed={**defaults,**(user_input or {})}
        fields={vol.Required(key,default=displayed[key]):str for key in ('id','name')}
        fields[vol.Required('grid_source',default=displayed['grid_source'])]=selector.BooleanSelector()
        if self._device_kind=='battery':
            for key in ('capacity_wh','charge_w','discharge_w'):
                fields[vol.Required(key,default=displayed[key])]=selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0,max=1000000,mode=selector.NumberSelectorMode.BOX))
        control,params=plugin_object(factory,(user_input or {}).get('parameters',old_parameters))
        if factory.configuration: fields[vol.Required('parameters',default=params)]=control
        return self.async_show_form(step_id='device_parameters',data_schema=vol.Schema(fields),errors=errors)
