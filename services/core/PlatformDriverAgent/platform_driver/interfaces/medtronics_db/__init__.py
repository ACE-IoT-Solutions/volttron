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
The Venstar  Driver allows control and monitoring of Venstar Thermostats via an HTTP API
"""

import logging
import time
import copy
import pyodbc
import grequests

from datetime import datetime, timezone, timedelta

from volttron.platform.agent import utils
from platform_driver.interfaces import BaseRegister, BaseInterface, BasicRevert
from volttron.platform.vip.agent import Agent, Core, RPC, PubSub

_log = logging.getLogger("venstar_tstat")
#VENSTAR_LOGGER.setLevel(logging.WARNING)


class Register(BaseRegister):
    """
    Generic class for containing information about the points in Medtronic DB


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
        super(Register, self).__init__("byte",
                                       True,
                                       volttron_point_name,
                                       units,
                                       description=description)


class Interface(BasicRevert, BaseInterface):
    """Create an interface for the Medtronic DB using the standard BaseInterface convention
    """
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.db_conn_str = None

    def configure(self, config_dict, registry_config_str):
        """Required"""
        self.client = config_dict.get('client', 'test')
        self.site = config_dict.get('site', 'test')
        db_driver = config_dict.get('db_driver', 'sqlite')
        db_server = config_dict.get('db_server', 'localhost')
        db_port = config_dict.get('db_port', '5432')
        db_database = config_dict.get('db_database', 'test')
        db_uid = config_dict.get('db_uid', 'test')
        db_pwd = config_dict.get('db_pwd', 'test')
        self.sql_conn_str = f"DRIVER={db_driver};SERVER={db_server};PORT={db_port};DATABASE={db_database};UID={db_uid};PWD={db_pwd}"

    def get_point(self, point_name):
        """Required"""
        pass

    def _set_point(self, point_name, value):
        """Required"""
        pass

    def get_ms_data(self):
        """Pulls data from the Medtronic DB"""
        points_data = []
        sql_conn = pyodbc.connect(self.db_conn_str)
        crsr = sql_conn.cursor()
        crsr.tables(tbleType='TABLE')
        crsr.execute(
            f"""
            SELECT Points.DeviceId, Points.Id, Points.DeviceId, Points.Name,
            Trends.CurrentValue, Trends.CurrentDate
            FROM Points
            JOIN Trends ON Points.Id = Trends.PointId;
            """
        )
        data = crsr.fetchall()
        columns = [column[0] for column in crsr.description]
        for row in data:
        # Create a dict and add it to the list
            points_data.append(dict(zip(columns, row)))

        crsr.close()
        sql_conn.close()
        return points_data

    def process_ms_data(self, msql_points):
        """Processes the data from the Medtronic DB"""
        result_data = {}
        now = datetime.now(timezone.utc)
        for msql_point in msql_points:
            parsed_date = datetime.fromisoformat(msql_point["CurrentDate"])
            timediff = abs(now - parsed_date)
            if timediff <= timedelta(minutes=5):
                try:
                    clean_point_name = msql_point["Name"].lower().replace(" ", "_").replace("-", "_")
                    topic = (
                        f"{self.client}/{self.site}/{msql_point['DeviceId']}/{clean_point_name}_{msql_point['Id']}"
                    )
                    result_data[topic] = float(msql_point["CurrentValue"])
                except ValueError:
                    continue
        return result_data

    def _scrape_all(self):
        """
        Required Pass all points
        """
        msql_points = self.get_ms_data()
        return self.process_ms_data(msql_points)