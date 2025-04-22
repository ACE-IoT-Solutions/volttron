"""
Interface for collecting and controlling OpConnect EV chargers
"""

import logging
import traceback

import grequests


from opconnect.datastructures import HTTPMethods
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
        self.base_url = None
        self.username = None
        self.password = None
        self.auth_token = None

    def configure(self, config_dict, registry_config_str):
        """
        Configure the OpConnect interface with the provided configuration dictionary
        and register configuration string.
        """
        self.username = config_dict.get("username")
        self.password = config_dict.get("password")
        self.base_url = f"https://{self.base_url}"
        self.auth_token = self.authenticate()

    def authenticate(self):
        """
        Request auth token from API
        """
        request = grequests.post(
            f"{self.base_url}/API/Session.svc/Session/ext",
            json={"email": self.username, "password": self.password},
        )
        (result,) = grequests.map(
            (request), exception_handler=self.grequests_exception_handler
        )
        if result is None:
            _log.error("Failed to connect to OpConnect API")
            return None
        if result.status_code != 200:
            _log.error(
                f"Failed to authenticate with OpConnect API: {result.status_code}"
            )
            return None
        return result.json().get("authToken")

    def make_safe_request(self, url, method, **kwargs):
        """
        Make a safe request to the OpConnect API.
        """
        headers = {"Authorization": self.auth_token}
        headers.update(kwargs.get("headers", {}))
        if method == HTTPMethods.GET:
            request = grequests.get(url, headers=headers, **kwargs)
            (result,) = grequests.map(
                (request), exception_handler=self.grequests_exception_handler
            )
            if result is None:
                _log.error("Failed to connect to OpConnect API")
                return None
            if result.status_code == 401:
                # auth token expired, re-authenticate
                self.auth_token = self.authenticate()
                recursive = kwargs.get("recursive", False)
                # only try one recursion
                if not recursive:
                    kwargs["recursive"] = True
                    return self.make_safe_request(url, method, **kwargs)

        elif method == HTTPMethods.POST:
            request = grequests.post(url, headers=headers, **kwargs)
            (result,) = grequests.map(
                (request), exception_handler=self.grequests_exception_handler
            )
            if result is None:
                _log.error("Failed to connect to OpConnect API")
                return None
            if result.status_code == 401:
                # auth token expired, re-authenticate
                self.auth_token = self.authenticate()
                recursive = kwargs.get("recursive", False)
                # only try one recursion
                if not recursive:
                    kwargs["recursive"] = True
                    return self.make_safe_request(url, method, **kwargs)
            if result.status_code != 200:
                _log.error(
                    f"Failed to make request to OpConnect API: {result.status_code}"
                )
                return None
        else:
            raise ValueError(f"Unsupported method: {method}")
        return request.json()

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
        return grequests.get("EV")

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
