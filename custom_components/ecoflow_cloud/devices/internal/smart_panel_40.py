"""
EcoFlow Smart Electrical Panel 40 (EF-SHP-40) — internal (private API) device.

MQTT payload format: repeated Header protobuf envelope, pdata decoded as
SmartPanel40Status (cmd_func=254, cmd_id=21).

Field numbers reverse-engineered from live captures against device SN HR61ZA1*.
"""

from __future__ import annotations

import logging
from typing import Any, cast, override

from google.protobuf.json_format import MessageToDict
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.util import dt

from custom_components.ecoflow_cloud.api import EcoflowApiClient
from custom_components.ecoflow_cloud.api.message import JSONDict
from custom_components.ecoflow_cloud.devices import BaseInternalDevice
from custom_components.ecoflow_cloud.devices.internal import flatten_dict
from custom_components.ecoflow_cloud.devices.internal.proto import ef_smartmeter_pb2
from custom_components.ecoflow_cloud.devices.internal.proto import ef_smartpanel40_pb2
from custom_components.ecoflow_cloud.sensor import (
    AmpSensorEntity,
    MiscSensorEntity,
    QuotaStatusSensorEntity,
    VoltSensorEntity,
    WattsSensorEntity,
)

_LOGGER = logging.getLogger(__name__)

_CMD_FUNC = 254
_CMD_STATUS = 21
_NUM_CIRCUITS = 40


def _circuit_key(i: int, field: str) -> str:
    """Return the flattened params key for circuit i (1-based)."""
    return f"{_CMD_FUNC}_{_CMD_STATUS}.loadCh{i}SampleInfo.{field}"


def _circuit_cfg_key(i: int, field: str) -> str:
    return f"{_CMD_FUNC}_{_CMD_STATUS}.loadCh{i}Sta.{field}"


class SmartPanel40(BaseInternalDevice):

    @override
    def sensors(self, client: EcoflowApiClient) -> list[SensorEntity]:
        pf = f"{_CMD_FUNC}_{_CMD_STATUS}"
        entities: list[SensorEntity] = [
            # Total home load
            WattsSensorEntity(client, self, f"{pf}.powGetSysLoad", "Home Load"),

            # Grid per-phase
            VoltSensorEntity(client, self, f"{pf}.gridConnectionVolL1", "Grid Voltage L1"),
            VoltSensorEntity(client, self, f"{pf}.gridConnectionVolL2", "Grid Voltage L2"),
            AmpSensorEntity(client, self, f"{pf}.gridConnectionAmpL1", "Grid Current L1"),
            AmpSensorEntity(client, self, f"{pf}.gridConnectionAmpL2", "Grid Current L2"),
            WattsSensorEntity(client, self, f"{pf}.gridConnectionPowerL1", "Grid Power L1"),
            WattsSensorEntity(client, self, f"{pf}.gridConnectionPowerL2", "Grid Power L2"),

            # Computed total grid power (stored by _prepare_data)
            WattsSensorEntity(client, self, f"{pf}.grid_power_total", "Grid Power Total"),

            # Timezone info
            MiscSensorEntity(client, self, f"{pf}.utcTimezoneId", "Timezone", enabled=False),

            self._status_sensor(client),
        ]

        # Per-circuit sensors (enabled=False by default — user can enable in HA)
        for i in range(1, _NUM_CIRCUITS + 1):
            entities.extend([
                VoltSensorEntity(
                    client, self, _circuit_key(i, "voltage"),
                    f"Circuit {i} Voltage", enabled=False,
                ),
                AmpSensorEntity(
                    client, self, _circuit_key(i, "current"),
                    f"Circuit {i} Current", enabled=False,
                ),
                WattsSensorEntity(
                    client, self, _circuit_key(i, "apparent_pwr"),
                    f"Circuit {i} Power", enabled=False,
                ),
                MiscSensorEntity(
                    client, self, _circuit_cfg_key(i, "name"),
                    f"Circuit {i} Name", enabled=False,
                ),
            ])

        return entities

    def numbers(self, client: EcoflowApiClient) -> list[NumberEntity]:
        return []

    def switches(self, client: EcoflowApiClient) -> list[SwitchEntity]:
        return []

    def selects(self, client: EcoflowApiClient) -> list[SelectEntity]:
        return []

    def _status_sensor(self, client: EcoflowApiClient) -> QuotaStatusSensorEntity:
        return QuotaStatusSensorEntity(client, self)

    @override
    def _prepare_data(self, raw_data: bytes) -> dict[str, Any]:
        res: dict[str, Any] = {"params": {}}
        try:
            packet = ef_smartmeter_pb2.SmartMeterSetMessage()
            packet.ParseFromString(raw_data)

            for message in packet.msg:
                cmd_func = message.cmd_func
                cmd_id = message.cmd_id
                _LOGGER.debug(
                    "SmartPanel40 cmd_func=%s cmd_id=%s pdata=%s",
                    cmd_func, cmd_id, message.pdata.hex(),
                )

                if message.HasField("device_sn") and message.device_sn != self.device_data.sn:
                    _LOGGER.info(
                        "Ignoring EcoPacket for SN %s on topic for SN %s",
                        message.device_sn, self.device_data.sn,
                    )
                    continue

                pdata = message.pdata
                if message.enc_type == 1:
                    pdata = bytes([b ^ (message.seq % 256) for b in pdata])

                params = cast(JSONDict, res.setdefault("params", {}))
                prefix = f"{cmd_func}_{cmd_id}"

                if cmd_func == _CMD_FUNC and cmd_id == _CMD_STATUS:
                    payload = ef_smartpanel40_pb2.SmartPanel40Status()
                    payload.ParseFromString(pdata)
                    raw = MessageToDict(payload, preserving_proto_field_name=False)
                    for k, v in flatten_dict(raw).items():
                        params[f"{prefix}.{k}"] = v

                    # Compute total grid power from L1 + L2
                    p_l1 = params.get(f"{prefix}.gridConnectionPowerL1", 0.0)
                    p_l2 = params.get(f"{prefix}.gridConnectionPowerL2", 0.0)
                    if p_l1 or p_l2:
                        params[f"{prefix}.grid_power_total"] = round(
                            float(p_l1) + float(p_l2), 1
                        )

                    # Compute per-circuit apparent power (V × I)
                    for i in range(1, _NUM_CIRCUITS + 1):
                        camel = f"loadCh{i}SampleInfo"
                        v_key = f"{prefix}.{camel}.voltage"
                        a_key = f"{prefix}.{camel}.current"
                        p_key = f"{prefix}.{camel}.apparent_pwr"
                        v_val = float(params.get(v_key) or 0.0)
                        a_val = float(params.get(a_key) or 0.0)
                        if v_val and a_val:
                            params[p_key] = round(abs(v_val * a_val), 1)

                else:
                    _LOGGER.debug(
                        "SmartPanel40: unhandled cmd_func=%s cmd_id=%s", cmd_func, cmd_id
                    )

                res["cmdFunc"] = cmd_func
                res["cmdId"] = cmd_id
                res["timestamp"] = dt.utcnow()

        except Exception as exc:
            _LOGGER.error("SmartPanel40 _prepare_data error: %s", exc)
            _LOGGER.debug("raw hex: %s", raw_data.hex())

        return res
