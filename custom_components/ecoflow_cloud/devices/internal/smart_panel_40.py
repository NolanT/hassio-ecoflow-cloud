"""
EcoFlow Smart Electrical Panel 40 (EF-SHP-40) — internal (private API) device.

MQTT payload format: repeated Header protobuf envelope, pdata decoded as
SmartPanel40Status (cmd_func=254, cmd_id=21).

Field numbers sourced from DevAplComm.java (decompiled EcoFlow 6.11.0 app).
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
    CelsiusSensorEntity,
    FrequencySensorEntity,
    MiscSensorEntity,
    QuotaStatusSensorEntity,
    SecondsRemainSensorEntity,
    VoltSensorEntity,
    WattsSensorEntity,
)

_LOGGER = logging.getLogger(__name__)

_CMD_FUNC = 254
_CMD_STATUS = 21
_NUM_CIRCUITS = 40


def _circuit_key(i: int, field: str) -> str:
    """Return the flattened params key for circuit i (1-based), sample info."""
    return f"{_CMD_FUNC}_{_CMD_STATUS}.loadCh{i}SampleInfo.{field}"


def _circuit_cfg_key(i: int, field: str) -> str:
    """Return the flattened params key for circuit i (1-based), status/config."""
    return f"{_CMD_FUNC}_{_CMD_STATUS}.loadCh{i}Sta.{field}"


class SmartPanel40(BaseInternalDevice):

    @override
    def sensors(self, client: EcoflowApiClient) -> list[SensorEntity]:
        pf = f"{_CMD_FUNC}_{_CMD_STATUS}"
        entities: list[SensorEntity] = [
            # ── System power ─────────────────────────────────────────────────
            WattsSensorEntity(client, self, f"{pf}.powGetSysLoad", "Home Load").with_energy(),
            WattsSensorEntity(client, self, f"{pf}.powGetPvSum", "PV Power").with_energy(),
            WattsSensorEntity(client, self, f"{pf}.powGetBpCms", "Battery Power").with_energy(),

            # Computed total grid power (L1 + L2, stored by _prepare_data)
            WattsSensorEntity(client, self, f"{pf}.grid_power_total", "Grid Power Total").with_energy(),

            # ── PV strings (per-MPPT, enabled by default) ────────────────────
            WattsSensorEntity(client, self, f"{pf}.dtPvPwrCurrent", "PV String 1"),
            WattsSensorEntity(client, self, f"{pf}.dtPv2PwrCurrent", "PV String 2"),
            WattsSensorEntity(client, self, f"{pf}.dtPv3PwrCurrent", "PV String 3"),
            WattsSensorEntity(client, self, f"{pf}.dtPv4PwrCurrent", "PV String 4"),
            WattsSensorEntity(client, self, f"{pf}.dtPv5PwrCurrent", "PV String 5"),
            WattsSensorEntity(client, self, f"{pf}.dtPv6PwrCurrent", "PV String 6"),
            WattsSensorEntity(
                client, self, f"{pf}.dtPv7PwrCurrent", "PV String 7",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.dtPv8PwrCurrent", "PV String 8",
                enabled=False,
            ),

            # ── Battery (mirrored from OceanPro) ─────────────────────────────
            MiscSensorEntity(client, self, f"{pf}.cmsBattStoreEnergy", "Stored Energy (Wh)"),
            SecondsRemainSensorEntity(
                client, self, f"{pf}.cmsChgRemTime", "Charge Time Remaining",
                enabled=False,
            ),

            # ── Grid phase (L1 / L2) ─────────────────────────────────────────
            VoltSensorEntity(
                client, self, f"{pf}.gridConnectionVolL1", "Grid Voltage L1",
                enabled=False,
            ),
            VoltSensorEntity(
                client, self, f"{pf}.gridConnectionVolL2", "Grid Voltage L2",
                enabled=False,
            ),
            AmpSensorEntity(
                client, self, f"{pf}.gridConnectionAmpL1", "Grid Current L1",
                enabled=False,
            ),
            AmpSensorEntity(
                client, self, f"{pf}.gridConnectionAmpL2", "Grid Current L2",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionPowerL1", "Grid Power L1",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionPowerL2", "Grid Power L2",
                enabled=False,
            ),
            FrequencySensorEntity(
                client, self, f"{pf}.gridConnectionFreqL1", "Grid Frequency L1",
                enabled=False,
            ),
            FrequencySensorEntity(
                client, self, f"{pf}.gridConnectionFreqL2", "Grid Frequency L2",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionReactivePowerL1", "Grid Reactive Power L1",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionReactivePowerL2", "Grid Reactive Power L2",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionApparentPowerL1", "Grid Apparent Power L1",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridConnectionApparentPowerL2", "Grid Apparent Power L2",
                enabled=False,
            ),

            # ── Panel bus voltage ────────────────────────────────────────────
            VoltSensorEntity(
                client, self, f"{pf}.panelBusVolL1", "Panel Bus Voltage L1",
                enabled=False,
            ),
            VoltSensorEntity(
                client, self, f"{pf}.panelBusVolL2", "Panel Bus Voltage L2",
                enabled=False,
            ),

            # ── Load source breakdown (disabled by default) ──────────────────
            WattsSensorEntity(
                client, self, f"{pf}.powGetSysLoadFromPv", "Home Load from PV",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.powGetSysLoadFromBp", "Home Load from Battery",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.powGetSysLoadFromGrid", "Home Load from Grid",
                enabled=False,
            ),

            # ── Generator (disabled by default) ──────────────────────────────
            WattsSensorEntity(
                client, self, f"{pf}.powGetStandbyGenerator", "Standby Generator Power",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.powGetPortableGenerator", "Portable Generator Power",
                enabled=False,
            ),

            # ── Device temperatures (disabled by default) ─────────────────────
            CelsiusSensorEntity(
                client, self, f"{pf}.devTemperature1", "Device Temperature 1",
                enabled=False,
            ),
            CelsiusSensorEntity(
                client, self, f"{pf}.devTemperature2", "Device Temperature 2",
                enabled=False,
            ),
            CelsiusSensorEntity(
                client, self, f"{pf}.devTemperature3", "Inverter Temperature",
                enabled=False,
            ),
            CelsiusSensorEntity(
                client, self, f"{pf}.devTemperature4", "Device Temperature 4",
                enabled=False,
            ),
            CelsiusSensorEntity(
                client, self, f"{pf}.devTemperature5", "Device Temperature 5",
                enabled=False,
            ),

            # ── Timezone / misc ──────────────────────────────────────────────
            MiscSensorEntity(
                client, self, f"{pf}.utcTimezoneId", "Timezone",
                enabled=False,
            ),

            self._status_sensor(client),
        ]

        # ── Per-circuit sensors (40 circuits, all disabled by default) ────────
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
                WattsSensorEntity(
                    client, self, _circuit_key(i, "reactivePwr"),
                    f"Circuit {i} Reactive Power", enabled=False,
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

                    # Convert grid frequency period (μs) → Hz
                    # Fields 960/961 contain period in microseconds; Hz = 1_000_000 / period
                    for phase, camel_period, camel_hz in (
                        ("L1", "gridConnectionFreqPeriodL1", "gridConnectionFreqL1"),
                        ("L2", "gridConnectionFreqPeriodL2", "gridConnectionFreqL2"),
                    ):
                        period = float(params.get(f"{prefix}.{camel_period}") or 0.0)
                        if period > 0:
                            params[f"{prefix}.{camel_hz}"] = round(1_000_000.0 / period, 3)

                    # Compute per-circuit apparent power (V × I) when device
                    # doesn't send apparent_pwr directly
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
