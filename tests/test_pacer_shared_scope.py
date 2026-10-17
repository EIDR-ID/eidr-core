"""RequestPacer(shared_scope=...) (0.61.0): one pace for every process on the
machine. Wrong answers here are silent -- two programs both "pacing" while
together breaking the server's limit -- so the tests run real processes."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from eidr_core.external import RequestPacer


class FakeClock:
    def __init__(self):
        self.t = 1_000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 6))
        self.t += s


def test_two_pacers_with_one_scope_share_the_spacing(tmp_path):
    c = FakeClock()
    a = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="t", scope_dir=tmp_path)
    b = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="t", scope_dir=tmp_path)
    a.wait()
    b.wait()                       # a different instance, the same scope
    assert c.slept == [0.3]


def test_back_off_reaches_every_pacer_in_the_scope(tmp_path):
    c = FakeClock()
    a = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="t", scope_dir=tmp_path)
    b = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="t", scope_dir=tmp_path)
    a.back_off(7)
    b.wait()
    assert c.slept == [7.0]


def test_different_scopes_and_no_scope_stay_independent(tmp_path):
    c = FakeClock()
    a = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="one", scope_dir=tmp_path)
    b = RequestPacer(clock=c.now, sleep=c.sleep, shared_scope="two", scope_dir=tmp_path)
    plain = RequestPacer(clock=c.now, sleep=c.sleep)
    a.wait()
    b.wait()
    plain.wait()
    assert c.slept == []


def test_a_bad_scope_name_is_refused(tmp_path):
    with pytest.raises(ValueError):
        RequestPacer(shared_scope="../escape", scope_dir=tmp_path)


def test_the_slot_is_held_across_instances(tmp_path):
    # Two instances in two threads: without the shared slot their bodies
    # overlap, because each instance has its own threading semaphore.
    spans = []
    lock = threading.Lock()

    def run():
        p = RequestPacer(min_interval=0.0, shared_scope="slot", scope_dir=tmp_path)
        for _ in range(3):
            with p.request():
                start = time.time()
                time.sleep(0.05)
                with lock:
                    spans.append((start, time.time()))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    spans.sort()
    assert len(spans) == 6
    assert all(b[0] >= a[1] - 0.005 for a, b in zip(spans, spans[1:], strict=False))


def test_two_processes_share_one_pace(tmp_path):
    # Real processes: each makes 3 requests; together, starts are at least
    # min_interval apart and no two bodies overlap.
    script = textwrap.dedent(f"""
        import json, sys, time
        from eidr_core.external import RequestPacer
        p = RequestPacer(min_interval=0.2, shared_scope="proc", scope_dir={str(tmp_path)!r})
        out = []
        for _ in range(3):
            with p.request():
                s = time.time(); time.sleep(0.03); out.append((s, time.time()))
        print(json.dumps(out))
    """)
    procs = [subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
             for _ in range(2)]
    spans = []
    for pr in procs:
        out, _ = pr.communicate(timeout=60)
        assert pr.returncode == 0
        spans += [tuple(s) for s in json.loads(out)]
    spans.sort()
    assert len(spans) == 6
    starts = [s for s, _ in spans]
    # The pacer spaces the CLAIMED starts 0.2 s apart; the body's own clock
    # reading comes a little after its claim, by a scheduler-dependent amount
    # (CI saw one gap of 0.179 s), so each measured gap gets slack and the
    # whole run must still take at least five intervals.
    assert all(b - a >= 0.12 for a, b in zip(starts, starts[1:], strict=False)), starts
    assert starts[-1] - starts[0] >= 5 * 0.2 - 0.05, starts
    assert all(b[0] >= a[1] - 0.005 for a, b in zip(spans, spans[1:], strict=False))
