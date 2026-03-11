from custom_components.ecoflow_cloud.entities import EcoFlowDictEntity
from typing import Any
from custom_components.ecoflow_cloud import ECOFLOW_DOMAIN
from custom_components.ecoflow_cloud.api import EcoflowApiClient
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.components.binary_sensor import BinarySensorEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    client: EcoflowApiClient = hass.data[ECOFLOW_DOMAIN][entry.entry_id]
    for sn, device in client.devices.items():
        sensors = device.binary_sensors(client)
        async_add_entities(sensors)


class MiscBinarySensorEntity(BinarySensorEntity, EcoFlowDictEntity, RestoreEntity):
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Restore last known state from HA recorder so we don't flash "unknown"
        # on every integration reload or HA restart.
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.state == STATE_ON:
                self._attr_is_on = True
            elif last_state.state == STATE_OFF:
                self._attr_is_on = False
            # STATE_UNKNOWN / STATE_UNAVAILABLE → leave _attr_is_on as None

    def _update_value(self, val: Any) -> bool:
        self._attr_is_on = bool(val)
        return True
