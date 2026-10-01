# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2023 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}
import inspect
import os
import re

import gevent
import gevent.lock
from watchdog.events import PatternMatchingEventHandler
from watchdog.utils.patterns import match_any_paths
import logging

_log = logging.getLogger(__name__)


def get_random_key(length: int = 65) -> str:
    """
    Returns a hex random key of specified length.  The length must be > 0 in order for
    the key to be valid.  Raises a ValueError if the length is invalid.

    The default length is 65, which is 130 in length when hexlify is run.

    :param length:
    :return:
    """
    if length <= 0:
        raise ValueError("Invalid length specified for random key must be > 0")

    import binascii
    random_key = binascii.hexlify(os.urandom(length)).decode('utf-8')
    return random_key


def is_ip_private(vip_address):
    """ Determines if the passed vip_address is a private ip address or not.

    :param vip_address: A valid ip address.
    :return: True if an internal ip address.
    """
    ip = vip_address.strip().lower().split("tcp://")[1]

    # https://en.wikipedia.org/wiki/Private_network

    priv_lo = re.compile(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    priv_24 = re.compile(r"^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    priv_20 = re.compile(r"^192\.168\.\d{1,3}.\d{1,3}$")
    priv_16 = re.compile(r"^172.(1[6-9]|2[0-9]|3[0-1]).[0-9]{1,3}.[0-9]{1,3}$")

    return priv_lo.match(ip) is not None or priv_24.match(
        ip) is not None or priv_20.match(ip) is not None or priv_16.match(
        ip) is not None


def get_hostname():
    with open('/etc/hostname') as fp:
        hostname = fp.read().strip()

    assert hostname
    return hostname

def monkey_patch():
    from gevent import monkey

    # At this point these are the only things that need to be patched
    # and the server and client are working harmoniously with this.
    patches = [
        ('ssl', monkey.patch_ssl),
        ('socket', monkey.patch_socket),
        ('os', monkey.patch_os),
    ]

    # patch modules if necessary.  Only if the module hasn't been patched before.
    # this could happen if the server code uses the client (which it does).
    for module, fn in patches:
        if not monkey.is_module_patched(module):
            fn()

class _GeventFileReloader(PatternMatchingEventHandler):
    """
    Base for the file reloaders.  Schedule it on the *directory* containing the
    file(s), never on the file itself: an inotify watch on a file follows its
    inode, so it dies silently the first time the file is replaced by a rename
    (atomic writes, editors, config management).

    Watchdog dispatches events on its own native thread.  Callbacks touch gevent
    and zmq state, so they are handed to the hub of the thread that created the
    reloader and run there in a greenlet, one at a time.  Exceptions are logged
    and never propagate back into watchdog, where they would kill the observer
    thread and stop all further events.
    """
    def __init__(self, patterns, path=None):
        super().__init__(patterns=patterns, ignore_directories=True)
        self._path = path
        self._hub = gevent.get_hub()
        self._lock = gevent.lock.Semaphore()
        self._last_signature = self._file_signature()

    def _invoke(self):
        raise NotImplementedError()

    def on_closed(self, event):
        # Only emitted for IN_CLOSE_WRITE, reads do not trigger a reload.
        self._schedule(event)

    def on_moved(self, event):
        # A file renamed into place, e.g. an atomic write.  Moves *away* from
        # the watched name are ignored.
        if match_any_paths([event.dest_path], included_patterns=self.patterns,
                           case_sensitive=self.case_sensitive):
            self._schedule(event)

    def _schedule(self, event):
        # Called on the watchdog thread.
        self._hub.loop.run_callback_threadsafe(gevent.spawn, self._run_callback, event)

    def _run_callback(self, event):
        with self._lock:
            self._last_signature = self._file_signature()
            _log.debug("Calling callback on event {}".format(event))
            try:
                self._invoke()
            except Exception:
                _log.exception("Exception in file watch callback for event {}".format(event))
            _log.debug("After callback on event {}".format(event))

    def _file_signature(self):
        if self._path is None:
            return None
        try:
            st = os.stat(self._path)
        except OSError:
            return None
        return st.st_ino, st.st_mtime_ns, st.st_size

    def poll(self, interval):
        """
        Safety net for missed file events: every `interval` seconds, run the
        callback if the file's inode, mtime or size differs from what the last
        callback saw.  Runs forever, so call it in its own greenlet.  Only
        available for reloaders watching a single concrete path.
        """
        if self._path is None:
            raise ValueError("polling requires a single file path")
        while True:
            gevent.sleep(interval)
            if self._file_signature() != self._last_signature:
                _log.warning("Change to {} detected by polling, file events were "
                             "missed".format(self._path))
                self._run_callback("poll")


class VolttronHomeFileReloader(_GeventFileReloader):
    """
    Extends PatternMatchingEvent handler to watch changes to a singlefile/file pattern within volttron home.
    filetowatch should be path relative to volttron home.
    For example filetowatch auth.json with watch file <volttron_home>/auth.json.
    filetowatch *.json will watch all json files in <volttron_home>

    Schedule on <volttron_home>, see _GeventFileReloader.
    """
    def __init__(self, filetowatch, callback):
        # Protect from circular reference for file
        from volttron.platform import get_home

        super(VolttronHomeFileReloader, self).__init__([get_home() + '/' + filetowatch])
        _log.debug("patterns is {}".format([get_home() + '/' + filetowatch]))
        self._callback = callback

    def _invoke(self):
        self._callback()


class AbsolutePathFileReloader(_GeventFileReloader):
    """
    Extends PatternMatchingEvent handler to watch changes to a single file
    given by its absolute path.  The callback is called with that path.

    Schedule on the file's directory, see _GeventFileReloader.
    """
    def __init__(self, filetowatch, callback):
        super(AbsolutePathFileReloader, self).__init__([filetowatch], path=filetowatch)
        self._callback = callback
        self._filetowatch = filetowatch

    @property
    def watchfile(self):
        return self._filetowatch

    def _invoke(self):
        self._callback(self._filetowatch)


def print_stack():
    """
    Utility function to print the full frames stack of a function call.

    The format of the stack is filename->function:lineno
    """
    called = 0
    for x in inspect.stack():
        _log.debug(f"stack: [{called}] {x.filename}->{x.function}:{x.lineno}")
        called += 1
