"""Generic UDS service catalogue.

This is an original, paraphrased engineering summary of well-known UDS service
structure. It is NOT a reproduction of ISO 14229 text. ECU / OEM specifics live
in the ECU profile (``profile.py``), which is the authorised, project-specific
source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SUPPRESS_POSITIVE_RESPONSE = 0x80


@dataclass(frozen=True)
class ServiceInfo:
    sid: int
    name: str
    has_subfunction: bool
    request_format: str
    response_format: str
    summary: str
    typical_nrcs: tuple[int, ...] = field(default_factory=tuple)

    @property
    def positive_sid(self) -> int:
        return self.sid + 0x40


SERVICES: dict[int, ServiceInfo] = {
    s.sid: s
    for s in [
        ServiceInfo(0x10, "DiagnosticSessionControl", True,
                    "10 <sub>", "50 <sub> <P2 hi lo> <P2* hi lo>",
                    "Switches the diagnostic session (default 01, programming 02, extended 03). "
                    "Response carries the P2 (ms) and P2* (10 ms units) server timing. "
                    "A successful session change re-locks security access.",
                    (0x12, 0x13, 0x22)),
        ServiceInfo(0x11, "ECUReset", True,
                    "11 <resetType>", "51 <resetType>",
                    "Requests an ECU reset (hard 01, key-off-on 02, soft 03). After the positive "
                    "response the ECU returns to the default session.",
                    (0x12, 0x13, 0x22, 0x33, 0x7F)),
        ServiceInfo(0x14, "ClearDiagnosticInformation", False,
                    "14 <groupOfDTC 3 bytes>", "54",
                    "Clears stored DTCs and related data for a DTC group (FFFFFF = all).",
                    (0x13, 0x22, 0x31)),
        ServiceInfo(0x19, "ReadDTCInformation", True,
                    "19 <sub> [<statusMask>]", "59 <sub> <availabilityMask> ...",
                    "Reads DTC information: 01 count by status mask, 02 list by status mask, "
                    "0A list of supported DTCs.",
                    (0x12, 0x13, 0x31)),
        ServiceInfo(0x22, "ReadDataByIdentifier", False,
                    "22 <DID hi lo> [<DID hi lo> ...]", "62 <DID hi lo> <data> ...",
                    "Reads one or more data identifiers. Each DID is two bytes; the response "
                    "echoes each DID followed by its data record.",
                    (0x13, 0x22, 0x31, 0x33)),
        ServiceInfo(0x27, "SecurityAccess", True,
                    "27 <odd: requestSeed> | 27 <even: sendKey> <key>",
                    "67 <sub> [<seed>]",
                    "Seed/key unlock. Odd sub-function requests a seed, the following even "
                    "sub-function sends the computed key. An all-zero seed means already unlocked.",
                    (0x12, 0x13, 0x24, 0x35, 0x36, 0x37)),
        ServiceInfo(0x28, "CommunicationControl", True,
                    "28 <controlType> <communicationType>", "68 <controlType>",
                    "Enables or disables receive/transmit of normal (01), network-management (02) "
                    "or both (03) messages.",
                    (0x12, 0x13, 0x22, 0x31, 0x7F)),
        ServiceInfo(0x2E, "WriteDataByIdentifier", False,
                    "2E <DID hi lo> <data>", "6E <DID hi lo>",
                    "Writes a data record to a data identifier. Length of data must equal the "
                    "DID length.",
                    (0x13, 0x22, 0x31, 0x33)),
        ServiceInfo(0x31, "RoutineControl", True,
                    "31 <sub> <RID hi lo> [<option record>]", "71 <sub> <RID hi lo> [<status>]",
                    "Start (01), stop (02) or request results (03) of a routine identified by a "
                    "two-byte RID.",
                    (0x12, 0x13, 0x22, 0x24, 0x31, 0x33)),
        ServiceInfo(0x3E, "TesterPresent", True,
                    "3E <sub>", "7E <sub>",
                    "Keeps a non-default session alive (resets the S3 timer). Sub-function 00 "
                    "with bit 7 set suppresses the positive response.",
                    (0x12, 0x13)),
        ServiceInfo(0x85, "ControlDTCSetting", True,
                    "85 <sub>", "C5 <sub>",
                    "Switches DTC status-bit updating on (01) or off (02).",
                    (0x12, 0x13, 0x22, 0x31, 0x7F)),
    ]
}

# Services that a generic ECU may not implement; used to build "service not supported" tests.
PROBE_UNSUPPORTED_SIDS = (0x87, 0x83, 0x86, 0x2A, 0x3D, 0xBA)


def service_name(sid: int) -> str:
    info = SERVICES.get(sid)
    return info.name if info else f"Service0x{sid:02X}"
