"""
EcoFlow OceanPro Hybrid Inverter (EF-PCS-24) — internal (private API) device.

MQTT payload format: repeated Header protobuf envelope (same outer structure as
SmartMeter), with pdata decoded as OceanProStatus (cmd_func=254, cmd_id=21)
or OceanProSysInfo (cmd_func=254, cmd_id=25).

Field numbers reverse-engineered from live captures against device SN HR51ZA1*.
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
from custom_components.ecoflow_cloud.devices.internal.proto import ef_oceanpro_pb2
from custom_components.ecoflow_cloud.sensor import (
    AmpSensorEntity,
    LevelSensorEntity,
    MiscSensorEntity,
    QuotaStatusSensorEntity,
    VoltSensorEntity,
    WattsSensorEntity,
)

_LOGGER = logging.getLogger(__name__)

# cmd_func / cmd_id values observed in live captures
_CMD_FUNC = 254
_CMD_STATUS = 21    # long property-upload  (OceanProStatus)
_CMD_SYSINFO = 25   # short heartbeat       (OceanProSysInfo)


class OceanPro(BaseInternalDevice):

    @override
    def sensors(self, client: EcoflowApiClient) -> list[SensorEntity]:
        pf = f"{_CMD_FUNC}_{_CMD_STATUS}"  # "254_21"
        return [
            # Home load
            WattsSensorEntity(client, self, f"{pf}.powGetSysLoad", "Home Load"),

            # Grid power (negative = exporting to grid)
            WattsSensorEntity(client, self, f"{pf}.pclPwrOffset", "Grid Power"),

            # Battery SoC — raw value ÷ 10 is done in _prepare_data
            LevelSensorEntity(client, self, f"{pf}.battery_soc", "Battery SoC"),

            # Phase L1
            VoltSensorEntity(client, self, f"{pf}.gridVolL1", "Grid Voltage L1"),
            AmpSensorEntity(client, self, f"{pf}.gridAmpL1", "Grid Current L1"),
            WattsSensorEntity(client, self, f"{pf}.gridPowL1", "Grid Power L1"),

            # Phase L2
            VoltSensorEntity(client, self, f"{pf}.gridVolL2", "Grid Voltage L2"),
            AmpSensorEntity(client, self, f"{pf}.gridAmpL2", "Grid Current L2"),
            WattsSensorEntity(client, self, f"{pf}.gridPowL2", "Grid Power L2"),

            # Short heartbeat sensors (cmd_id=25) — disabled by default
            WattsSensorEntity(
                client, self,
                f"{_CMD_FUNC}_{_CMD_SYSINFO}.pvPwr",
                "PV Power (heartbeat)",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self,
                f"{_CMD_FUNC}_{_CMD_SYSINFO}.sysLoadPwr",
                "System Load (heartbeat)",
                enabled=False,
            ),

            self._status_sensor(client),
        ]

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
                    "OceanPro cmd_func=%s cmd_id=%s pdata=%s",
                    cmd_func, cmd_id, message.pdata.hex(),
                )

                if message.HasField("device_sn") and message.device_sn != self.device_data.sn:
                    _LOGGER.info(
                        "Ignoring EcoPacket for SN %s on topic for SN %s",
                        message.device_sn,
                        self.device_data.sn,
                    )
                    continue

                # XOR-decrypt if encrypted
                pdata = message.pdata
                if message.enc_type == 1:
                    pdata = bytes([b ^ (message.seq % 256) for b in pdata])

                params = cast(JSONDict, res.setdefault("params", {}))
                prefix = f"{cmd_func}_{cmd_id}"

                if cmd_func == _CMD_FUNC and cmd_id == _CMD_STATUS:
                    payload = ef_oceanpro_pb2.OceanProStatus()
                    payload.ParseFromString(pdata)
                    raw = MessageToDict(payload, preserving_proto_field_name=False)
                    for k, v in flatten_dict(raw).items():
                        params[f"{prefix}.{k}"] = v

                    # Derive a scaled battery SoC (raw field 268 = soc × 10)
                    raw_soc = raw.get("batterySocX10")
                    if raw_soc is not None:
                        params[f"{prefix}.battery_soc"] = round(int(raw_soc) / 10.0, 1)

                elif cmd_func == _CMD_FUNC and cmd_id == _CMD_SYSINFO:
                    payload = ef_oceanpro_pb2.OceanProSysInfo()
                    payload.ParseFromString(pdata)
                    raw = MessageToDict(payload, preserving_proto_field_name=False)
                    for k, v in flatten_dict(raw).items():
                        params[f"{prefix}.{k}"] = v

                else:
                    _LOGGER.debug("OceanPro: unhandled cmd_func=%s cmd_id=%s", cmd_func, cmd_id)

                res["cmdFunc"] = cmd_func
                res["cmdId"] = cmd_id
                res["timestamp"] = dt.utcnow()

        except Exception as exc:
            _LOGGER.error("OceanPro _prepare_data error: %s", exc)
            _LOGGER.debug("raw hex: %s", raw_data.hex())

        return res
