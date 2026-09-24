import pytest

from uds_assistant.generator.suites import build_suite
from uds_assistant.runner.runner import Runner
from uds_assistant.runner.transport import SimTransport
from uds_assistant.simulator.mock_ecu import FAULTS


def test_generated_suite_passes_against_clean_ecu(profile):
    tests = build_suite(profile)
    summary = Runner(profile, SimTransport(profile)).run(tests)
    assert summary.errors == 0
    assert summary.failed == 0
    assert summary.passed == summary.total


@pytest.mark.parametrize("fault", sorted(FAULTS))
def test_every_injected_fault_is_caught_by_some_test(profile, fault):
    tests = build_suite(profile)
    summary = Runner(profile, SimTransport(profile, faults=[fault])).run(tests, faults=[fault])
    assert summary.failed + summary.errors > 0, f"fault {fault!r} was not detected by any generated test"
