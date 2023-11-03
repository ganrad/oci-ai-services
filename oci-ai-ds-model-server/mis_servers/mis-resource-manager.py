#!/usr/bin/env python
# coding: utf-8
# MIT License

# Copyright (c) 2023 OCI-AI-CE

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Module:
    A resource manager that manages the lifecycle of inference server resources.

Description:
    The primary purpose of this microservice is to manage the lifecycle (accept, persist, re-process, provide status, delete) of model inference server (mis) resources.

Supported resources:
- Async inference request.

Author:
    Ganesh Radhakrishnan (ganrad01@gmail.com)
Dated:
    10-21-2023

"""

from enum import Enum
import datetime
import json
import logging
import os
import psycopg2
import requests
import sys
import time
import traceback

from models.async_infer_dao import AsyncInferenceRequest

from fastapi import Request, FastAPI, HTTPException, Form, Body, Header
from pydantic import BaseModel

# ### Constants ###
API_VERSION="v1" # Published API Version
DATE_FORMAT="%Y-%m-%d %I:%M:%S %p"
START_TIME=datetime.datetime.now().strftime(DATE_FORMAT)

# ### Global Vars ###
api_endpoint = "/api/" + API_VERSION # API Endpoint/Route

# ### Inner Classes ###
class OperationStatus(Enum):
    ACCEPTED = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4

# ### Module Functions ###
def model_present_in_cache(model_id):
    """
       Returns True if model is present in cache else False
    """
    for entry in model_cache:
        if entry.model_ocid == model_id:
            return True
    return False

def object_to_dict(obj):
    """
    Convert a class object to a dictionary
    """

    data = {}
    if getattr(obj, '__dict__', None):
        for key, value in obj.__dict__.items():
            try:
                data[key] = object_to_dict(value)
            except AttributeError:
                data[key] = value
        return data
    else:
        return obj

# ### DB Functions ###
def create_db_tables():
    """
       Create the resource table(s) in PGSQL
    """
    # Establish the DB connection
    conn = psycopg2.connect(
	database=db_name,
	user=db_uname,
	password=db_password,
	host=db_host,
	port=db_host_port
    )
    # Creating table as per requirement
    sql = "CREATE TABLE IF NOT EXISTS INF_JOBS(id BIGSERIAL PRIMARY KEY,data JSONB)"

    # Creating a cursor object using the cursor() method
    with conn.cursor() as cursor:
        cursor.execute(sql)
        count = cursor.rowcount

    conn.commit()
    if count:
        logger.info("create_db_tables(): Table [INF_JOBS] created successfully ...")
    else:
        logger.info("create_db_tables(): Table [INF_JOBS] already exists, skip creation ...")

    # Closing the connection
    conn.close()

# ### Configure logging ###
# Default log level is INFO. Can be set and injected at container runtime.

# Read from config file
loglevel = os.getenv("LOG_LEVEL", default="INFO") # one of DEBUG,INFO,WARNING,ERROR,CRITICAL
nloglevel = getattr(logging,loglevel.upper(),None)
if not isinstance(nloglevel, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logger = logging.getLogger('mis-resource-manager')
logger.setLevel(nloglevel)

ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

# ### Configure Postgresql client ###
db_host = os.getenv("POSTGRES_HOST", default=f"postgres.{os.getenv('POD_NAMESPACE')}")
db_host_port = os.getenv("POSTGRES_SERVICE_PORT", default="5432")
db_name = os.getenv("POSTGRES_DB", default="postgres")
db_uname = os.getenv("POSTGRES_USER", default="postgres")
db_password = os.getenv("POSTGRES_PASSWORD", default="cw2023!")
db_params = {
    "db_name": db_name,
    "db_uname": db_uname,
    "db_password": db_password,
    "db_host": db_host,
    "db_host_port": db_host_port
}

logger.info(f"Main(): Set Postgresql client connection params:\n {db_params}")
try:
    create_db_tables()
except Exception as e:
    logger.fatal(f"Main(): Encountered exception: {e}")
    logger.fatal("Main(): Could not establish connectivity to persistent/DB backend, exiting server ...")
    exit()

# Set the server port; Is optional, can be injected at container runtime.
server_port=int(os.getenv("UVICORN_PORT", default="8000"))

# ### Configure FastAPI Server

api_description=f"""
<hr>

**API Version:** {API_VERSION}

**API Endpoint:** {api_endpoint}/

### Description
A microservice that exposes API endpoints for performing CRUD operations on inference server managed resources.

### Important Notes
<hr>

"""

tags_metadata = [
    {
        "name": "Create Server Resource",
        "description": "**Create** a new server managed resource"
    },
    {
        "name": "Get Resource Details",
        "description": "**Retrieve** the managed resource information"
    },
    {
        "name": "Update Server Resource",
        "description": "**Update** the server managed resource"
    },
    {
        "name": "Remove Server Resource",
        "description": "**Remove** the server managed resource"
    }
]

# Initialize the FastAPI Uvicorn Server
app = FastAPI(
    title="Inference Server Resource Manager",
    description=api_description,
    version=API_VERSION,
    contact={
        "name": "OCI AI Services Customer Engineering",
        "url": "https://github.com/ganrad/oci-ai-services/tree/main/oci-ai-ds-model-server",
        "email": "ganrad01@gmail.com"
    },
    license_info={
        "name": "The MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    openapi_url=api_endpoint + "/openapi.json",
    docs_url=api_endpoint + "/docs",
    redoc_url=None,
    openapi_tags=tags_metadata
)

# ### Microservice API ###

@app.get(api_endpoint + "/healthcheck/", tags=["Health Check"], status_code=200)
async def health_check(probe_type: str = Header(default=None)): # =Py 3.8/3.9
    """Run a health check on this microservice

    HTTP Headers
    ------------
    probe-type : (str, optional)

        Any string value eg., readiness, liveness ...

    Returns
    -------
    result : dict

        A dictionary containing current health status of this microservice

    """

    results = {
         "probe_type": probe_type,
         "backend_health": "OK",
         "time": datetime.datetime.now().strftime(DATE_FORMAT),
         "operation": "health_check",
         "status": OperationStatus.COMPLETED.name
    }
    logger.info(f"health_check(): Probe={probe_type}")
    return results

@app.post(api_endpoint + "/create/{resource_type}", tags=["Create Server Resource"], status_code=201)
async def create_resource(resource_type: str, data: dict = Body()):
    """Creates a new server managed resource

    Parameters
    ----------
    resource_type: str

        The type of the resource

    data: dict

        The json payload converted to a dict

    Raises
    ------
    Exception: HTTPException

        An exception is thrown if the server is unable to process the request

    Returns
    -------
    result : dict

        A dictionary containing the status of the requested operation

    """

    logger.info(f"create_resource():\nResource Type: {resource_type}\nResource (dict): {data}")

    try:
        async_request = AsyncInferenceRequest(data=db_params)
        count = async_request.create_entity(data=data)
    except Exception as e:
        logger.info(f"create_resource(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Encountered exception while persisting data", 
            "err_detail": str(e)
        }
        # return 500: Internal server error
        raise HTTPException(status_code=500, detail=err_detail)

    resp_msg = {
        "operation": "create_resource",
        "resource_type": resource_type,
        "db_recs_inserted": count,
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg
    
@app.get(api_endpoint + "/getresourceinfo/{resource_type}", tags=["Get Resource Details"], status_code=200)
async def get_resource_details(resource_type: str, resource_id: str):
    """Retrieves the server managed resource details

    Parameters
    ----------
    resource_type : str

        The type of the resource

    resource_id : str

        The unique ID of the resource

    Raises
    ------
    Exception: HTTPException

        An exception is thrown if the server is unable to process the request

    Returns
    -------
    result : dict

        A dictionary containing the resource details

    """

    logger.info(f"get_resource_details():\nResource Type: {resource_type}\nResource ID: {resource_id}")

    try:
        async_request = AsyncInferenceRequest(data=db_params)
        result = async_request.get_entity_by_id(jobid=resource_id)
    except Exception as e:
        logger.info(f"get_resource_details(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Encountered exception while reading data", 
            "err_detail": str(e)
        }
        # return 422: Unprocessable Content
        raise HTTPException(status_code=422, detail=err_detail)

    resp_msg = {
        "operation": "get_resource_details",
        "resource_type": resource_type,
        "job_details": result,
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg

@app.post(api_endpoint + "/update/{resource_type}", tags=["Update Server Resource"], status_code=201)
async def update_resource(resource_type: str, resource_id: str):
    """Updates the server managed resource

    Parameters
    ----------
    resource_type : str
    resource_id : str

    Returns
    -------
    result : dict

        A dictionary containing the updated resource attributes

    """

    resp_msg = {
        "operation": "update_resource",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg

@app.delete(api_endpoint + "/delete/{resource_type}", tags=["Remove Server Resource"], status_code=200)
async def remove_resource(resource_type: str, resource_id: str):
    """Removes the server managed resource

    Parameters
    ----------
    resource_type : str
    resource_id : str

    Raises
    ------
    Exception : HTTPException

    An exception is thrown when the resource is not found

    Returns
    -------
    result : dict

        A dictionary containing the status of delete resource operation

    """

    resp_msg = {
        "operation": "delete_resource",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg
