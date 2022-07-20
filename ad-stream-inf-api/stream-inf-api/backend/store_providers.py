"""
   Author: ganrad01@gmail.com
   Description: This module contains backend store provider implementations.
   Dated: 07-19-2022

   Notes:
"""

import logging

from abc import ABC, abstractmethod

from pymemcache.client.base import Client

logger = logging.getLogger(__name__)

class AbstractStoreProvider(ABC):

    @abstractmethod
    def get_value(self):
        pass

    @abstractmethod
    def set_value(self, value):
        pass

class MemcacheStoreProvider(AbstractStoreProvider):
    _context = None

    def __init__(self, context):
        logger.info(f"__init__: Initializing memcached server.\nURL={context._host_port}")

        self._context = context

    def get_value(self, key):
        logger.info(f"get_value():\nkey={key}")

    def set_value(self,key,value):
        logger.info(f"set_value():\nkey={key}\nvalue={value}")

