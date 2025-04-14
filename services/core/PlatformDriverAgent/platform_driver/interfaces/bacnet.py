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

"""
BACnet Driver Interface

This module provides an interface to communicate with BACnet devices
using the BACnet/IP protocol. It handles device discovery, reading and writing
properties, and supports Change of Value (COV) subscriptions for efficient
data collection.
"""

import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict

import gevent
from platform_driver.driver_exceptions import DriverConfigError
from platform_driver.interfaces import BaseInterface, BaseRegister

from volttron.platform.jsonrpc import RemoteError
from volttron.platform.vip.agent import errors

# Logging is completely configured by now.
_log = logging.getLogger(__name__)

# Default lifetime for COV subscriptions in seconds
DEFAULT_COV_LIFETIME = 180
# Buffer time to renew COV subscriptions before they expire
COV_UPDATE_BUFFER = 3
# Mapping of BACnet object types to Python types for proper value conversion
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
    # "schedule": bool,
}


class Register(BaseRegister):
    """
    BACnet Register Class

    Represents a single BACnet point or property to be read from or written to.
    Extends the BaseRegister class to include BACnet-specific attributes.
    """

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
        """
        Initialize a BACnet register.

        Args:
            instance_number: BACnet object instance number
            object_type: BACnet object type (e.g., "analogValue", "binaryOutput")
            property_name: BACnet property to read/write (usually "presentValue")
            read_only: Boolean indicating if point is read-only
            point_name: Volttron point name
            units: Engineering units of the point
            description: Optional description of the point
            priority: BACnet priority for writing (1-16, None for read-only points)
            list_index: Index for accessing array properties, None for non-array properties
        """
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
    """
    BACnet Interface Implementation

    This class provides the interface for communicating with BACnet devices
    through a BACnet proxy agent. It handles device configuration, point discovery,
    reading/writing values, and optimizing communication with devices.
    """

    def __init__(self, **kwargs):
        """
        Initialize the BACnet interface.

        Args:
            **kwargs: Keyword arguments passed to the base interface
        """
        super(Interface, self).__init__(**kwargs)
        # Initial maximum register count for batch operations
        self.register_count = 10000
        # Used to reduce register count when segmentation issues occur
        self.register_count_divisor = 1
        # List of points configured for COV (Change of Value) subscriptions
        self.cov_points = []
        # Flag to enable/disable batch reads when possible
        self.use_read_multiple = True
        # Flag to enable/disable data collection (disabled when device is unreachable)
        self.enable_collection = True
        # Timestamp when collection was disabled
        self.collection_disabled_time = None
        # Dictionary to track points that have failed and when they failed
        self.failing_points: Dict[str, datetime] = {}
        # Time period to wait before retrying failed points
        self.fail_retry = timedelta(hours=1)
        # Dictionary to track unresponsive devices (commented out)
        # self.unresponsive_devices = {}

    def configure(self, config_dict, registry_config_str):
        """
        Configure the BACnet interface with settings from the driver configuration.

        Args:
            config_dict: A dictionary of driver configuration settings
            registry_config_str: A list of register definitions (points to be read/written)
        """
        # Minimum BACnet priority allowed for writing (1-16, with 1 being highest priority)
        self.min_priority = config_dict.get("min_priority", 8)
        # Parse the registry configuration to create register objects
        self.parse_config(registry_config_str)
        # BACnet device address (IP:Port for BACnet/IP)
        self.target_address = config_dict.get("device_address")
        # BACnet device instance ID
        self.device_id = int(config_dict.get("device_id"))
        # Lifetime for COV subscriptions in seconds
        self.cov_lifetime = config_dict.get("cov_lifetime", DEFAULT_COV_LIFETIME)
        # VIP address of the BACnet proxy agent
        self.proxy_address = config_dict.get("proxy_address", "platform.bacnet_proxy")
        # Maximum number of points to read in a single request
        self.max_per_request = config_dict.get("max_per_request", 24)
        # Whether to use ReadPropertyMultiple service when possible
        self.use_read_multiple = config_dict.get("use_read_multiple", True)
        # Timeout for BACnet requests in seconds
        self.timeout = float(config_dict.get("timeout", 30.0))
        # Whether to attempt single-point reads if batch reads fail
        self.failover_bacnet_to_single = bool(
            config_dict.get("failover_bacnet_to_single", True)
        )

        # How often to retry pinging an unresponsive device
        self.ping_retry_interval = timedelta(
            seconds=config_dict.get("ping_retry_interval", 900)
        )
        self.scheduled_ping = None

        # Initial ping to verify device is reachable
        self.ping_target()

        # Establish COV subscriptions for all points marked for COV in the registry
        for point_name in self.cov_points:
            self.establish_cov_subscription(point_name, self.cov_lifetime, True)

    def schedule_ping(self):
        """
        Schedules a ping attempt to the BACnet device after the retry interval.
        Ensures we don't schedule multiple pings simultaneously.
        """
        if self.scheduled_ping is None:
            now = datetime.now()
            next_try = now + self.ping_retry_interval
            self.scheduled_ping = self.core.schedule(next_try, self.ping_target)

    def ping_target(self):
        """
        Sends a directed WhoIsRequest to the BACnet device to verify connectivity.

        For devices behind routers (especially RemoteStation addresses), this establishes
        the network route to the device. If successful, enables data collection.
        If unsuccessful, schedules a retry based on ping_retry_interval.
        """
        # Some devices (mostly RemoteStation addresses behind routers) will not be reachable without
        # first establishing the route to the device. Sending a directed WhoIsRequest is will
        # settle that for us when the response comes back.

        pinged = False
        try:
            # Call the ping_device method on the BACnet proxy agent
            self.vip.rpc.call(
                self.proxy_address, "ping_device", self.target_address, self.device_id
            ).get(timeout=self.timeout)
            pinged = True
            # Device responded, enable data collection
            self.enable_collection = True
        except errors.Unreachable:
            _log.warning("Unable to reach BACnet proxy.")

        except errors.VIPError:
            _log.warning("Error trying to ping device.")

        except gevent.timeout.Timeout:
            _log.warning(
                f"Timeout trying to ping device {self.target_address}. Scheduling to retry"
            )

        # Clear the scheduled ping flag
        self.scheduled_ping = None

        # Schedule retry if ping was unsuccessful
        if not pinged:
            self.schedule_ping()

    def get_point(self, point_name, get_priority_array=False):
        """
        Concrete implementation of get_point for BACnet interface.

        Args:
            point_name: Name of the point/register to read
            get_priority_array: If True, reads the priorityArray property instead of the
                               register's configured property (usually presentValue)

        Returns:
            The value of the requested point/property as the appropriate Python type
        """
        # Get the register object for this point
        register = self.get_register_by_name(point_name)
        # Determine which property to read - either priorityArray or the configured property
        property_name = "priorityArray" if get_priority_array else register.property
        # For priorityArray, we don't use an index value
        register_index = None if get_priority_array else register.index
        # Use the BACnet proxy to read the property
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
        """
        Concrete implementation of set_point for BACnet interface.

        Args:
            point_name: Name of the point to write to
            value: Value to write to the point
            priority: BACnet priority to use (1-16, with 1 being highest priority)
                      If None, uses the register's configured priority

        Returns:
            Result from the BACnet write operation

        Raises:
            IOError: If trying to write to a read-only point or using a priority
                    lower than the configured minimum priority
        """
        # TODO: support writing from an array.
        # Get the register object for this point
        register = self.get_register_by_name(point_name)
        # Check if point is configured as read-only
        if register.read_only:
            raise IOError(
                "Trying to write to a point configured read only: " + point_name
            )

        # Validate the requested priority against minimum allowed
        if priority is not None and priority < self.min_priority:
            raise IOError(
                "Trying to write with a priority lower than the minimum of "
                + str(self.min_priority)
            )

        # We've already validated the register priority against the min priority.
        # Prepare arguments for the BACnet write_property call
        args = [
            self.target_address,
            value,
            register.object_type,
            register.instance_number,
            register.property,
            priority if priority is not None else register.priority,
            register.index,
        ]
        # Use the BACnet proxy to write the property
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
        """
        Reads values for all configured points from the BACnet device.

        This method implements an efficient batch-reading strategy with various
        fallback mechanisms to handle device limitations:
        1. Tries to read points in batches using ReadPropertyMultiple when possible
        2. Falls back to single-point reads if batch reads fail
        3. Skips points that have recently failed until their retry period expires
        4. Handles various BACnet communication errors with appropriate strategies

        Returns:
            Dictionary mapping point names to their current values
        """
        # TODO: support reading from an array.
        now = datetime.now()
        point_map = {}
        point_names = []
        # Get all registered points (both read-only and writable)
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)

        # Check if collection is disabled (due to previous communication failures)
        if self.enable_collection is False:
            # If disabled for less than 24 hours, skip collection attempt
            if datetime.now() - self.collection_disabled_time < timedelta(hours=24):
                return
            else:
                # After 24 hours, try again
                self.enable_collection = True

        # Build list of points to read, skipping recently failed points
        for register in read_registers + write_registers:
            if register.point_name in self.failing_points:
                if self.failing_points[register.point_name] > (now - self.fail_retry):
                    _log.debug(f"Skipping {register.point_name} due to recent failure.")
                    continue
                else:
                    _log.debug(
                        f"Retrying {register.point_name} after failure period expired."
                    )
                    del self.failing_points[register.point_name]
            point_names.append(register.point_name)
            point_map[register.point_name] = [
                register.object_type,
                register.instance_number,
                register.property,
                register.index,
            ]

        # If no points to read, disable collection and schedule ping
        if len(point_map) == 0:
            self.enable_collection = False
            self.schedule_ping()

        # Storage for batch read results
        results = []
        # Process points in batches based on max_per_request setting
        if self.use_read_multiple:
            timeout = min( self.timeout, max(30, self.max_per_request), 180)  # cap timeout to 3 minutes for each batch
        else:
            timeout = self.timeout
        for i in range(0, len(point_names), self.max_per_request):
            # Start with configured read_multiple setting, may change based on device capability
            use_read_multiple = self.use_read_multiple
            # Generate a batch of reads equal to the max_per_request
            batch = {
                key: point_map[key] for key in point_names[i : i + self.max_per_request]
            }
            while True:
                try:
                    # Attempt to read properties through the BACnet proxy
                    batch_result = self.vip.rpc.call(
                        self.proxy_address,
                        "read_properties",
                        self.target_address,
                        batch,
                        self.max_per_request,
                        use_read_multiple,
                    ).get(timeout=timeout)
                    # _log.debug(f"found {len(batch_result)} results in platform driver")
                    results.append(batch_result)
                except gevent.timeout.Timeout as exc:
                    # Handle timeouts during reading
                    _log.error(
                        f"Timed out reading target {self.target_address} with batch {batch}: {exc}"
                    )
                    if not use_read_multiple:
                        # If already using single reads, give up on this batch
                        break
                    # Otherwise propagate the error
                    raise exc
                except RemoteError as exc:
                    # Handle unknown property errors
                    if "unknownProperty" in exc.message:
                        _log.debug(f"unknownProperty error: {exc.message}")
                        # self.vip.config.set("unknown_properties", exc.message)
                    # Handle no response from device
                    if (
                        "noResponse" in exc.message
                        and self.use_read_multiple
                        and self.failover_bacnet_to_single is True
                    ):
                        _log.warning(
                            f"device {self.target_address} did not respond reading multiple"
                        )
                        # Fallback to single property reads
                        use_read_multiple = False
                        continue
                    elif "noResponse" in exc.message and not self.use_read_multiple:
                        # If still no response with single reads, disable collection
                        # and schedule ping to reenable collection when device responds after interval
                        self.enable_collection = False
                        self.collection_disabled_time = datetime.now()
                        self.schedule_ping()
                        break
                    # Handle segmentation not supported error
                    if "segmentationNotSupported" in exc.message:
                        if self.max_per_request <= 1:
                            _log.error(
                                "Receiving a segmentationNotSupported error with 'max_per_request' setting of 1."
                            )
                            raise
                        # Reduce number of points per request and try again
                        self.register_count_divisor += 1
                        self.max_per_request = max(
                            int(self.register_count / self.register_count_divisor), 1
                        )
                        _log.info(
                            "Device requires a lower max_per_request setting. Trying: "
                            + str(self.max_per_request)
                        )
                        continue
                    # Handle unrecognized service error (device doesn't support ReadPropertyMultiple)
                    elif (
                        exc.message.endswith("rejected the request: 9")
                        and self.use_read_multiple
                    ):
                        _log.info(
                            "Device rejected request with 'unrecognized-service' error, attempting to access with use_read_multiple false"
                        )
                        self.use_read_multiple = False
                        continue
                    else:
                        # Log and re-raise other errors
                        trace = traceback.format_exc()
                        _log.error(
                            f"Error reading target {self.target_address}: {trace}"
                        )
                        raise exc
                except errors.Unreachable:
                    # If the Proxy is not running bail
                    _log.warning("Unable to reach BACnet proxy.")
                    self.schedule_ping()
                    raise
                else:
                    # Successfully read this batch, break the retry loop
                    break
        # Combine all batch results into a single dictionary
        result = {k: v for d in results for k, v in d.items()}
        return result

    def revert_all(self, priority=None):
        """
        Revert entire device to its default state by releasing all writable points.

        Args:
            priority: BACnet priority to use for the revert operation.
                      If None, uses each register's configured priority.
        """
        # TODO: Add multipoint write support for more efficient reversion
        # Get all writable registers
        write_registers = self.get_registers_by_type("byte", False)
        # Revert each point individually
        for register in write_registers:
            self.revert_point(register.point_name, priority=priority)

    def revert_point(self, point_name, priority=None):
        """
        Revert a specific point to its default state by writing NULL to its priority array slot.

        Args:
            point_name: Name of the point to revert
            priority: BACnet priority to use for the revert operation.
                      If None, uses the register's configured priority.
        """
        # Writing None (NULL) to a priority slot releases control at that priority
        self.set_point(point_name, None, priority=priority)

    def parse_config(self, configDict):
        """
        Parse the registry configuration for BACnet points.

        Processes each row in the registry configuration to create Register objects
        for each BACnet point, and identifies points that should use COV subscriptions.

        Args:
            configDict: List of dictionaries, each representing a BACnet point configuration

        Raises:
            DriverConfigError: If a point is configured with a priority lower than the minimum allowed
        """
        if configDict is None:
            return

        # Store total register count for calculating batch read sizes
        self.register_count = len(configDict)

        for regDef in configDict:
            # Skip lines that have no point name defined
            if not regDef.get("Volttron Point Name"):
                continue

            # Extract point configuration from registry definition
            io_type = regDef.get("BACnet Object Type")
            read_only = regDef.get("Writable").lower() != "true"
            point_name = regDef.get("Volttron Point Name")

            # Check if the point is flagged for change of value subscriptions
            is_cov = regDef.get("COV Flag", "false").lower() == "true"

            # BACnet object instance number
            index = int(regDef.get("Index"))

            # Process array index if specified (for array properties)
            list_index = regDef.get("Array Index", "")
            list_index = list_index.strip()

            if not list_index:
                list_index = None
            else:
                list_index = int(list_index)

            # Process write priority if specified (for writable points)
            priority = regDef.get("Write Priority", "")
            priority = priority.strip()
            if not priority:
                priority = None
            else:
                priority = int(priority)

                # Validate write priority against minimum allowed
                if priority < self.min_priority:
                    message = "{point} configured with a priority {priority} which is lower than than minimum {min}."
                    raise DriverConfigError(
                        message.format(
                            point=point_name, priority=priority, min=self.min_priority
                        )
                    )

            # Extract additional metadata
            description = regDef.get("Notes", "")
            units = regDef.get("Units")
            property_name = regDef.get("Property")

            try:
                # Create register object for this point
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

                # Add register to the interface's register map
                self.insert_register(register)
            except Exception as exc:  # pylint: disable=broad-except
                _log.error(f"Error parsing register definition: {regDef=} {exc=}")

            # If point is flagged for COV, add to the COV subscription list
            if is_cov:
                self.cov_points.append(point_name)

    def establish_cov_subscription(self, point_name, lifetime, renew=False):
        """
        Establishes a COV (Change of Value) subscription for a BACnet point.

        COV subscriptions allow the BACnet device to push updates to VOLTTRON when
        values change, rather than requiring constant polling. This can significantly
        reduce network traffic and improve responsiveness to value changes.

        Args:
            point_name: Name of the point to establish COV subscription for
            lifetime: Duration (in seconds) that the subscription should remain active
                      If None, subscription lasts indefinitely
            renew: If True, automatically reschedule subscription renewal before expiration

        Note:
            The BACnet proxy agent must support COV subscriptions for this to work.
            Not all BACnet devices support COV subscriptions for all point types.
        """
        # Get the register object for this point
        register = self.get_register_by_name(point_name)
        try:
            # Request COV subscription through the BACnet proxy
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
        # Schedule COV resubscribe before the subscription expires
        if renew and (lifetime > COV_UPDATE_BUFFER):
            now = datetime.now()
            # Schedule renewal a few seconds before expiration
            next_sub_update = now + timedelta(seconds=(lifetime - COV_UPDATE_BUFFER))
            self.core.schedule(
                next_sub_update,
                self.establish_cov_subscription,
                point_name,
                lifetime,
                renew,
            )
