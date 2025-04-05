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


import logging
import gevent
import traceback
from datetime import datetime, timedelta

from platform_driver.driver_exceptions import DriverConfigError
from platform_driver.interfaces import BaseInterface, BaseRegister
from volttron.platform.vip.agent import errors
from volttron.platform.jsonrpc import RemoteError

# Logging is completely configured by now.
_log = logging.getLogger(__name__)

DEFAULT_COV_LIFETIME = 180
COV_UPDATE_BUFFER = 3
BACNET_TYPE_MAPPING = {
    "multiStateValue": int,
    "multiStateInput": int,
    "multiStateOutput": int,
    "accumulator": int,
    "analogValue": float,
    "analogInput": float,
    "analogOutput": float,
    "loop": float,
    "binaryValue": bool,
    "binaryInput": bool,
    "binaryOutput": bool,
}


class Register(BaseRegister):
    def __init__(
        self,
        instance_number,
        object_type,
        property_name,
        read_only,
        point_name,
        units,
        description="",
        priority=None,
        list_index=None,
    ):
        super(Register, self).__init__(
            "byte", read_only, point_name, units, description=description
        )
        self.instance_number = int(instance_number)
        self.object_type = object_type
        self.property = property_name
        self.priority = priority
        self.index = list_index
        self.python_type = BACNET_TYPE_MAPPING[object_type]


class Interface(BaseInterface):
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.register_count = 10000
        self.register_count_divisor = 1
        self.cov_points = []
        self.use_read_multiple = True
        self.enable_collection = True
        self.collection_disabled_time = None
        self.failed_rpm_points = set()  # Track points that have failed with RPM
        self.last_rpm_retry = datetime.now()
        self.rpm_retry_interval = timedelta(minutes=60)  # Retry failed points hourly
        # self.unresponsive_devices = {}

    def configure(self, config_dict, registry_config_str):
        self.min_priority = config_dict.get("min_priority", 8)
        self.parse_config(registry_config_str)
        self.target_address = config_dict.get("device_address")
        self.device_id = int(config_dict.get("device_id"))
        self.cov_lifetime = config_dict.get("cov_lifetime", DEFAULT_COV_LIFETIME)
        self.proxy_address = config_dict.get("proxy_address", "platform.bacnet_proxy")
        self.max_per_request = config_dict.get("max_per_request", 24)
        self.use_read_multiple = config_dict.get("use_read_multiple", True)
        self.timeout = float(config_dict.get("timeout", 30.0))

        # Reset failed points list when configuration is updated
        self.failed_rpm_points = set()
        self.last_rpm_retry = datetime.now()

        # Configure RPM retry interval (in minutes)
        self.rpm_retry_interval = timedelta(
            minutes=config_dict.get("rpm_retry_interval_minutes", 60)
        )

        self.ping_retry_interval = timedelta(
            seconds=config_dict.get("ping_retry_interval", 5.0)
        )
        self.scheduled_ping = None

        self.ping_target()

        # list of points to establish change of value subscriptions with, generated from the registry config
        for point_name in self.cov_points:
            self.establish_cov_subscription(point_name, self.cov_lifetime, True)

    def schedule_ping(self):
        if self.scheduled_ping is None:
            now = datetime.now()
            next_try = now + self.ping_retry_interval
            self.scheduled_ping = self.core.schedule(next_try, self.ping_target)

    def ping_target(self):
        # Some devices (mostly RemoteStation addresses behind routers) will not be reachable without
        # first establishing the route to the device. Sending a directed WhoIsRequest is will
        # settle that for us when the response comes back.

        pinged = False
        try:
            self.vip.rpc.call(
                self.proxy_address, "ping_device", self.target_address, self.device_id
            ).get(timeout=self.timeout)
            pinged = True
        except errors.Unreachable:
            _log.warning("Unable to reach BACnet proxy.")

        except errors.VIPError:
            _log.warning("Error trying to ping device.")

        except gevent.timeout.Timeout:
            _log.warning(
                f"Timeout trying to ping device {self.target_address}. Scheduling to retry"
            )

        self.scheduled_ping = None

        # Schedule retry.
        if not pinged:
            self.schedule_ping()

    def get_point(self, point_name, get_priority_array=False):
        register = self.get_register_by_name(point_name)
        property_name = "priorityArray" if get_priority_array else register.property
        register_index = None if get_priority_array else register.index
        result = self.vip.rpc.call(
            self.proxy_address,
            "read_property",
            self.target_address,
            register.object_type,
            register.instance_number,
            property_name,
            register_index,
        ).get(timeout=self.timeout)
        return result

    def set_point(self, point_name, value, priority=None):
        # TODO: support writing from an array.
        register = self.get_register_by_name(point_name)
        if register.read_only:
            raise IOError(
                "Trying to write to a point configured read only: " + point_name
            )

        if priority is not None and priority < self.min_priority:
            raise IOError(
                "Trying to write with a priority lower than the minimum of "
                + str(self.min_priority)
            )

        # We've already validated the register priority against the min priority.
        args = [
            self.target_address,
            value,
            register.object_type,
            register.instance_number,
            register.property,
            priority if priority is not None else register.priority,
            register.index,
        ]
        result = self.vip.rpc.call(self.proxy_address, "write_property", *args).get(
            timeout=self.timeout
        )
        return result

    # def add_unresponsive_device(self, address):
    #     """
    #     Keep list of devices that don't respond so they aren't scanned too frequently
    #     """
    #     self.unresponsive_devices[address] = datetime.now()

    def scrape_all(self):
        # TODO: support reading from an array.
        point_map = {}
        rpm_point_map = {}
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)

        if self.enable_collection is False:
            if datetime.now() - self.collection_disabled_time < timedelta(hours=24):
                return
            else:
                self.enable_collection = True

        # Check if it's time to retry failed RPM points
        current_time = datetime.now()
        retry_failed_points = False

        if (
            current_time - self.last_rpm_retry > self.rpm_retry_interval
            and self.failed_rpm_points
        ):
            _log.info(
                f"Time to retry {len(self.failed_rpm_points)} failed RPM points for {self.target_address}"
            )
            retry_failed_points = True
            self.last_rpm_retry = current_time

        for register in read_registers + write_registers:
            # Add all points to the global point map
            point_map[register.point_name] = [
                register.object_type,
                register.instance_number,
                register.property,
                register.index,
            ]

            # Use RPM for points that:
            # 1. Haven't previously failed, OR
            # 2. Are being retried due to the retry interval
            if self.use_read_multiple and (
                retry_failed_points or register.point_name not in self.failed_rpm_points
            ):
                rpm_point_map[register.point_name] = [
                    register.object_type,
                    register.instance_number,
                    register.property,
                    register.index,
                ]

        result = {}

        # If we have points to read with RPM and RPM is enabled
        if self.use_read_multiple and rpm_point_map:
            while True:
                try:
                    rpm_result = self.vip.rpc.call(
                        self.proxy_address,
                        "read_properties",
                        self.target_address,
                        rpm_point_map,
                        self.max_per_request,
                        True,  # Always use read_multiple for rpm_point_map
                    ).get(timeout=180)

                    result.update(rpm_result)
                    _log.debug(f"Successfully read {len(rpm_result)} points using RPM")

                    # If we're retrying failed points and some succeeded, remove them from the failed list
                    if retry_failed_points:
                        successful_retries = (
                            set(rpm_result.keys()) & self.failed_rpm_points
                        )
                        if successful_retries:
                            _log.info(
                                f"Successfully retried {len(successful_retries)} previously failed RPM points"
                            )
                            self.failed_rpm_points -= successful_retries

                    break

                except gevent.timeout.Timeout as exc:
                    _log.error(f"Timed out reading target {self.target_address}")
                    raise exc

                except RemoteError as exc:
                    # Handle different types of property-related errors
                    if (
                        "unknownProperty" in exc.message
                        or "propertyError" in exc.message
                    ):
                        _log.debug(f"Property error: {exc.message}")

                        # Try to extract the object identifier from the error message
                        match_found = False

                        try:
                            if "unknownProperty" in exc.message:
                                obj_identifier = exc.message.split("unknownProperty: ")[
                                    1
                                ].strip()
                                obj_type, obj_instance = obj_identifier.strip(
                                    "()"
                                ).split(", ")
                                prop_name = (
                                    None  # Unknown for general unknownProperty errors
                                )
                                match_found = True
                            elif "propertyError" in exc.message:
                                obj_prop = exc.message.split("propertyError: ")[
                                    1
                                ].strip()
                                obj_part, prop_part = obj_prop.split(".")
                                obj_type, obj_instance = obj_part.strip("()").split(
                                    ", "
                                )
                                prop_name = (
                                    prop_part.split("[")[0]
                                    if "[" in prop_part
                                    else prop_part
                                )
                                match_found = True
                        except (IndexError, ValueError) as parse_err:
                            _log.warning(
                                f"Could not parse object info from error: {exc.message} ({parse_err})"
                            )

                        # If we successfully parsed the object info, mark the affected points
                        if match_found:
                            for point_name, props in list(rpm_point_map.items()):
                                # If prop_name is specified, only mark points with that property
                                if (
                                    props[0] == obj_type
                                    and str(props[1]) == obj_instance
                                ) and (prop_name is None or props[2] == prop_name):
                                    self.failed_rpm_points.add(point_name)
                                    _log.debug(
                                        f"Added {point_name} to failed RPM points list due to {exc.message}"
                                    )
                                    # Remove from current rpm_point_map so we don't retry it
                                    rpm_point_map.pop(point_name, None)
                        else:
                            # If we couldn't parse the error, disable RPM for this read attempt only
                            _log.warning(
                                f"Could not parse property error, skipping RPM for this read: {exc.message}"
                            )
                            break

                        # If we still have points to read with RPM, continue
                        if rpm_point_map:
                            continue
                        else:
                            _log.debug(
                                "No more valid RPM points left after handling property errors"
                            )
                            break

                    if "noResponse" in exc.message:
                        _log.warning(
                            f"device {self.target_address} did not respond reading multiple"
                        )
                        # Don't disable RPM completely, just for this read attempt
                        break

                    if "segmentationNotSupported" in exc.message:
                        if self.max_per_request <= 1:
                            _log.error(
                                "Receiving a segmentationNotSupported error with 'max_per_request' setting of 1."
                            )
                            raise
                        self.register_count_divisor += 1
                        self.max_per_request = max(
                            int(self.register_count / self.register_count_divisor), 1
                        )
                        _log.info(
                            "Device requires a lower max_per_request setting. Trying: "
                            + str(self.max_per_request)
                        )
                        continue

                    elif exc.message.endswith("rejected the request: 9"):
                        _log.info(
                            "Device rejected request with 'unrecognized-service' error, switching to individual reads"
                        )
                        # This device doesn't support RPM at all, so we'll read individually
                        self.use_read_multiple = False
                        break

                    else:
                        trace = traceback.format_exc()
                        _log.error(
                            f"Error reading target {self.target_address}: {trace}"
                        )
                        raise exc

                except errors.Unreachable:
                    # If the Proxy is not running bail.
                    _log.warning("Unable to reach BACnet proxy.")
                    self.schedule_ping()
                    raise

        # Read any points that couldn't be read using RPM
        remaining_points = {k: v for k, v in point_map.items() if k not in result}
        if remaining_points:
            try:
                # Use individual reads for remaining points
                individual_result = self.vip.rpc.call(
                    self.proxy_address,
                    "read_properties",
                    self.target_address,
                    remaining_points,
                    self.max_per_request,
                    False,  # Always use individual reads for remaining points
                ).get(timeout=180)

                result.update(individual_result)
                _log.debug(
                    f"Successfully read {len(individual_result)} points using individual reads"
                )
            except gevent.timeout.Timeout as exc:
                _log.error(
                    f"Timed out reading target {self.target_address} with individual reads"
                )
                raise exc
            except RemoteError as exc:
                if "noResponse" in exc.message:
                    # Device is unresponsive even to individual reads
                    _log.error(
                        f"Device {self.target_address} did not respond to individual reads"
                    )
                    self.enable_collection = False
                    self.collection_disabled_time = datetime.now()
                else:
                    trace = traceback.format_exc()
                    _log.error(
                        f"Error reading target {self.target_address} with individual reads: {trace}"
                    )
                    raise exc
            except errors.Unreachable:
                _log.warning("Unable to reach BACnet proxy.")
                self.schedule_ping()
                raise

        _log.debug(f"Total points read from {self.target_address}: {len(result)}")
        return result

    def revert_all(self, priority=None):
        """
        Revert entrire device to it's default state
        """
        # TODO: Add multipoint write support
        write_registers = self.get_registers_by_type("byte", False)
        for register in write_registers:
            self.revert_point(register.point_name, priority=priority)

    def revert_point(self, point_name, priority=None):
        """
        Revert point to it's default state
        """
        self.set_point(point_name, None, priority=priority)

    def parse_config(self, config_dict):
        if config_dict is None:
            return

        self.register_count = len(config_dict)

        for reg_definition in config_dict:
            # Skip lines that have no address yet.
            if not reg_definition.get("Volttron Point Name"):
                continue

            io_type = reg_definition.get("BACnet Object Type")
            read_only = reg_definition.get("Writable").lower() != "true"
            point_name = reg_definition.get("Volttron Point Name")

            # checks if the point is flagged for change of value
            is_cov = reg_definition.get("COV Flag", "false").lower() == "true"

            index = int(reg_definition.get("Index"))

            list_index = reg_definition.get("Array Index", "")
            list_index = list_index.strip()

            if not list_index:
                list_index = None
            else:
                list_index = int(list_index)

            priority = reg_definition.get("Write Priority", "")
            priority = priority.strip()
            if not priority:
                priority = None
            else:
                priority = int(priority)

                if priority < self.min_priority:
                    message = "{point} configured with a priority {priority} which is lower than than minimum {min}."
                    raise DriverConfigError(
                        message.format(
                            point=point_name, priority=priority, min=self.min_priority
                        )
                    )

            description = reg_definition.get("Notes", "")
            units = reg_definition.get("Units")
            property_name = reg_definition.get("Property")

            try:
                register = Register(
                    index,
                    io_type,
                    property_name,
                    read_only,
                    point_name,
                    units,
                    description=description,
                    priority=priority,
                    list_index=list_index,
                )

                self.insert_register(register)
            except Exception as exc:  # pylint: disable=broad-except
                _log.error(f"Error parsing register definition: {reg_definition=} {exc=}")

            if is_cov:
                self.cov_points.append(point_name)

    def establish_cov_subscription(self, point_name, lifetime, renew=False):
        """
        Asks the BACnet proxy to establish a COV subscription for the point via RPC.
        If lifetime is specified, the subscription will live for that period, else the
        subscription will last indefinitely. Default period of 3 minutes. If renew is
        True, the the core scheduler will call this method again near the expiration
        of the subscription.
        """
        register = self.get_register_by_name(point_name)
        try:
            self.vip.rpc.call(
                self.proxy_address,
                "create_cov_subscription",
                self.target_address,
                self.device_path,
                point_name,
                register.object_type,
                register.instance_number,
                lifetime=lifetime,
            )
        except errors.Unreachable:
            _log.warning(
                "Unable to establish a subscription via the bacnet proxy as it was unreachable."
            )
        # Schedule COV resubscribe
        if renew and (lifetime > COV_UPDATE_BUFFER):
            now = datetime.now()
            next_sub_update = now + timedelta(seconds=(lifetime - COV_UPDATE_BUFFER))
            self.core.schedule(
                next_sub_update,
                self.establish_cov_subscription,
                point_name,
                lifetime,
                renew,
            )
