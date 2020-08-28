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
import re
import sys
import time

from volttron.platform.vip.agent import *
from volttron.platform.agent import utils
from volttron.platform.messaging.utils import normtopic
from volttron.platform.messaging import headers as headers_mod
from volttron.platform.messaging.health import (STATUS_BAD,
                                                STATUS_GOOD, Status)


import gevent

import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTv311, MQTTv31
from paho.mqtt.subscribe import callback

from collections import defaultdict

utils.setup_logging()
_log = logging.getLogger(__name__)
__version__ = '0.0.1'


__authors__ = [
               'Andrew Rodgers <andrew@aceiotsolutions.com>',
               ]
__copyright__ = 'Copyright (c) 2020, ACE IoT Solutions LLC'
__license__ = 'Apache 2.0'


def mqtt_source_agent(config_path, **kwargs):
    '''Emulate device driver to publish data and Actuatoragent for testing.

    The first column in the data file must be the timestamp and it is not
    published to the bus unless the config option:
    'use_timestamp' - True will use timestamp in input file.
    timestamps. False will use the current now time and publish using it.
    '''

    conf = utils.load_config(config_path)
    _log.debug(str(conf))
    use_timestamp = conf.get('use_timestamp', True)
    remember_playback = conf.get('remember_playback', False)
    reset_playback = conf.get('reset_playback', False)

    publish_interval = float(conf.get('publish_interval', 5))

    base_path = conf.get('basepath', "")

    input_data = conf.get('input_data', [])

    # unittype_map maps the point name to the proper units.
    unittype_map = conf.get('unittype_map', {})
    
    # should we keep playing the file over and over again.
    replay_data = conf.get('replay_data', False)

    max_data_frequency = conf.get("max_data_frequency")

    return MQTTSource(config_path, **kwargs)


class MQTTSource(Agent):
    '''
    Provides a path for MQTT data to be ingested into a VOLTTRON Platform and 
    published to the bus
    '''
    def __init__(self, config_path, **kwargs):
        config = utils.load_config(config_path)
        super(MQTTSource, self).__init__(**kwargs)


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
        self.mqtt_subscription = config.get('mqtt_subscription', '#')
        if type(self.mqtt_subscription) == str:
            self.mqtt_subscription = (self.mqtt_subscription,)

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
        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure, actions=["NEW"], pattern="config")
        self.vip.config.subscribe(self.config_error, actions=["UPDATE"], pattern="config")


    def config_error(self, config_name, action, contents):
        _log.error("Currently the data publisher must be restarted for changes to take effect.")

    def configure(self, config_name, action, contents):
        config = self.default_config.copy()
        config.update(contents)
        self.mqttc = mqtt.Client(client_id=self.mqtt_client_id, protocol=self.mqtt_protocol)

        def on_message_function(client, userdata, message):
            self.on_message(client, userdata, message)
        
        def on_connect_function(client, userdata, flags, return_code):
            self.on_connect(client, userdata, flags, return_code)
        
        def on_log_function(client, userdata, level, buf):
            self.on_log(client, userdata, level, buf)
        
        self.broker_connected = False

        self.mqttc.on_message = self.on_message
        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_log = self.on_log
        if self.mqtt_auth:
            self.mqttc.username_pw_set(self.mqtt_auth['user'], password=self.mqtt_auth['password'])
        try:
            self.mqttc.connect(self.mqtt_hostname, self.mqtt_port, self.mqtt_keepalive)
        except:
            self.reconnect()
        _log.debug("entering loop")
        self.start_loop()
        _log.info('Config Data: {}'.format(config))
    
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
        _log.debug("Connection Accepted, subscribing")
        self.broker_connected = True
        for topic_string in self.mqtt_subscription:
            client.subscribe(topic_string)

    def on_message(self, client, userdata, message):
        now = utils.format_timestamp(datetime.datetime.now())

        headers = {headers_mod.DATE: now, headers_mod.TIMESTAMP: now}
        topic, point = message.topic.rsplit("/", 1)
        all_topic = "devices/" + topic + "/all"
        _log.debug(all_topic)
        _log.debug(point)

        zmq_message = [{point: float(message.payload)}]

        self.vip.pubsub.publish(peer='pubsub',
                                topic=all_topic,
                                message=zmq_message,  # [data, {'source': 'publisher3'}],
                                headers=headers)

        _log.debug("topic: {} Payload: {}".format(message.topic, str(message.payload)))


def main(argv=sys.argv):
    '''Main method called by the eggsecutable.'''
    utils.vip_main(mqtt_source_agent, version=__version__)

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
