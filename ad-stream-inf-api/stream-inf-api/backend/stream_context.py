"""
   Author: ganrad01@gmail.com
   Description: Stream Context module.  Encapsulates streaming API configuration.
   Dated: 07-12-2022

   Notes:
"""

class StreamContext:
    _store_type = None
    _host_port = None

    def __init__(self, store_type, host_port):
        self._store_type = store_type
        self._host_port = host_port
