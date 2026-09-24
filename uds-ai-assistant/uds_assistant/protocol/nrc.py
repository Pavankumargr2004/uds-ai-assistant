"""Negative response codes (ISO 14229-1 concepts; names paraphrased for this project)."""

NRC_NAMES: dict[int, str] = {
    0x10: "generalReject",
    0x11: "serviceNotSupported",
    0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat",
    0x14: "responseTooLong",
    0x21: "busyRepeatRequest",
    0x22: "conditionsNotCorrect",
    0x24: "requestSequenceError",
    0x31: "requestOutOfRange",
    0x33: "securityAccessDenied",
    0x35: "invalidKey",
    0x36: "exceededNumberOfAttempts",
    0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted",
    0x72: "generalProgrammingFailure",
    0x78: "requestCorrectlyReceivedResponsePending",
    0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}

NRC_HINTS: dict[int, str] = {
    0x11: "The service identifier is not implemented by this ECU.",
    0x12: "The sub-function value is not implemented for this service.",
    0x13: "Request length does not match the length expected for this service / identifier.",
    0x22: "Preconditions are not met (for example a routine is already running).",
    0x24: "Requests were sent in the wrong order (for example sendKey before requestSeed).",
    0x31: "A parameter (DID, RID, value, group) is unsupported, out of range or unavailable in this session.",
    0x33: "Security access is required and the ECU is locked.",
    0x35: "The key sent does not match the key computed by the ECU.",
    0x36: "Too many invalid key attempts; the ECU locks security access.",
    0x37: "A lock-out delay is still running after too many failed attempts.",
    0x78: "The ECU received the request and needs more time; a final response follows.",
    0x7E: "The sub-function is not available in the currently active session.",
    0x7F: "The service is not available in the currently active session.",
}


def nrc_name(code: int) -> str:
    return NRC_NAMES.get(code, f"manufacturerOrUnknown(0x{code:02X})")
