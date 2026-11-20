"""
Time budget for a single multi-request scrape of one BACnet device.

The platform driver passes its per-device ``timeout`` with each scrape. The proxy turns that into a
deadline that covers every request it sends for that scrape, and uses this class to track how far it
got. When the deadline passes, the proxy stops sending requests and returns what it has, along with
``to_dict()`` so the driver can report *why* the scrape was cut short:

- ``slow``: the device answered the last request before the deadline; it just has more data than
  fits in the timeout. Raising the device's ``timeout`` (to about ``estimated_seconds``) fixes it.
- ``unresponsive``: the last request got no answer (bacpypes ``noResponse``). A longer timeout won't help.
- ``unknown``: no request finished before the deadline, so there is nothing to judge by.
"""

import time

# Stop this long before the caller's own timeout so the partial results still reach it.
DEADLINE_MARGIN_MAX = 5.0
DEADLINE_MARGIN_FRACTION = 0.1

CAUSE_SLOW = "slow"
CAUSE_UNRESPONSIVE = "unresponsive"
CAUSE_UNKNOWN = "unknown"


class ScrapeBudget:
    def __init__(self, timeout, total_requests, clock=time.monotonic):
        self._clock = clock
        self.started = clock()
        self.timeout = float(timeout) if timeout is not None else None
        if self.timeout is None:
            self.deadline = None
        else:
            margin = min(DEADLINE_MARGIN_MAX, self.timeout * DEADLINE_MARGIN_FRACTION)
            self.deadline = self.started + max(self.timeout - margin, 0.0)
        self.total_requests = total_requests
        self.answered = 0
        self.no_response = 0
        self.last_answered = None
        self.deadline_hit = False

    def remaining(self):
        """Seconds left before the deadline, or None when there is no deadline."""
        if self.deadline is None:
            return None
        return max(self.deadline - self._clock(), 0.0)

    def expired(self):
        return self.deadline is not None and self._clock() >= self.deadline

    def record_answered(self):
        """The device replied to a request (with data or with a BACnet error)."""
        self.answered += 1
        self.last_answered = True

    def record_no_response(self):
        self.no_response += 1
        self.last_answered = False

    def record_deadline_hit(self):
        self.deadline_hit = True

    @property
    def completed(self):
        return self.answered + self.no_response

    def cause(self):
        if not self.deadline_hit:
            return None
        if self.last_answered is None:
            return CAUSE_UNKNOWN
        return CAUSE_SLOW if self.last_answered else CAUSE_UNRESPONSIVE

    def estimated_seconds(self):
        """
        How long a full scrape takes. When the scrape finished, that is the time it took; when it was
        cut short, it is projected from the average time per finished request.
        """
        elapsed = self._clock() - self.started
        if not self.deadline_hit:
            return elapsed
        if self.completed == 0:
            return None
        return elapsed / self.completed * self.total_requests

    def to_dict(self):
        return {
            "elapsed": self._clock() - self.started,
            "total_requests": self.total_requests,
            "answered": self.answered,
            "no_response": self.no_response,
            "skipped": self.total_requests - self.completed,
            "deadline_hit": self.deadline_hit,
            "cause": self.cause(),
            "estimated_seconds": self.estimated_seconds(),
        }
