"""
Unit tests for the proxy's scrape deadline: no platform or BACnet network needed.

The real BACnetProxyAgent read loop runs against a fake BACnet application that answers each request
after a scripted delay, so we can check partial results and the cause reported when time runs out.
"""
import types

import gevent
import pytest
from gevent.event import AsyncResult

from bacnet_proxy.agent import BACnetProxyAgent
from bacnet_proxy.scrape_budget import (CAUSE_SLOW, CAUSE_UNKNOWN, CAUSE_UNRESPONSIVE,
                                        ScrapeBudget)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_deadline_leaves_margin_before_caller_timeout():
    clock = FakeClock()
    assert ScrapeBudget(180, 1, clock).remaining() == pytest.approx(175)  # margin capped at 5s
    assert ScrapeBudget(10, 1, clock).remaining() == pytest.approx(9)     # 10% margin
    assert ScrapeBudget(None, 1, clock).remaining() is None


def test_finished_scrape_reports_actual_time():
    clock = FakeClock()
    budget = ScrapeBudget(30, 2, clock)
    budget.record_answered()
    budget.record_answered()
    clock.now += 12
    stats = budget.to_dict()
    assert stats["deadline_hit"] is False
    assert stats["cause"] is None
    assert stats["estimated_seconds"] == pytest.approx(12)


@pytest.mark.parametrize("answers, cause", [
    ([True, True], CAUSE_SLOW),
    ([False, True], CAUSE_SLOW),
    ([True, False], CAUSE_UNRESPONSIVE),
    ([], CAUSE_UNKNOWN),
])
def test_cause_follows_last_finished_request(answers, cause):
    budget = ScrapeBudget(30, 10, FakeClock())
    for answered in answers:
        budget.record_answered() if answered else budget.record_no_response()
    budget.record_deadline_hit()
    assert budget.cause() == cause


def test_cut_short_scrape_projects_full_time():
    clock = FakeClock()
    budget = ScrapeBudget(60, 10, clock)
    for _ in range(4):
        budget.record_answered()
    clock.now += 55
    budget.record_deadline_hit()
    stats = budget.to_dict()
    assert stats["skipped"] == 6
    assert stats["estimated_seconds"] == pytest.approx(55 / 4 * 10)


# --- the proxy read loop -------------------------------------------------------------------------

class FakeApplication:
    """Answers request n after delays[n] seconds: "ok" -> {}, "noResponse" -> RuntimeError."""

    def __init__(self, script):
        self.script = list(script)
        self.sent = 0

    def submit_request(self, iocb):
        delay, outcome = self.script[self.sent]
        self.sent += 1

        def answer():
            gevent.sleep(delay)
            if outcome == "ok":
                iocb.ioResult.set({})
            else:
                iocb.ioResult.set_exception(RuntimeError("Device communication aborted: noResponse"))
        gevent.spawn(answer)


class FakeIOCB:
    def __init__(self, request):
        self.ioRequest = request
        self.ioResult = AsyncResult()


def make_proxy(script):
    proxy = types.SimpleNamespace(bacnet_application=FakeApplication(script), iocb_class=FakeIOCB,
                                  _max_per_request=1)
    for name in ("read_properties", "_read_using_multiple_requests", "_get_object_properties",
                 "_get_access_spec", "_json_safe", "read_using_single_request", "_read_property_or_raise",
                 "is_valid_json"):
        setattr(proxy, name, types.MethodType(getattr(BACnetProxyAgent, name), proxy))
    return proxy


POINTS = {f"p{i}": ["analogInput", i, "presentValue"] for i in range(5)}


def test_slow_device_returns_partial_results_with_slow_cause():
    # 5 requests at 0.2s each need 1s; the 0.5s timeout (0.45s deadline) only fits 2.
    proxy = make_proxy([(0.2, "ok")] * 5)
    response = proxy.read_properties("10.0.0.1", POINTS, 1, True, timeout=0.5, return_stats=True)
    stats = response["stats"]
    assert stats["deadline_hit"] is True
    assert stats["cause"] == CAUSE_SLOW
    assert stats["answered"] == 2
    assert stats["skipped"] == 3
    assert stats["estimated_seconds"] == pytest.approx(1.1, abs=0.2)
    assert proxy.bacnet_application.sent == 3  # third request was in flight at the deadline


def test_unresponsive_device_reports_unresponsive_cause():
    proxy = make_proxy([(0.1, "ok"), (0.1, "noResponse")] + [(0.3, "noResponse")] * 3)
    stats = proxy.read_properties("10.0.0.1", POINTS, 1, True, timeout=0.5, return_stats=True)["stats"]
    assert stats["deadline_hit"] is True
    assert stats["cause"] == CAUSE_UNRESPONSIVE


def test_scrape_within_timeout_is_not_flagged():
    proxy = make_proxy([(0.01, "ok")] * 5)
    stats = proxy.read_properties("10.0.0.1", POINTS, 1, True, timeout=5, return_stats=True)["stats"]
    assert stats["deadline_hit"] is False
    assert stats["answered"] == 5
    assert stats["cause"] is None


def test_old_callers_get_plain_results():
    proxy = make_proxy([(0.01, "ok")] * 5)
    assert proxy.read_properties("10.0.0.1", POINTS, 1, True) == {}


def test_single_request_path_honors_deadline():
    proxy = make_proxy([(0.2, "ok")] * 5)
    response = proxy.read_properties("10.0.0.1", POINTS, 1, False, timeout=0.5, return_stats=True)
    assert response["stats"]["deadline_hit"] is True
    assert response["stats"]["cause"] == CAUSE_SLOW
    assert len(response["results"]) == 2
