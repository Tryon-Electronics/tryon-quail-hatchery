"""HACS-managed installer for the Tryon Quail Hatchery Pyscript bundle."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .installer import install_bundle

DOMAIN = 'tryon_quail_hatchery'


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Deploy on first setup / update; configuration and data remain user-owned."""
    payload = str(Path(__file__).parent / 'payload')
    try:
        result = await hass.async_add_executor_job(install_bundle, hass.config.config_dir, payload)
    except (OSError, ValueError) as err:
        raise ConfigEntryNotReady(f'Unable to install hatchery bundle: {err}') from err
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = result
    if result['installed'] or result['updated'] or result['conflicts']:
        conflicts = '\n'.join('- ' + path for path in result['conflicts'])
        message = (
            f"Bundle {result['version']} prepared. Existing batches.json was preserved. "
            'Enable packages, review helper conflicts, configure Pyscript imports and the '
            'YAML dashboard as described in README, then check configuration and restart. '
            'This integration does not edit configuration.yaml or existing automations. '
            'Create the notification automation from the installed blueprint and choose your own phone.'
        )
        if conflicts:
            message += '\n\nEdited/legacy files were kept; replacements are staged with .quail-update:\n' + conflicts
        persistent_notification.async_create(hass, message, 'Tryon Quail Hatchery setup', DOMAIN)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Keep installed config and hatch data on removal; see documented cleanup."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
