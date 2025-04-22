"""
Collection of data structures used in the OPConnect interface.
"""

import enum

class HTTPMethods(enum.Enum, str):
    """
    Enum for HTTP methods.
    """
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
