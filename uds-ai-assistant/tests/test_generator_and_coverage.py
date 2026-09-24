from uds_assistant.coverage import compute_coverage
from uds_assistant.generator.suites import build_suite


def test_full_suite_reaches_100_percent_coverage(profile):
    tests = build_suite(profile)
    cov = compute_coverage(profile, tests)
    assert cov["gaps"] == []
    assert cov["percent"] == 100.0
    assert len(tests) > 50


def test_setup_steps_are_all_positive(profile):
    tests = build_suite(profile)
    for t in tests:
        for s in t.steps:
            if s.role == "setup" and s.action == "send":
                assert s.expect == "positive", f"{t.id} step {s.n} setup step is not positive"


def test_every_test_has_at_least_one_test_role_step(profile):
    tests = build_suite(profile)
    for t in tests:
        assert any(s.role == "test" for s in t.steps), f"{t.id} has no 'test' role step"
