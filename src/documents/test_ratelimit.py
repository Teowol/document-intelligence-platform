"""Phase 9: rate limiting tests (threshold + reset behaviour)."""

import pytest
from django.core.exceptions import PermissionDenied

from conftest import make_user
from documents.ratelimit import is_rate_limited, require_rate_limit

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return make_user(username="rl")


def test_limit_allows_below_threshold(user):
    allowed = [not is_rate_limited(user, key="x", limit=3) for _ in range(3)]
    assert allowed == [True, True, True]


def test_limit_blocks_above_threshold(user):
    # consume the allowed count, then the next call is limited
    for _ in range(3):
        is_rate_limited(user, key="y", limit=3)
    assert is_rate_limited(user, key="y", limit=3) is True


def test_limits_are_key_independent(user):
    is_rate_limited(user, key="a", limit=1)
    assert is_rate_limited(user, key="b", limit=1) is False


def test_limits_are_user_independent(user, django_user_model):
    other = make_user(username="rl2", email="rl2@example.com")
    is_rate_limited(user, key="c", limit=1)
    assert is_rate_limited(other, key="c", limit=1) is False


def test_require_raises_when_exceeded(user):
    with pytest.raises(PermissionDenied):
        for _ in range(6):
            require_rate_limit(user, key="qa", limit=5)
