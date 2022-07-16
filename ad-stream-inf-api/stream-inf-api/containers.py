"""
   Author: ganrad01@gmail.com
   Description: Containers module. Defines the dependencies to be injected into service at run-time.
   Dated: 07-06-2022

   Notes:
"""

import logging

from dependency_injector import containers, providers
from .backend.stream_context import StreamContext
from . import services

logger = logging.getLogger(__name__)

class Container(containers.DeclarativeContainer):

    wiring_config = containers.WiringConfiguration(modules=[".handlers"])
    config = providers.Configuration(yaml_files=["config.yaml"])   

    # Create a stream context
    stream_context = providers.Factory(
        StreamContext,
        store_type=config.store.provider_id,
        host_port=config.memcached.host_port)
        
    # Create AD Service 
    ad_service = providers.Factory(
        services.AdService,
        conf_file=config.oci.credential_store,
        api_endpoint=config.oci.service_endpoint,
        compartment_id=config.oci.compartment_id,
        stream_context=stream_context)

    logger.info("Container: Created context and service object")

