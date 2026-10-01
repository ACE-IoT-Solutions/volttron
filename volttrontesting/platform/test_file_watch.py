import os
import sys
import threading

import gevent
import pytest
from watchdog.events import FileClosedEvent, FileMovedEvent

from volttron.platform.agent.utils import watch_file
from volttron.utils import AbsolutePathFileReloader


def _wait_for(predicate, timeout=5.0):
    with gevent.Timeout(timeout, False):
        while not predicate():
            gevent.sleep(0.05)
    return predicate()


def _dispatch_from_thread(handler, event):
    """Dispatch an event the way watchdog does, from a native thread."""
    thread = threading.Thread(target=handler.dispatch, args=(event,))
    thread.start()
    thread.join()


@pytest.fixture
def watched_file(tmpdir):
    path = tmpdir.join("watched.json")
    path.write("{}")
    return str(path)


def test_callback_runs_on_hub_thread(watched_file):
    calls = []
    handler = AbsolutePathFileReloader(watched_file, lambda path: calls.append(
        (path, threading.get_ident())))

    _dispatch_from_thread(handler, FileClosedEvent(watched_file))

    assert _wait_for(lambda: calls)
    assert calls == [(watched_file, threading.get_ident())]


def test_callback_can_block_on_gevent(watched_file):
    done = []

    def callback(path):
        gevent.sleep(0.1)
        done.append(path)

    handler = AbsolutePathFileReloader(watched_file, callback)
    _dispatch_from_thread(handler, FileClosedEvent(watched_file))

    assert _wait_for(lambda: done)


def test_exception_does_not_reach_watchdog_thread(watched_file):
    calls = []

    def callback(path):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError("boom")

    handler = AbsolutePathFileReloader(watched_file, callback)
    errors = []

    def dispatch(event):
        try:
            handler.dispatch(event)
        except BaseException as exc:
            errors.append(exc)

    for _ in range(2):
        thread = threading.Thread(target=dispatch, args=(FileClosedEvent(watched_file),))
        thread.start()
        thread.join()

    assert _wait_for(lambda: len(calls) == 2)
    assert errors == []


def test_move_into_place_triggers_and_move_away_does_not(watched_file):
    calls = []
    handler = AbsolutePathFileReloader(watched_file, calls.append)
    tmp_path = watched_file + ".tmp"

    _dispatch_from_thread(handler, FileMovedEvent(watched_file, tmp_path))
    gevent.sleep(0.2)
    assert calls == []

    _dispatch_from_thread(handler, FileMovedEvent(tmp_path, watched_file))
    assert _wait_for(lambda: calls)


def test_events_for_other_files_are_ignored(watched_file):
    calls = []
    handler = AbsolutePathFileReloader(watched_file, calls.append)

    _dispatch_from_thread(handler, FileClosedEvent(watched_file + ".other"))
    gevent.sleep(0.2)
    assert calls == []


def test_callbacks_do_not_overlap(watched_file):
    active = []
    overlapped = []
    calls = []

    def callback(path):
        if active:
            overlapped.append(path)
        active.append(path)
        gevent.sleep(0.1)
        active.pop()
        calls.append(path)

    handler = AbsolutePathFileReloader(watched_file, callback)
    for _ in range(3):
        _dispatch_from_thread(handler, FileClosedEvent(watched_file))

    assert _wait_for(lambda: len(calls) == 3)
    assert overlapped == []


def test_poll_detects_missed_change(watched_file):
    calls = []
    handler = AbsolutePathFileReloader(watched_file, calls.append)
    poller = gevent.spawn(handler.poll, 0.1)
    try:
        gevent.sleep(0.3)
        assert calls == []

        with open(watched_file, "w") as fp:
            fp.write('{"changed": true}')
        assert _wait_for(lambda: calls)

        # No further calls once the change has been seen.
        count = len(calls)
        gevent.sleep(0.3)
        assert len(calls) == count
    finally:
        poller.kill()


def test_poll_skips_change_already_handled_by_event(watched_file):
    calls = []
    handler = AbsolutePathFileReloader(watched_file, calls.append)
    poller = gevent.spawn(handler.poll, 0.2)
    try:
        with open(watched_file, "w") as fp:
            fp.write('{"changed": true}')
        _dispatch_from_thread(handler, FileClosedEvent(watched_file))
        assert _wait_for(lambda: calls)
        gevent.sleep(0.5)
        assert len(calls) == 1
    finally:
        poller.kill()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="inotify only")
def test_watch_file_survives_atomic_replace(watched_file):
    calls = []
    watcher = gevent.spawn(watch_file, watched_file, lambda: calls.append(1))
    gevent.sleep(0.5)
    try:
        for i in range(3):
            tmp_path = watched_file + ".tmp"
            with open(tmp_path, "w") as fp:
                fp.write('{"n": %d}' % i)
            os.replace(tmp_path, watched_file)
            assert _wait_for(lambda: len(calls) == i + 1), "missed replace %d" % i

        with open(watched_file, "w") as fp:
            fp.write('{"in_place": true}')
        assert _wait_for(lambda: len(calls) == 4)

        # Reading the file must not trigger a reload.
        with open(watched_file) as fp:
            fp.read()
        gevent.sleep(0.5)
        assert len(calls) == 4
    finally:
        watcher.kill()
