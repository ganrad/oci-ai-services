"""
   Author: ganrad01@gmail.com

   Description: Application module. Defines the aiohttp application factory. This module
   creates and configures the DI container and web.Application. It also defines the URL
   routes and respective handlers.

   Dated: 07-06-2022

   Notes:
"""

import logging
import logging.config
import yaml

from aiohttp import web

from .containers import Container
from . import handlers

def create_app() -> web.Application:

    container = Container()
    if not container.config.oci.compartment_id:
        container.config.oci.compartment_id.from_env("OCI_Compartment_ID")

    app = web.Application()
    app.container = container

    app.add_routes([
        web.post("/inference/stream", handlers.inferStream),
        web.get("/inference/healthz", handlers.getOciAdServiceHealth),
    ])
    return app


if __name__ == "__main__":
    # Set up logging
    with open("./log-config.yaml", "r") as f:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    logger = logging.getLogger(__name__)

    app = create_app()

    logger.info("AdStreamAPI server is starting....")

    web.run_app(app)
