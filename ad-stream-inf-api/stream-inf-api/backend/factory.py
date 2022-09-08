"""
   Author: ganrad01@gmail.com
   Description: Store provider factory  module. Defines the factory class used to generate store provider implementations.
   Dated: 07-12-2022

   Notes:
"""

import logging

from pymemcache.client.base import Client
from .store_providers import *
from ..constants import *

logger = logging.getLogger(__name__)

class StoreProviderFactory:
    _instance = None
    _backend = None

    def __new__(cls, context):
        if cls._instance is None:
            logger.info("init: Initializing Store Provider Factory")

            cls._instance = super(StoreProviderFactory, cls).__new__(cls)

            logger.info(f"init: Backend store provider=[{context._store_type}]")
            if context._store_type == STORE_PROVIDER_MEMCACHED:
                cls._backend = MemcacheStoreProvider(context)

        return (cls._instance)

    def getBackendInstance(self):
        logger.debug(f"getBackendInstance:")

        return(self._backend)
