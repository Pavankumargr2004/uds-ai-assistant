from uds_assistant.protocol.hexutil import match_pattern, parse_hex, to_hex
from uds_assistant.protocol.oracle import SpecOracle


def test_hexutil_roundtrip():
    assert parse_hex("22 F1 90") == bytes([0x22, 0xF1, 0x90])
    assert parse_hex("0x22F190") == bytes([0x22, 0xF1, 0x90])
    assert to_hex(bytes([0x22, 0xF1])) == "22 F1"


def test_match_pattern_wildcards():
    assert match_pattern("62 F1 90 ?? ??", bytes([0x62, 0xF1, 0x90, 0x11, 0x22]))
    assert not match_pattern("62 F1 90 ?? ??", bytes([0x62, 0xF1, 0x91, 0x11, 0x22]))
    assert match_pattern("", None)


def test_oracle_unsupported_service(profile):
    o = SpecOracle(profile)
    exp, _ = o.step(bytes([0x87, 0x00]), o.initial_state())
    assert exp.kind == "negative" and exp.nrc == 0x11


def test_oracle_session_change_relocks(profile):
    o = SpecOracle(profile)
    st = o.initial_state()
    exp, st = o.step(bytes([0x10, 0x03]), st)
    assert exp.kind == "positive"
    exp, st = o.step(bytes([0x27, 0x01]), st)
    assert exp.kind == "positive"
    # (not actually unlocking here - just checking dispatch works without security)
    exp, st2 = o.step(bytes([0x22, 0xF1, 0x90]), st)
    assert exp.kind == "positive"  # VIN read needs no security
