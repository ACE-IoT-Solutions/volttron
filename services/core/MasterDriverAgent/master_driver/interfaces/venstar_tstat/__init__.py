# Copyright (c) 2019, ACE IoT Solutions LLC.
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
The Venstar  Driver allows control and monitoring of Venstar Thermostats via an HTTP API
"""

import logging
import time
import copy

import grequests

from volttron.platform.agent import utils
from master_driver.interfaces import BaseRegister, BaseInterface, BasicRevert


VENSTAR_LOGGER = logging.getLogger("venstar_tstat")
VENSTAR_LOGGER.setLevel(logging.WARNING)


class Register(BaseRegister):
    """
    Generic class for containing information about the points exposed by the Venstar API


    :param register_type: Type of the register. Either "bit" or "byte". Usually "byte".
    :param pointName: Name of the register.
    :param units: Units of the value of the register.
    :param description: Description of the register.

    :type register_type: str
    :type pointName: str
    :type units: str
    :type description: str

    The TED Meter Driver does not expose the read_only parameter, as the TED API does not
    support writing data.
    """

    def __init__(self, volttron_point_name, units, description):
        super(Register, self).__init__("byte",
                                       True,
                                       volttron_point_name,
                                       units,
                                       description=description)


class Interface(BasicRevert, BaseInterface):
    """Create an interface for the Venstar Thermostat using the standard BaseInterface convention
    """

    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.device_path = kwargs.get("device_path")
        self.logger = VENSTAR_LOGGER

    def configure(self, config_dict, registry_config_str):
        """Configure method called by the master driver with configuration 
        stanza and registry config file, we ignore the registry config, using 
        standard layout for the thermostat properties
        """
        self.device_address = config_dict['device_address']
        self.timeout = config_dict.get('timeout', 5)
        self.track_totalizers = config_dict.get('track_totalizers', True)
        self.init_time = time.time()
        # self.ted_config = self._get_ted_configuration()
        # self._create_registers(self.ted_config)
        # if self.track_totalizers:
        #     self._get_totalizer_state()

    def _get_totalizer_state(self):
        """
        Sets up the totalizer state in the config store to allow perstistence
        of cumulative totalizers, despite regular resets of the totalizers on
        the device.
        """
        try:
            totalizer_state = self.vip.config.get("state/ted_meter/{}".format(self.device_path))
        except KeyError:
            totalizer_state = {register_name: {
                "total": 0, "last_read": 0
            } for register_name in self.get_register_names(
            ) if self.get_register_by_name(register_name).units == "kWh" and "_totalized" in register_name}
            self.vip.config.set("state/ted_meter/{}".format(self.device_path), totalizer_state)
        self.totalizer_state = totalizer_state

    def _get_tstat_configuration(self):
        """
        Retrieves the TED Pro configuration from the device, used to build the registers
        """
        req = (grequests.get(
            "http://{tstat_host}/query/info".format(ted_host=self.device_address))
            )
        system, = grequests.map(req)
        if system.status_code != 200:
            raise Exception(
                "Invalid response from meter, check config, received status code: {}".format(system.status_code))
        config = {}
        return config
    
    def insert_register(self, register):
        """
        We override the default insert_register behavior so that we can
        automatically create additional totalized registers when 
        ``track_totalizers`` is True
        """
        super(Interface, self).insert_register(register)
        if self.track_totalizers:
            if register.units == 'kWh':
                totalized_register = copy.deepcopy(register)
                totalized_register.point_name = register.point_name + "_totalized"
                super(Interface, self).insert_register(totalized_register)

    def _create_registers(self, ted_config):
        """
        Processes the config scraped from the TED Pro device and generates
        register for each available parameter
        """
        return

    def _set_points(self, points):
        requests = (grequests.post(f'http://{self.device_address}/control', timeout=self.timeout, data=points),)
        response, = grequests.map(requests)
        if response.status_code != 200:
            raise Exception(
                    "Invalid response from thermostat, check config, received status code: {}, response: {}".format(response.status_code, response.text))



    def _set_point(self, point_name, value):
        """
        TED has no writable points, so skipping set_point method
        """
        self._set_points({point_name: value})


    def get_point(self, point_name):
        points = self._scrape_all()
        return points.get(point_name)


    def get_data(self):
        """
        returns a tuple of ETree objects corresponding to the three aapi endpoints
        """
        # requests = [grequests.get(url, auth=(self.username, self.password), timeout=self.timeout) for url in (
        #     "http://{tstat_host}/query/info".format(
        #         tstat_host=self.device_address),
        # )
        # ]
        requests = [grequests.get(url, timeout=self.timeout) for url in (
            "http://{tstat_host}/query/info".format(
                tstat_host=self.device_address),
        )
        ]
        system, = grequests.map(requests)
        for response in (system,):
            if response.status_code != 200:
                raise Exception(
                    "Invalid response from meter, check config, received status code: {}".format(response.status_code))
        
        return (system.json(),)


    def _scrape_all(self):
        output = {}
        system_data, = self.get_data()
        output = system_data
        del output['name']
        return output

    def _get_totalized_value(self, point_name, read_value, multiplier):
        """
        processes the read value and returns the totalized value, based on the
        internal state tracking
        """

        totalizer_point_name = point_name + '_totalized'
        totalizer_value = self.totalizer_state.get(totalizer_point_name)
        if totalizer_value is not None:
            total, last_read = totalizer_value["total"], totalizer_value["last_read"]
            if read_value >= total:
                self.totalizer_state[totalizer_point_name]["total"] = read_value
                actual = read_value
            else:
                if read_value >= last_read:
                    self.totalizer_state[totalizer_point_name]["total"] += read_value - last_read 
                else:
                    self.totalizer_state[totalizer_point_name]["total"] += read_value
                actual = self.totalizer_state[totalizer_point_name]["total"]
            self.totalizer_state[totalizer_point_name]["last_read"] = read_value
            self.vip.config.set('state/ted_meter/{}'.format(self.device_path),
                                self.totalizer_state)
        else:
            actual = read_value
        return actual * multiplier
