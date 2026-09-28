# Copyright (c) 2024, ACE IoT Solutions LLC.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.

"""
The Sol Ark Driver allows monitoring of Sol Ark data via an HTTP API
"""

import logging
import time

from volttron.platform.agent import utils
from platform_driver.interfaces import BaseRegister, BaseInterface, BasicRevert
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub
from volttron.platform.messaging.health import STATUS_GOOD, STATUS_BAD

from .solark import fetch_bearer_token, get_plant_flow

_log = logging.getLogger("solark")

# plant/energy/{id}/flow, not plant/{id}/realtime: flow carries PV power AND
# battery SOC/charge/discharge in one response, so one call covers everything
# downstream consumers (e.g. racer_optimization) need. Calling both realtime
# and flow every scrape doubled the request rate and got this driver rate
# limited -- flow alone is also what TAMU's own reference code calls.
DEFAULT_POINTS = ["pvPower", "soc", "battPower", "batTo", "toBat", "loadOrEpsPower"]

class Register(BaseRegister):
    """
    Generic class for containing information about the points exposed by the Sol Ark API


    :param register_type: Type of the register. Either "bit" or "byte". Usually "byte".
    :param pointName: Name of the register.
    :param units: Units of the value of the register.
    :param description: Description of the register.

    :type register_type: str
    :type pointName: str
    :type units: str
    :type description: str
    """

    def __init__(self, volttron_point_name, units, description):
        super(Register, self).__init__(
            "byte", True, volttron_point_name, units, description=description
        )


class Interface(BasicRevert, BaseInterface):
    """
    Create an interface for the Sol Ark API using the standard BaseInterface convention
    """

    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.device_path = kwargs.get("device_path")
        self.logger = _log

    def configure(self, config_dict, registry_config_str):
        """
        Configure method called by the platform driver with configuration
        stanza and registry config file
        """
        self.username = config_dict["username"]
        self.password = config_dict["password"]
        self.api_key = config_dict["api_key"]
        self.client_id = config_dict["client_id"]
        self.plant_id = config_dict["plant_id"]
        _log.info("setting up solark interface")
        # _log.debug(f"{user_exists(self.username)}")
        self.token = fetch_bearer_token(self.api_key, self.username, self.password)
        if self.token is None:
            _log.error("Failed to fetch bearer token. Please check your credentials.")
            self.vip.health.set_status(STATUS_BAD, "Failed to fetch bearer token")
            return
        self.vip.health.set_status(STATUS_GOOD, "Bearer token fetched successfully")
        _log.debug(f"...{self.token[-3:]}")

        for entry in DEFAULT_POINTS:
            _log.debug(f"inserting register {entry=}")
            self.insert_register(Register(entry, "", ""))

    def _create_registers(self, ted_config):
        """
        Processes the config scraped from the device and generates
        register for each available parameter
        """
        return

    def _set_points(self, points):
        pass

    def _set_point(self, point_name, value):
        return self._set_points({point_name: value})

    def get_point(self, point_name):
        points = self._scrape_all()
        return points.get(point_name)
    
    @staticmethod
    def _to_float(point_name, value):
        """
        Cast a scraped point value to float. Historians (e.g. the Postgres/Timescale
        views) expect numeric values, but batTo/toBat come back from SolArk's API as
        booleans (or, in some responses, the strings "true"/"false") rather than 0/1,
        so those are mapped to 1.0/0.0. Anything else that isn't numeric has no
        meaningful float value, so it's dropped rather than published as a string
        downstream consumers can't handle.
        :param point_name: name of the point the value belongs to, for logging
        :param value: raw value returned by the SolArk API for this point
        :return: value cast to float, or None if it could not be cast (caller should drop it)
        """
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            value = value.strip().lower() == "true"
        try:
            return float(value)
        except (TypeError, ValueError) as e:
            _log.error(f"Dropping SolArk point {point_name}: could not cast value {value!r} to float: {e}")
            return None

    def filter_valid_points(self, points):
        new_points = {}
        _log.debug(f"filtering points: {points}")
        for point, value in points.items():
            if point not in DEFAULT_POINTS:
                continue
            cast_value = self._to_float(point, value)
            if cast_value is not None:
                new_points[point] = cast_value
        return new_points

    def _scrape_all(self):
        output = get_plant_flow(self.plant_id, self.api_key, self.token) or {}
        data = self.filter_valid_points(output)
        _log.debug(f"scraping solark: {data}")
        return data
