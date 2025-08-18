"""
Interface for collecting timeseries data from haystack API
"""

import logging
import json

import grequests
import pyhaystack

from gevent import with_timeout, Timeout
from platform_driver.interfaces import BaseRegister, BaseInterface, BasicRevert
from pyhaystack.util.state import NotReadyError
from volttron.platform.agent import utils

_log = logging.getLogger("haystack_api")
utils.setup_logging()

OP_TIMEOUT = 180


class Register(BaseRegister):
    """
    Register class for Haystack API
    """

    def __init__(self, name, units, description):
        super(Register, self).__init__(
            register_type="byte",
            read_only=True,
            pointName=name,
            units=units,
            description=description,
        )


class Interface(BasicRevert, BaseInterface):
    """
    Interface for the Haystack API
    """

    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.device_path = kwargs.get("device_path")
        self.server_address = None
        self.config = None
        self.registry_config = None
        self.registers = {}
        self.session = None
        self.point_entities = None
        self.build_register_map()

    def configure(self, config_dict, registry_config_str):
        """
        Configure the Haystack API interface with the provided configuration dictionary
        and register configuration string.
        """
        self.config = config_dict
        self.session = pyhaystack.connect(**self.config)

        _log.debug(f"{registry_config_str=}")
        self.registry_config = registry_config_str
        for register in registry_config_str:
            name = register["name"]
            units = register["units"]
            _log.debug(f"inserting {register=}")
            self.insert_register(Register(name, units, ""))

        _log.info("retrieving all point entities on configure")
        self.point_entities = self.find_all_points()

    def parse_register_config(self, registry_config_str):
        """
        Parse the registry configuration string into a list of Register objects
        """
        # Assuming the registry_config_str is a JSON string
        try:
            config = json.loads(registry_config_str)
            return [Register(**item) for item in config]
        except json.JSONDecodeError as exc:
            _log.error(f"Failed to parse registry config: {exc}")
            return []

    def find_all_points(self):
        """
        Find all points in the server
        """
        points = {}
        haystack_points = self.find_entity("point and curVal").values()
        _log.debug(f"{haystack_points=}")
        for point in haystack_points:
            _log.debug(f"{point=}")
            points[point.id.name] = point
        _log.debug(f"Found initial points on configure: {points}")
        return points

    def find_entity(self, search_str):
        """
        Safely call session's find_entity with authentication
        """
        try:
            _log.debug(f"Finding entity with search string: {search_str}")
            op = self.session.find_entity(filter_expr=search_str)
            with_timeout(OP_TIMEOUT, op.wait)
            entity = op.result
            _log.debug(f"Entity found: {entity}")
        except NotReadyError as exc:
            _log.error(f"Failed to find entity: {exc}")
            return None

        return entity

    def get_entity(self, entity):
        """
        Safely call session's get_entity with authentication
        """
        try:
            _log.debug(f"trying to get {entity=}")
            op = self.session.get_entity(entity)
            with_timeout(180, op.wait)
            entity = op.result
        except (Timeout, NotReadyError, AttributeError) as exc:
            _log.error(f"Failed to get entity {entity}: {exc}")
            return None

        _log.debug(f"Entity retrieved: {entity}")
        return entity

    def get_point(self, point_name, **kwargs):
        """
        Get individual point
        """

        return self.scrape(point_name)

    def scrape_all(self):
        """
        Retrieve current value for all points in registry config
        """
        scrape_results = self._scrape_all()
        _log.debug(f"scrape_all results: {scrape_results}")
        return scrape_results

    def _scrape_all(self):
        """
        Override function from base class
        """
        results = {}
        for point in [entry["name"] for entry in self.registry_config]:
            try:
                results.update(self.scrape(point))
            except (AttributeError, ValueError) as exc:
                _log.warning(f"could not scrape {point=}: {exc=}")
                continue
        return results

    def _set_point(self, point_name, value):
        _log.warning(
            f"_set_point is not implemented for Haystack API. {[point_name, value]}"
        )
        return None

    def scrape(self, point):
        """
        Retrieve data for a given point
        """
        point_ref = self.point_entities[point]
        _log.debug(f"trying to scrape {point_ref=}")
        _log.debug(f"point ref has id: {point_ref.id=}")
        point_grid = self.get_entity(point_ref.id)
        if (
            isinstance(point_grid.tags["curVal"], bool)
            or isinstance(point_grid.tags["curVal"], float)
            or isinstance(point_grid.tags["curVal"], int)
            or isinstance(point_grid.tags["curVal"], str)
        ):
            return {point: float(point_grid.tags["curVal"])}
        value = point_grid.tags["curVal"].value
        return {
            point: value,
        }
