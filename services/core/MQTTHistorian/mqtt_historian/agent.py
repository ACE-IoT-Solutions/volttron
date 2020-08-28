# -*- coding: utf-8 -*- {{{
# vim: set fenc=utf-8 ft=python sw=4 ts=4 sts=4 et:
#
# Copyright 2020, ACE IoT Solutions
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

import datetime
import logging
import sys
import time
import gevent

from volttron.platform.agent.base_historian import BaseHistorian, add_timing_data_to_header
from volttron.platform.agent import utils
from volttron.platform.messaging.health import (STATUS_BAD,
                                                STATUS_GOOD, Status)

from paho.mqtt.client import MQTTv311, MQTTv31
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish


utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '0.2'


class MQTTHistorian(BaseHistorian):
    """This historian publishes data to MQTT.
    """

    def __init__(self, config_path, **kwargs):
        config = utils.load_config(config_path)
        self.config = config


        # We pass every optional parameter to the MQTT library functions so they
        # default to the same values that paho uses as defaults.
        self.mqtt_qos = config.get('mqtt_qos', 0)
        self.mqtt_retain = config.get('mqtt_retain', False)

        self.mqtt_hostname = config.get('mqtt_hostname', 'localhost')
        self.mqtt_port = config.get('mqtt_port', 1883)
        self.mqtt_client_id = config.get('mqtt_client_id', '')
        self.mqtt_keepalive = config.get('mqtt_keepalive', 60)
        self.mqtt_will = config.get('mqtt_will', None)
        self.mqtt_auth = config.get('mqtt_auth', None)
        self.mqtt_tls = config.get('mqtt_tls', None)

        protocol = config.get('mqtt_protocol', MQTTv311)
        if protocol == "MQTTv311":
            protocol = MQTTv311
        elif protocol == "MQTTv31":
            protocol = MQTTv31

        if protocol not in (MQTTv311, MQTTv31):
            raise ValueError("Unknown MQTT protocol: {}".format(protocol))

        self.mqtt_protocol = protocol
        self.default_config = {}

        # will be available in both threads.
        self._last_error = 0

        super(MQTTHistorian, self).__init__(**kwargs)
    
    def configure(self, contents):
        config = self.default_config.copy()
        config.update(contents)
        self.mqttc = mqtt.Client(client_id=self.mqtt_client_id, protocol=self.mqtt_protocol)
        self.broker_connected = False

        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_log = self.on_log
        if self.mqtt_auth:
            self.mqttc.username_pw_set(self.mqtt_auth['user'], password=self.mqtt_auth['password'])
        try:
            self.mqttc.connect(self.mqtt_hostname, self.mqtt_port, self.mqtt_keepalive)
        except:
            self.reconnect()
        gevent.spawn(self.start_loop)
    
    def start_loop(self):
        self.vip.health.set_status(
            STATUS_GOOD, "Connection successful, entering read loop")
        while True:
            result = self.mqttc.loop(timeout=1)
            if result == 7:
                self.reconnect()
            gevent.sleep(0.1)

    def on_log(self, client, userdata, level, buf):
        _log.debug(buf)

    def timestamp(self):
        return time.mktime(datetime.datetime.now().timetuple())

    def reconnect(self):
        while True:
            try:
                self.mqttc.reconnect()
                _log.info("Reconnected")
                break
            except:
                _log.info("Reconnection failed")
                gevent.sleep(10)

    
    def on_disconnect(self, client, userdata, rc):
        self.broker_connected = False
        _log.info("Disconnected, code {}".format(rc))
        self.reconnect()

    def on_connect(self, client, userdata, flags, return_code):
        _log.debug(return_code)
        if return_code != mqtt.CONNACK_ACCEPTED:
            self.vip.health.set_status(
                STATUS_BAD, "Connection Failed")
            raise Exception(return_code)
        _log.debug("Connection Accepted")
        self.broker_connected = True

    def publish_to_historian(self, to_publish_list):
        _log.debug("publish_to_historian number of items: {}"
                   .format(len(to_publish_list)))
        current_time = self.timestamp()

        if self._last_error:
            # if we failed we need to wait 60 seconds before we go on.
            if self.timestamp() < self._last_error + 60:
                _log.debug('Not allowing send < 60 seconds from failure')
                return

        try:
            for x in to_publish_list:
                topic = x['topic']

                # Construct payload from data in the publish item.
                # Available fields: 'value', 'headers', and 'meta'
                payload = x['value']

                try:
                    self.mqttc.publish(topic, payload=payload, qos=self.mqtt_qos, retain=self.mqtt_retain)
                except Exception as e:
                    _log.warning("Exception ({}) raised by publish: {}".format(
                        e.__class__.__name__,
                        e))
                    self._last_error = self.timestamp()
        except Exception as e:
            raise e
        else:
            self.report_all_handled()


def main(argv=sys.argv):
    utils.vip_main(MQTTHistorian)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
