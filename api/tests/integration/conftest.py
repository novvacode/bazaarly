import pytest


@pytest.fixture(autouse=True)
def _integration_clean_state(clean_state: None) -> None:
    """Every integration test starts from empty tables and an empty Redis DB."""
