# Acme Motors body control module - diagnostic notes (OEM layer)

These are project-authored notes summarizing OEM diagnostic conventions for the BCM-X1
family. They exist so the knowledge base has more than one layer to search across.

## Session handling

Acme ECUs use the standard three-session model (default, programming, extended). Tools
should always request the extended diagnostic session before any write or routine, and
should send TesterPresent at least every 2.5 seconds while in a non-default session to
stay safely under the S3 server timeout.

## Security access conventions

Acme's seed/key algorithm family for body control modules is a simple XOR against a
per-level constant. Production ECUs use a stronger algorithm; the XOR scheme in this
project's sample profile is for demonstration only and must never be treated as a real
security implementation.

Security access is always re-locked by:
- a diagnostic session change (service 0x10), and
- an ECU reset (service 0x11).

Tools must not cache an unlocked state across either event.

## VIN programming

The VIN (DID 0xF190) may only be written once per vehicle build in the field process;
downstream tools should treat a second VIN write attempt as a process exception even
though the ECU itself does not enforce single-write behaviour at the protocol level.

## Calibration erase

EraseCalibrationMemory (routine 0xFF00) is a destructive operation gated behind the
higher security level. Field tools must confirm with the operator before invoking it,
and should never include it in an unattended regression suite without an explicit
opt-in flag.
