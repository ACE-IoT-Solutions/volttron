"""
Collection of data structures used in the OPConnect interface.
"""

from enum import Enum
class HTTPMethods(str, Enum):
    """
    Enum for HTTP methods.
    """
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
