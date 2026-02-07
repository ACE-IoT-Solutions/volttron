# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:
#
# Copyright 2020, Battelle Memorial Institute.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This material was prepared as an account of work sponsored by an agency of
# the United States Government. Neither the United States Government nor the
# United States Department of Energy, nor Battelle, nor any of their
# employees, nor any jurisdiction or organization that has cooperated in the
# development of these materials, makes any warranty, express or
# implied, or assumes any legal liability or responsibility for the accuracy,
# completeness, or usefulness or any information, apparatus, product,
# software, or process disclosed, or represents that its use would not infringe
# privately owned rights. Reference herein to any specific commercial product,
# process, or service by trade name, trademark, manufacturer, or otherwise
# does not necessarily constitute or imply its endorsement, recommendation, or
# favoring by the United States Government or any agency thereof, or
# Battelle Memorial Institute. The views and opinions of authors expressed
# herein do not necessarily state or reflect those of the
# United States Government or any agency thereof.
#
# PACIFIC NORTHWEST NATIONAL LABORATORY operated by
# BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
# under Contract DE-AC05-76RL01830
# }}}

from orjson import dumps as _dumps, loads as _loads


__all__ = ('dump', 'dumpb', 'dumps', 'load', 'loadb', 'loads')


def dumpb(data, **kwargs):
    return _dumps(data, **kwargs)


def loadb(s, **kwargs):
    return _loads(s, **kwargs)

def dumps(data, **kwargs):
    return _dumps(data, **kwargs).decode('utf-8')

def loads(s, **kwargs):
    return _loads(s.encode('utf-8'), **kwargs)

def dump(data, fp, **kwargs):
    fp.write(dumps(data, **kwargs).decode('utf-8'))

def load(fp, **kwargs):
    if isinstance(fp, io.TextIOBase):
        return _loads(fp.read().encode('utf-8'), **kwargs)
    else:
        return _loads(fp.read(), **kwargs)
