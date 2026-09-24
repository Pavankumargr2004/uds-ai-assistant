import pytest

from uds_assistant.protocol.profile import load_profile

PROFILE_PATH = "data/samples/bcm_ecu_profile.yaml"


@pytest.fixture(scope="session")
def profile():
    return load_profile(PROFILE_PATH)
