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



import errno


__all__ = ['VIPError', 'Unreachable', 'Again', 'UnknownSubsystem']


class VIPError(Exception):
    def __init__(self, errnum, msg, peer, subsystem, *args):
        super(VIPError, self).__init__(errnum, msg, peer, subsystem, *args)
        self.errno = int(errnum)
        self.msg = msg
        self.peer = peer
        self.subsystem = subsystem

    def __str__(self):
        return 'VIP error (%d): %s' % (self.errno, self.msg)

    def __repr__(self):
        return '%s%r' % (type(self).__name__, self.args)

    @classmethod
    def from_errno(cls, errnum, msg, *args):
        original_errnum = errnum
        # Handle both integer error numbers and string representations like 'Errno.EHOSTUNREACH'
        if isinstance(errnum, str):
            # Try to parse string format like 'Errno.EHOSTUNREACH'
            if errnum.startswith('Errno.'):
                error_name = errnum.split('.', 1)[1]  # Get 'EHOSTUNREACH' part
                # Get the errno value from the errno module
                if hasattr(errno, error_name):
                    errnum = getattr(errno, error_name)
                else:
                    # If we can't find the errno, try to extract a number if present
                    try:
                        import re
                        match = re.search(r'\d+', errnum)
                        if match:
                            errnum = int(match.group())
                        else:
                            # Default to a generic error code if we can't parse it
                            errnum = errno.EIO  # Generic I/O error
                    except Exception as e:
                        errnum = errno.EIO
            else:
                # Try to convert string to int directly
                try:
                    errnum = int(errnum)
                except ValueError:
                    # Default to a generic error code if we can't parse it
                    errnum = errno.EIO  # Generic I/O error
        else:
            errnum = int(errnum)
        
        return {
            errno.EHOSTUNREACH: Unreachable,
            errno.EAGAIN: Again,
            errno.EPROTONOSUPPORT: UnknownSubsystem,
        }.get(errnum, cls)(errnum, msg, *args)


class Unreachable(VIPError):
    def __str__(self):
        return '%s: %s' % (super(Unreachable, self).__str__(), self.peer)


class Again(VIPError):
    pass


class UnknownSubsystem(VIPError):
    def __str__(self):
        return '%s: %s' % (
            super(UnknownSubsystem, self).__str__(), self.subsystem)