export const SAMPLE_BCM_YAML = `# Synthetic ECU diagnostic extract for the demo project. Not real OEM data.
name: BCM-X1
oem: Acme Motors
version: "2.3"
description: Body control module (interior lighting, door locks, odometer calibration).
request_id: 0x7E0
response_id: 0x7E8

timing:
  p2_ms: 50
  p2_star_ms: 5000
  s3_ms: 5000

sessions:
  0x01: defaultSession
  0x02: programmingSession
  0x03: extendedDiagnosticSession

security_levels:
  - level: 0x01            # requestSeed sub-function
    send_key_sub: 0x02
    seed_length: 4
    key_length: 4
    algorithm: xor
    constant: 0xA5C3F00D
    max_attempts: 3
    lockout_ms: 10000
    description: Level 1 - configuration writes and protected reads
  - level: 0x03
    send_key_sub: 0x04
    seed_length: 4
    key_length: 4
    algorithm: xor
    constant: 0x5A3C0FF1
    max_attempts: 3
    lockout_ms: 10000
    description: Level 2 - calibration and erase operations

services:
  0x10:
    name: DiagnosticSessionControl
    sessions: [0x01, 0x02, 0x03]
    subfunctions:
      0x01: {name: defaultSession}
      0x02: {name: programmingSession}
      0x03: {name: extendedDiagnosticSession}
  0x11:
    name: ECUReset
    sessions: [0x02, 0x03]
    subfunctions:
      0x01: {name: hardReset}
      0x03: {name: softReset}
  0x14:
    name: ClearDiagnosticInformation
    sessions: [0x01, 0x02, 0x03]
  0x19:
    name: ReadDTCInformation
    sessions: [0x01, 0x02, 0x03]
    subfunctions:
      0x01: {name: reportNumberOfDTCByStatusMask}
      0x02: {name: reportDTCByStatusMask}
      0x0A: {name: reportSupportedDTC}
  0x22:
    name: ReadDataByIdentifier
    sessions: [0x01, 0x02, 0x03]
  0x27:
    name: SecurityAccess
    sessions: [0x02, 0x03]
    subfunctions:
      0x01: {name: requestSeed_L1}
      0x02: {name: sendKey_L1}
      0x03: {name: requestSeed_L2}
      0x04: {name: sendKey_L2}
  0x28:
    name: CommunicationControl
    sessions: [0x03]
    subfunctions:
      0x00: {name: enableRxAndTx}
      0x01: {name: enableRxAndDisableTx}
      0x02: {name: disableRxAndEnableTx}
      0x03: {name: disableRxAndTx}
  0x2E:
    name: WriteDataByIdentifier
    sessions: [0x02, 0x03]
  0x31:
    name: RoutineControl
    sessions: [0x02, 0x03]
    subfunctions:
      0x01: {name: startRoutine}
      0x02: {name: stopRoutine}
      0x03: {name: requestRoutineResults}
  0x3E:
    name: TesterPresent
    sessions: [0x01, 0x02, 0x03]
    subfunctions:
      0x00: {name: zeroSubFunction}
  0x85:
    name: ControlDTCSetting
    sessions: [0x03]
    subfunctions:
      0x01: {name: "on"}
      0x02: {name: "off"}

dids:
  - id: 0xF186
    name: ActiveDiagnosticSession
    length: 1
    data_type: uint
    live: active_session
    read: {sessions: [0x01, 0x02, 0x03]}
    description: Currently active diagnostic session, computed by the ECU.
  - id: 0xF187
    name: SparePartNumber
    length: 10
    data_type: ascii
    default: "BCM0012345"
    read: {sessions: [0x01, 0x02, 0x03]}
  - id: 0xF189
    name: ECUSoftwareVersion
    length: 8
    data_type: ascii
    default: "01.02.03"
    read: {sessions: [0x01, 0x02, 0x03]}
  - id: 0xF18C
    name: ECUSerialNumber
    length: 12
    data_type: ascii
    default: "SN2026090001"
    read: {sessions: [0x01, 0x02, 0x03]}
  - id: 0xF190
    name: VIN
    length: 17
    data_type: ascii
    default: "WAUZZZ8K9DA123456"
    example: "1HGCM82633A004352"
    invalid_example: "1HGCM82633A00435I"
    pattern: "[A-HJ-NPR-Z0-9]{17}"
    read: {sessions: [0x01, 0x02, 0x03]}
    write: {sessions: [0x03], security: 0x01}
    description: Vehicle identification number (17 characters, letters I, O and Q are not allowed).
  - id: 0x0200
    name: InteriorLightBrightness
    length: 1
    data_type: uint
    default: 50
    example: 75
    min: 0
    max: 100
    read: {sessions: [0x01, 0x02, 0x03]}
    write: {sessions: [0x03]}
    description: Interior light brightness in percent. Writable in extended session without unlock.
  - id: 0x0300
    name: DoorLockConfig
    length: 1
    data_type: uint
    default: 1
    example: 2
    min: 0
    max: 3
    read: {sessions: [0x03]}
    write: {sessions: [0x03], security: 0x01}
    description: Door lock behaviour (0 manual, 1 auto-lock, 2 speed-lock, 3 both).
  - id: 0x0400
    name: OdometerCalibration
    length: 4
    data_type: uint
    default: 0
    example: 1000
    min: 0
    max: 999999
    read: {sessions: [0x03], security: 0x01}
    write: {sessions: [0x03], security: 0x03}
    description: Odometer calibration offset in km. Read needs level 1, write needs level 2.

routines:
  - id: 0x0301
    name: LampSelfTest
    sessions: [0x03]
    option_length: 1
    start_response: "00"
    stop_response: "00"
    results_response: "01"
    single_instance: true
    description: Runs a self-test on one lamp channel (0..3). Results byte 01 = passed.
  - id: 0xFF00
    name: EraseCalibrationMemory
    sessions: [0x03]
    security: 0x03
    option_length: 0
    start_response: ""
    stop_response: ""
    results_response: "00"
    single_instance: true
    send_pending: true
    description: Erases calibration memory. ECU answers with NRC 0x78 first, then the final response.

dtcs:
  - {code: 0x9A0116, status: 0x2F, name: Interior light circuit open}
  - {code: 0x9A0217, status: 0x08, name: Door lock actuator short to ground}
  - {code: 0xC10087, status: 0x24, name: CAN bus off}
`;

export function getSampleProfileFile(): File {
  return new File([SAMPLE_BCM_YAML], 'bcm_ecu_profile.yaml', { type: 'application/x-yaml' });
}
