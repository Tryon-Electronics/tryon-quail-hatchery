"""Single-instance setup flow for the downloadable hatchery bundle."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

DOMAIN = 'tryon_quail_hatchery'


class HatcheryConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            if not self.hass.services.has_service('pyscript', 'reload'):
                errors['base'] = 'pyscript_missing'
            elif not user_input.get('ready'):
                errors['base'] = 'setup_required'
            else:
                return self.async_create_entry(title='Tryon Quail Hatchery', data={})
        return self.async_show_form(step_id='user', data_schema=vol.Schema({
            vol.Required('ready', default=False): bool,
        }), errors=errors)
