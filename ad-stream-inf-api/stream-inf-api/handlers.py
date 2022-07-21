"""
   Author: Ganesh Radhakrishnan (ganrad01@gmail.com)

   Description: Handlers module. Contains implementations for all URL handlers

   Dated: 07-06-2022

   Notes:
"""

import json
import logging

from aiohttp import web
from dependency_injector.wiring import Provide, inject

from .services import AdService
from .containers import Container
from .errors import StreamApiException
from .constants import *

log = logging.getLogger(__name__)

@inject
async def getOciAdServiceHealth(
      request: web.Request,
      ad_service: AdService = Provide[Container.ad_service]
) -> web.Response:
    log.debug("getOciAdServiceHealth()")
    apiConfig = ad_service.getAdServiceHealth()

    return web.json_response(apiConfig)

@inject
async def inferStream(
      request: web.Request,
      ad_service: AdService = Provide[Container.ad_service]
) -> web.Response:
    log.info("inferStream: BEGIN")

    model_ocid = request.query.get("ocid")
    if model_ocid is None or model_ocid == "":
        return web.HTTPBadRequest(text="Model OCID (Query param='ocid') is a required parameter!")

    client_id = request.query.get("client_id")
    if client_id is None or client_id == "":
        return web.HTTPBadRequest(text="Client ID (Query param='client_id') is a required parameter!")

    content_type = request.query.get("content_type")
    if content_type is None or content_type == "":
        content_type = CONTENT_TYPE_CSV
    else:
        content_type = content_type.upper()
    if (content_type != CONTENT_TYPE_CSV) or (content_type != CONTENT_TYPE_JSON):
        content_type = CONTENT_TYPE_CSV

    window_size = request.query.get("window_size")
    if window_size is None or window_size == "":
        window_size = None
    else:
        if not window_size.isnumeric():
            return web.HTTPBadRequest(text="Window Size (Query param='window_size') is an integer!")
        else:
            window_size = int(window_size)
 
    tmp = request.query.get("sensitivity"); sensitivity_str = tmp if tmp else DEF_SENSITIVITY
    # check if value is float
    try:
        sensitivity = float(sensitivity_str)
    except ValueError:
        sensitivity = float(DEF_SENSITIVITY)

    tmp = request.query.get("refresh_cache"); recache = True if tmp and (tmp == "True" or tmp == "true") else False
    
    log.info(f"inferStream: Client ID=[{client_id}] - Input Params:\n----\nOCID = {model_ocid}\nContent Type = {content_type}\nWindow Size = {window_size}\nSensitivity = {sensitivity}\nRefresh Cache = {recache}\n----")

    if request.body_exists:
        content_length = request.content_length
        content = request.content
        
        data_bytes = await content.read()
        log.info(f"inferStream: Bytes read=[{content_length}]")

        try:
            infer_results = ad_service.executeInference(
                client_id,
                model_ocid,
                data_bytes,
                window_s = window_size,
                sensitivity = sensitivity,
                ctnt_type = content_type,
                refresh_cache = recache)
        except (StreamApiException) as sae:
            return web.HTTPBadRequest(text=json.dumps(sae.__dict__))
        except (Exception) as e:
            log.exception(f"inferStream: Encountered Exception while serving request. Client ID=[{client_id}]")
            return web.HTTPInternalServerError(text=f"Service handler=[{__name__}], encountered an exception while serving request.")

    else:
        log.info(f"inferStream: Client ID=[{client_id}] - No data sent in request")
        return web.HTTPBadRequest(text="No data sent in request")

    log.info("inferStream: END")
    ad_results = str(infer_results)

    #return web.Response(text=json.dumps(ad_results,ensure_ascii=False))
    #with open("ad-output.json","w") as f:
        #f.write(ad_results)

    return web.Response(text=ad_results)
