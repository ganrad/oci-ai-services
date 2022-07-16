"""
   Author: ganrad01@gmail.com
   Description: Store provider factory  module. Defines the factory class used to generate store provider implementations.
   Dated: 07-12-2022

   Notes:
"""

import logging

from pymemcache.client.base import Client
from ..constants import *

logger = logging.getLogger(__name__)

class StoreProviderFactory:
    _instance = None
    _context = None

    def __new__(cls, context):
        if cls._instance is None:
            logger.info("init: Initializing Store Provider Factory")

            cls._instance = super(StoreProviderFactory, cls).__new__(cls)
            cls._context = context

            logger.info(f"init: Backend store provider=[{cls._context._store_type}]")
            if cls._context._store_type == STORE_PROVIDER_MEMCACHED:
                pass
                #backend_client = Client(cls._context._host_port)

        return (cls._instance)
