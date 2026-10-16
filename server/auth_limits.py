"""Small bounded login throttle for this single-worker demo deployment."""

import time
from collections import OrderedDict, deque

BUCKETS = OrderedDict()


def allow(ip, limit=30):
    current = time.monotonic()
    attempts = BUCKETS.pop(ip, deque())
    while attempts and attempts[0] < current - 900:
        attempts.popleft()
    accepted = len(attempts) < limit
    if accepted:
        attempts.append(current)
    BUCKETS[ip] = attempts
    while len(BUCKETS) > 2000:
        BUCKETS.popitem(last=False)
    return accepted
