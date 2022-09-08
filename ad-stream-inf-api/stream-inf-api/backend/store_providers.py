"""
   Author: ganrad01@gmail.com
   Description: This module contains backend store provider implementations.
   Dated: 07-19-2022

   Notes:
"""

import logging

from abc import ABC, abstractmethod

from pymemcache.client.base import Client
from pymemcache.client.retrying import RetryingClient
from pymemcache.exceptions import MemcacheUnexpectedCloseError

logger = logging.getLogger(__name__)

class AbstractStoreProvider(ABC):

    @abstractmethod
    def get_value(self, key):
        pass

    @abstractmethod
    def set_value(self, key, value):
        pass

    @abstractmethod
    def del_value(self, key):
        pass

class MemcacheStoreProvider(AbstractStoreProvider):
    _context = None
    _memcache_client = None

    def __init__(self, context):
        logger.info(f"__init__: Establishing connection with memcached server.\n----\nURL = {context._host_port}\n----")

        self._context = context

        # Instantiate memecached client
        base_client = Client(
            self._context._host_port,
            connect_timeout=10, # Wait 10 seconds. Time to wait for memcached server connection
            timeout=10, # Wait 10 seconds.  Do not wait indefinitely on the underlying socket to timeout!
            no_delay=True
        )

        # Configure built-in retrying mechanism for close error (cache server reboots)
        self._memcache_client = RetryingClient(
            base_client,
            attempts=3, # try 3 times
            retry_delay=0.01, # wait 10ms between each attempt
            retry_for=[MemcacheUnexpectedCloseError]
        )

    def get_value(self, key):
        # Retrieve value or key from cache server
        value = self._memcache_client.get(key)
        logger.info(f"get_value():\n----\nKey = {key}\nValue = {value}\n----")

        return value

    def set_value(self, key, value):
        # Set value in cache server
        self._memcache_client.set(key,value)
        logger.info(f"set_value():\n----\nKey = {key}\nValue = {value}\n----")

    def del_value(self, key):
        # Delete/Invalidate cached entry (can result in a cache miss ~ entry expired and evicted!)
        key_deleted = self._memcache_client.delete(key,False)
        logger.info(f"del_value():\n----\nKey = {key}\nDeleted = {key_deleted}\n----")
