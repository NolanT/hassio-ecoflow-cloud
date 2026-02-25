"""
EcoFlow OceanPro Hybrid Inverter (EF-PCS-24) — internal (private API) device.

MQTT payload format: repeated Header protobuf envelope (same outer structure as
SmartMeter), with pdata decoded as OceanProStatus (cmd_func=254, cmd_id=21)
or OceanProSysInfo (cmd_func=254, cmd_id=25).

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
from custom_components.ecoflow_cloud.devices.internal.proto import ef_oceanpro_pb2
from custom_components.ecoflow_cloud.sensor import (
    AmpSensorEntity,
    CelsiusSensorEntity,
    ChargingStateSensorEntity,
    CyclesSensorEntity,
    EnergySensorEntity,
    LevelSensorEntity,
    MiscSensorEntity,
    QuotaStatusSensorEntity,
    SecondsRemainSensorEntity,
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
        pf = f"{_CMD_FUNC}_{_CMD_STATUS}"   # "254_21"
        sh = f"{_CMD_FUNC}_{_CMD_SYSINFO}"  # "254_25"
        return [
            # ── System power ─────────────────────────────────────────────────
            WattsSensorEntity(client, self, f"{pf}.powGetSysLoad", "Home Load"),
            WattsSensorEntity(client, self, f"{pf}.pclPwrOffset", "Grid Power"),
            WattsSensorEntity(client, self, f"{pf}.powGetBpCms", "Battery Power"),
            WattsSensorEntity(client, self, f"{pf}.powGetPvSum", "PV Power"),

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

            # ── PV (from short heartbeat) ────────────────────────────────────
            WattsSensorEntity(client, self, f"{sh}.pvPwr", "PV Power (heartbeat)", enabled=False),

            # ── Battery ───────────────────────────────────────────────────────
            LevelSensorEntity(client, self, f"{pf}.cmsBattSoc", "Battery SoC"),
            LevelSensorEntity(
                client, self, f"{pf}.cmsBattSoh", "Battery Health",
                enabled=False,
            ),
            ChargingStateSensorEntity(
                client, self, f"{pf}.cmsChgDsgState", "Charge/Discharge State",
            ),
            MiscSensorEntity(client, self, f"{pf}.cmsBattStoreEnergy", "Stored Energy (Wh)"),
            MiscSensorEntity(
                client, self, f"{pf}.cmsBattRatedEnergy", "Rated Capacity (Wh)",
                enabled=False,
            ),
            MiscSensorEntity(
                client, self, f"{pf}.cmsBattFullEnergy", "Usable Capacity (Wh)",
                enabled=False,
            ),
            VoltSensorEntity(
                client, self, f"{pf}.cmsBattVol", "Battery Voltage",
                enabled=False,
            ),
            AmpSensorEntity(
                client, self, f"{pf}.cmsBattAmp", "Battery Current",
                enabled=False,
            ),
            CelsiusSensorEntity(
                client, self, f"{pf}.cmsBattTemp", "Battery Temperature",
                enabled=False,
            ),
            SecondsRemainSensorEntity(
                client, self, f"{pf}.cmsDsgRemTime", "Discharge Time Remaining",
                enabled=False,
            ),
            SecondsRemainSensorEntity(
                client, self, f"{pf}.cmsChgRemTime", "Charge Time Remaining",
                enabled=False,
            ),
            MiscSensorEntity(
                client, self, f"{pf}.cmsMaxChgSoc", "Max Charge SoC",
                enabled=False,
            ),
            MiscSensorEntity(
                client, self, f"{pf}.cmsMinDsgSoc", "Min Discharge SoC",
                enabled=False,
            ),
            CyclesSensorEntity(
                client, self, f"{pf}.cmsBattCycleNum", "Battery Cycles",
                enabled=False,
            ),
            MiscSensorEntity(
                client, self, f"{pf}.cmsBpOnlineCnt", "Battery Packs Online",
                enabled=False,
            ),
            MiscSensorEntity(
                client, self, f"{pf}.cmsBpRunningCnt", "Battery Packs Running",
                enabled=False,
            ),
            EnergySensorEntity(
                client, self, f"{pf}.cmsEnergyInSum", "Lifetime Energy Charged",
                enabled=False,
            ),
            EnergySensorEntity(
                client, self, f"{pf}.cmsEnergyOutSum", "Lifetime Energy Discharged",
                enabled=False,
            ),

            # ── Grid phase sensors (disabled by default) ──────────────────────
            VoltSensorEntity(
                client, self, f"{pf}.gridVolL1", "Grid Voltage L1",
                enabled=False,
            ),
            AmpSensorEntity(
                client, self, f"{pf}.gridAmpL1", "Grid Current L1",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridPowL1", "Grid Power L1",
                enabled=False,
            ),
            VoltSensorEntity(
                client, self, f"{pf}.gridVolL2", "Grid Voltage L2",
                enabled=False,
            ),
            AmpSensorEntity(
                client, self, f"{pf}.gridAmpL2", "Grid Current L2",
                enabled=False,
            ),
            WattsSensorEntity(
                client, self, f"{pf}.gridPowL2", "Grid Power L2",
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

            # ── Short heartbeat (disabled by default) ────────────────────────
            WattsSensorEntity(
                client, self,
                f"{sh}.sysLoadPwr",
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
                cmd_id   = message.cmd_id
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
