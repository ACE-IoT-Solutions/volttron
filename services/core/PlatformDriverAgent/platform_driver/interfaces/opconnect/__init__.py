"""
Interface for collecting and controlling OpConnect EV chargers
"""

import logging
import traceback

from json import JSONDecodeError

import grequests

from platform_driver.interfaces.opconnect.datastructures import HTTPMethods
from platform_driver.interfaces import BaseRegister, BaseInterface, BasicRevert

_log = logging.getLogger(__name__)


class Register(BaseRegister):
    """
    Register class for OpConnect
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
    Interface for the OpConnect EV chargers
    """

    def __init__(self, **kwargs):
        """
        Initialize OpConnect interface
        """
        super(Interface, self).__init__(**kwargs)
        self.base_url = None
        self.username = None
        self.password = None
        self.auth_token = None
        self.registry_config = None

    def configure(self, config_dict, registry_config_str):
        """
        Configure the OpConnect interface with the provided configuration dictionary
        and register configuration string.
        """
        self.username = config_dict.get("username")
        self.password = config_dict.get("password")
        self.base_url = config_dict.get("base_url")
        if self.username is None or self.password is None or self.base_url is None:
            _log.error(f"Missing required configuration parameters: {config_dict=}")
            return False
        self.authenticate()
        self.registry_config = registry_config_str
        for register in registry_config_str:
            name = register["name"]
            self.insert_register(Register(name, "", ""))

    def authenticate(self):
        """
        Request auth token from API
        """
        request = grequests.post(
            f"{self.base_url}/API/Session.svc/Session/ext",
            json={"email": self.username, "password": self.password},
        )
        result = grequests.map(
            [request], exception_handler=self.grequests_exception_handler
        )[0]
        if result is None:
            _log.error("Failed to connect to OpConnect API")
            return None
        if result.status_code != 200:
            _log.error(
                f"Failed to authenticate with OpConnect API: {result.status_code}"
            )
            return None
        authtoken = result.json().get("authToken")
        _log.debug(f"Authenticated with OpConnect API: {authtoken=}")
        self.auth_token = authtoken

    def make_safe_request(self, url, method, **kwargs):
        """
        Make a safe request to the OpConnect API.
        """
        headers = {"Authorization": self.auth_token}
        if kwargs.get("headers"):
            headers.update(kwargs.get("headers", {}))
            del kwargs["headers"]
        if method == HTTPMethods.GET:
            request = grequests.get(url, headers=headers, **kwargs)
            result = grequests.map(
                [request], exception_handler=self.grequests_exception_handler
            )[0]
            if result is None:
                _log.error("Failed to connect to OpConnect API")
                return None
            if result.status_code == 401:
                # auth token expired, re-authenticate
                self.authenticate()
                recursive = kwargs.get("recursive", False)
                # only try one recursion
                if not recursive:
                    kwargs["recursive"] = True
                    return self.make_safe_request(url, method, **kwargs)

        elif method == HTTPMethods.POST:
            request = grequests.post(url, headers=headers, **kwargs)
            result = grequests.map(
                [request], exception_handler=self.grequests_exception_handler
            )[0]
            if result is None:
                _log.error("Failed to connect to OpConnect API")
                return None
            if result.status_code == 401:
                _log.info(
                    f"{result.status_code}: auth token expired, re-authenticating"
                )
                self.authenticate()
                recursive = kwargs.get("recursive", False)
                # only try one recursion
                if not recursive:
                    kwargs["recursive"] = True
                    return self.make_safe_request(url, method, **kwargs)
            if result.status_code == 409:
                _log.warning(
                    "409: Demand is already set, please clear to set new demand"
                )
                return None
            if result.status_code != 200:
                _log.error(
                    f"Failed to make request to OpConnect API: {result.status_code}"
                )
                return None
        elif method == HTTPMethods.DELETE:
            request = grequests.delete(url, headers=headers, **kwargs)
            result = grequests.map(
                [request], exception_handler=self.grequests_exception_handler
            )[0]
            if result is None:
                _log.error("Failed to connect to OpConnect API")
                return None
            if result.status_code == 400:
                _log.error(f"400: Bad request, please check the parameters: {headers=}")
                return None
            if result.status_code == 401:
                _log.info(
                    f"{result.status_code}: auth token expired, re-authenticating"
                )
                self.authenticate()
                recursive = kwargs.get("recursive", False)
                # only try one recursion
                if not recursive:
                    kwargs["recursive"] = True
                    return self.make_safe_request(url, method, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")
        try:
            return result.json()
        except JSONDecodeError:
            status_code = result.status_code
            if status_code == 200:
                return True
            _log.error(f"Failed to parse JSON response: {status_code=} {result.text=}")
            return None

    def get_charging_stations(self):
        """
        Retrieve list of all charging stations
        """
        return self.make_safe_request(
            f"{self.base_url}/API/DemandResponse.svc/ChargingStation/List",
            HTTPMethods.GET,
        )

    def clear_demand_limit(self, charging_station_id):
        """
        Clear demand limit for a specific charging station
        """
        return self.make_safe_request(
            f"{self.base_url}/API/DemandResponse.svc/ChargingStation/ClearLimit",
            HTTPMethods.DELETE,
            headers={"chargeBoxID": charging_station_id, "connectorId": 1},
        )

    def scrape_all(self):
        """
        Scrape all data from the OpConnect EV chargers.
        """
        return self._scrape_all()

    def _scrape_all(self):
        """
        Internal call to override base method
        """
        results = self.make_safe_request(
            f"{self.base_url}/API/DemandResponse.svc/ChargingStation/List",
            HTTPMethods.GET,
        )
        point_data = {}
        if results is None:
            _log.error("Failed to retrieve data from OpConnect API")
            return {}
        entries = [entry["name"] for entry in self.registry_config]
        for point, value in results[0].items():
            if point in entries:
                point_data[point] = float(value)

        return point_data

    def get_point(self, point_name, **kwargs):
        """
        Get a point from the OpConnect EV chargers.
        """
        return self._get_point(point_name)

    def _get_point(self, point_name):
        """
        Internal call to override base method
        """
        results = self._scrape_all()
        try:
            return results[point_name]
        except KeyError:
            _log.error(f"Point {point_name} not found in OpConnect data")
            return None
        
    def set_point(self, point_name, value, **kwargs):
        """
        Set a point on the OpConnect EV chargers.
        Units must be in kW.
        """
        return self._set_point(point_name, value)

    def _set_point(self, point_name, value):
        """
        Internal call to override base method
        """

        if value is None:
            self.clear_demand_limit(point_name)

        data = {
            "chargeBoxID": point_name,
            "unit": "kW",
            "limit": value,
            "connectorId": 1,  # pass 1 for Enphase stations
        }
        self.make_safe_request(
            f"{self.base_url}/API/DemandResponse.svc/ChargingStation/SetLimit",
            HTTPMethods.POST,
            json=data,
        )
        _log.info(f"set opconnect point {point_name} to {value}")
        return True

    def grequests_exception_handler(self, request, exception):
        """
        Log exceptions from grequests
        """
        trace = traceback.format_exc()
        _log.error(f"grequests error: {exception} with {request}: {trace=}")
