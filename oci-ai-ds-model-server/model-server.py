#!/usr/bin/env python
# coding: utf-8
# MIT License

# Copyright (c) 2023 HZ-MS-CSA

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

# ###
# An Inference Server which serves multiple ML models trained and registered 
# in OCI Data Science Catalog.
#
# Description: This server can be used to run inferences on multiple ML
# models trained and registered in OCI Data Science Model Catalog. A single 
# instance of this inference server can serve multiple ML models registered in 
# model catalog. However, the ML models must have been trained in the same 
# conda environment and have the same set of 3rd party libary dependencies 
# (Python libraries).
#
# Author: Ganesh Radhakrishnan (ganrad01@gmail.com)
# Dated: 01-26-2023
#
# Notes:
#
# ###

from importlib.metadata import version
import datetime
import importlib.util
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from zipfile import ZipFile

import oci
import yaml

# ### Constants ###
SERVER_VERSION="0.0.2"
DATE_FORMAT="%Y-%m-%d %I:%M:%S %p"
START_TIME=datetime.datetime.now().strftime(DATE_FORMAT)

# ### Global Vars ###
reqs_success = 0 # No. of scoring requests completed successfully
reqs_failures = 0 # No. of failures encountered by this server
reqs_fail = 0 # No. of scoring requests which failed eg., due to incorrect data

model_cache = [] # Model metadata cache. Stores loaded model artifact metadata.

# ### Classes ###
class ModelCache:
  def __init__(self, name, ocid):
      self.model_name = name
      self.model_ocid = ocid
      self.inf_calls = 0
      self.last_reload_time = datetime.datetime.now().strftime(DATE_FORMAT)
      self.no_of_reloads = 1

  def __str__(self):
      return f"model_name: {self.model_name},model_ocid: {self.model_ocid},inf_calls: {self.inf_calls},last_reload: {self.last_reload_time},no_of_reloads: {self.no_of_reloads}"

# ### Module Functions ###
"""
  Updates the server model cache
"""
def update_model_cache(name, id, **kwargs):
    if "delete" in kwargs:
        model_cache[:] = [model for model in model_cache if not model.model_ocid == id]
        return
        
    found = False
    for meta in model_cache:
        if meta.model_ocid == id:
            found = True
            if "loaded" in kwargs:
                meta.last_reload_time = datetime.datetime.now().strftime(DATE_FORMAT)
                meta.no_of_reloads += 1
            if "inference" in kwargs:
                meta.inf_calls += 1
            break
    if not found:
        model_cache.append(ModelCache(name, id))

# ### Configure logging ###
# Default log level is INFO
loglevel = os.getenv('LOG_LEVEL', 'INFO') # one of DEBUG,INFO,WARNING,ERROR,CRITICAL
nloglevel = getattr(logging,loglevel.upper(),None)
if not isinstance(nloglevel, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logger = logging.getLogger('model-server')
logger.setLevel(nloglevel)

ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

# ### Configure OCI client ###
config = oci.config.from_file(os.environ['OCI_CONFIG_FILE_LOCATION'])
logger.info("Main(): Loaded OCI client config file")

# Set the server port
server_port=int(os.environ['UVICORN_PORT'])

# Initialize data science service client with config file
data_science_client = oci.data_science.DataScienceClient(config)

# ### Configure FastAPI Server
from fastapi import Request, FastAPI, HTTPException, Form, Body, Header, UploadFile

api_description="""
A REST API which allows users to load ML models and perform inferences on models
trained in OCI Data Science Platform.
"""

tags_metadata = [
    {
        "name": "Health Check",
        "description": "Liveness probe - Check if the API is up and runnning (alive)"
    },
    {
        "name": "Model Server Info.",
        "description": "Get model server information"
    },
    {
        "name": "Load Model",
        "description": "Load a ML model registered in OCI Data Science Catalog"
    },
    {
        "name": "Upload Model",
        "description": "Upload a ML model artifact (Zip file) to the inference server"
    },
    {
        "name": "Get Model Info.",
        "description": "Get an registered model's metadata"
    },
    {
        "name": "List Models",
        "description": "List model artifacts registered in a OCI Data Science Model Catalog"
    },
    {
        "name": "Predict Outcomes",
        "description": "Use live inference data to run predictions against a trained ML model"
    }
]

# Initialize the FastAPI Uvicorn Server
app = FastAPI(
    title="OCI Data Science Multi Model Inference Server",
    description=api_description,
    version=SERVER_VERSION,
    contact={
        "name": "Multi Model Inference Server",
        "url": "https://github.com/ganrad/oci-ai-services/tree/main/oci-ai-ds-model-server",
        "email": "ganrad01@gmail.com"
    },
    license_info={
        "name": "The MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    openapi_tags=tags_metadata
)

# ### Model Server API ###

"""
  Returns current health status of model server
"""
@app.get("/healthcheck/", tags=["Health Check"], status_code=200)
async def health_check(probe_type: str | None = Header(default=None)):
    results = {
         "OCI Connectivity": "OK",
         "HealthStatus": "UP",
         "Time": datetime.datetime.now().strftime(DATE_FORMAT)
    }
    logger.debug(f"health_check(): {probe_type}")
    return results

"""
  Returns model server info.
"""
@app.get("/serverinfo/", tags=["Model Server Info."], status_code=200)
async def server_info():
    results = {
         "Conda Environment (Slug name)": os.getenv("CONDA_HOME"),
         "Python": sys.version,
         "Web Server": "Uvicorn {ws_version}".format(ws_version = version('uvicorn')),
         "Framework": "FastAPI {frm_version}".format(frm_version = version('fastapi')),
         "Listen Port": server_port,
         "Log Level": os.getenv("UVICORN_LOG_LEVEL"),
         "Start time": START_TIME,
         # "Workers": os.getenv("UVICORN_WORKERS")
         "Server Info": {
           "Version": SERVER_VERSION,
           "Root": os.getcwd(),
           "Node Name": os.getenv("NODE_NAME"),
           "Namespace": os.getenv("POD_NAMESPACE"),
           "Instance Name": os.getenv("POD_NAME"),
           "Instance IP": os.getenv("POD_IP"),
           "Service Account": os.getenv("POD_SVC_ACCOUNT")
         },
         "Runtime Info": {
           "Scored Requests": reqs_success,
           "Failed Requests": reqs_fail,
           "Server Failures": reqs_failures
         },
         "Model Info": model_cache
    }
    return results

"""
  Loads the ML model artifacts from OCI Data Science.  Call this function to
  pre-load the model into the cache.

  Parameters:
  model_id: OCI Data Science Model OCID
"""
@app.get("/loadmodel/{model_id}", tags=["Load Model"], status_code=200)
async def load_model(model_id):
    global reqs_failures

    # Retrieve model metadata from OCI DS
    try:
        get_model_response = data_science_client.get_model(model_id=model_id)
    except Exception as e:
        reqs_failures += 1
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Internal server error",
            "err_detail": str(e)
        }
        raise HTTPException(status_code=500, detail=err_detail)
    
    # Check if conda env matches model slug name if not raise an exception
    model_obj = get_model_response.data
    slug_name = None
    for mdata in model_obj.custom_metadata_list:
        if ( mdata.category == "Training Environment" and mdata.key == "SlugName" ):
            slug_name = mdata.value
            break

    # TODO: If slug_name is empty then check if custom conda env is present!!

    logger.debug(f"load_model(): SlugName: {slug_name}")
    if slug_name != os.getenv('CONDA_HOME'):
        err_detail = {
            "err_message": f"Bad Request. Model Slug name: [{slug_name}] does not match Conda environment: [{os.getenv('CONDA_HOME')}]",
            "err_detail": "Check the Slug name in the model taxonomy. The slug name should match the Conda environment of the multi model server instance. You can check the Conda environment of this model server instance by invoking the '/serverinfo/' endpoint."
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)
    model_name = model_obj.display_name

    st_time = time.time();
    try:
        # Fetch the model artifacts
        get_model_artifact_content_response = data_science_client.get_model_artifact_content(model_id=model_id, opc_request_id=os.getenv("POD_NAME"))
    except Exception as e:
        reqs_failures += 1
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Internal server error",
            "err_detail": str(e)
        }
        raise HTTPException(status_code=500, detail=err_detail)

    # Get the data from response
    logger.debug(f"load_model(): Resource URL: {get_model_artifact_content_response.request.url}")
    logger.info(f"load_model(): Fetch model artifacts status: {get_model_artifact_content_response.status}")

    logger.debug(f"load_model(): Current working directory: {os.getcwd()}")
    artifact_file = model_id + ".zip"
    # Save the downloaded model artifact zip file in current directory
    with open(artifact_file,'wb') as zfile:
        for chunk in get_model_artifact_content_response.data.raw.stream(1024 * 1024, decode_content=False):
            zfile.write(chunk)
    logger.debug(f"load_model(): Saved model artifact zip file: {artifact_file}")

    # Check if model directory exists; if so delete and recreate it else create it
    zfile_path =  "./" + model_id
    if not os.path.isdir(zfile_path):
        os.makedirs(zfile_path)
        update_model_cache(model_name,model_id)
        logger.debug("load_model(): Created model artifact directory")
    else:
        shutil.rmtree(zfile_path)
        os.makedirs(zfile_path)
        update_model_cache(model_name,model_id,loaded=True)
        logger.debug("load_model(): Deleted model artifact directory & recreated it")

    # Unzip the model artifact file into the model id folder -
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(zfile_path)
    logger.debug(f"load_model(): Extracted model artifacts from zip file into directory: {zfile_path}")

    # Delete the artifact zip file
    os.remove(artifact_file)
    logger.debug(f"load_model(): Deleted model artifact zip file: {artifact_file}")

    en_time = time.time() - st_time
    resp_msg = {
        "model_name": model_name,
        "model_id": model_id,
        "operation": "load",
        "loadtime" : en_time,
        "status": "succeeded" }

    return resp_msg

"""
  Retrieves and returns the model metadata

  Parameters:
  model_id: OCI Data Science Model OCID
"""
@app.get("/getmodelinfo/{model_id}", tags=["Get Model Info."], status_code=200)
async def get_model_metadata(model_id):
    file_path = os.getcwd() + '/' + model_id + '/runtime.yaml'
    logger.debug(f"get_model_metadata(): File Path={file_path}")
    
    # Load the model artifacts if model runtime file is not present
    # if not file_obj.is_file():
    if not os.path.isfile(file_path):
        model_status = await load_model(model_id)
        logger.debug(f"get_model_metadata(): Load model status: {model_status['status']}")

    metadata = ''
    with open(file_path, 'r') as f:
        metadata = yaml.safe_load(f)

    return metadata

"""
  Retrieves the models for a given OCI compartment and DS project.

  Parameters:
  compartment_id: OCI Compartment ID
  project_id: OCI Data Science Project OCID

  Response body: A list containing model dictionaries - ocid's,name,state ...
"""
@app.get("/listmodels/", tags=["List Models"], status_code=200)
async def list_models(compartment_id: str, project_id: str, no_of_models=400):
    # Use DS API to fetch the model artifacts
    list_models_response = data_science_client.list_models(
        compartment_id=compartment_id,
        project_id=project_id,
        lifecycle_state=oci.data_science.models.Model.LIFECYCLE_STATE_ACTIVE,
        limit=no_of_models)

    model_list = list_models_response.data
    logger.debug(f"list_models():\n{model_list}")

    return model_list

"""
  Scores the data points sent in the payload using the respective model.

  Parameters:
  model_id: OCI Data Science Model OCID
  Request body: Data in the format expected by the model object
"""
@app.post("/score/", tags=["Predict Outcomes"], status_code=200)
#async def score(model_id: str, request: Request): (also works!)
async def score(model_id: str, data: dict = Body()):
    # Get predictions and explanations for each data point
    # data = await request.json(); # returns body as dictionary
    # data = await request.body(); # returns body as string
    global reqs_success
    global reqs_fail

    logger.debug(f"score(): Inference Inp. Data: {data}")
    if not data:
        reqs_fail += 1
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail="Bad Request. No data sent in the request body!")

    file_path = './' + model_id + '/score.py'
    ld_time = 0
    # Load the model artifacts if model directory is not present
    model_status = None
    if not os.path.isfile(file_path):
        model_status = await load_model(model_id)
        ld_time = model_status['loadtime']
        logger.debug(f"score(): Load model status: {model_status['status']}")

    module_name = 'score'

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    try:
        st_time = time.time()
        results = module.predict(data)
        en_time = time.time() - st_time
    except Exception as e:
        reqs_fail += 1
        logger.error(f"score(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Bad Request. Malformed data sent in the request body!",
            "err_detail": str(e)
        }
        # return 422: Unprocessable Entity
        raise HTTPException(status_code=422, detail=err_detail)

    results_data = dict()
    results_data["data"] = results
    results_data["load_time"] = ld_time
    results_data["inference_time"] = en_time
    logger.debug(f"score(): Inference Out. Data: {results_data}")

    reqs_success += 1
    update_model_cache(None,model_id,inference=True)

    return results_data

"""
  Upload model artifacts to the inference server.  The server will cache it
  as long as it is alive.

  Parameters:
  model_name: Unique model name.  Caution: If name is not unique, then already 
  cached model (if any) will be overwritten.
  file: Zipped archive file containing model artifacts

  Response body: A dict containing file upload status
"""
@app.post("/uploadmodel/", tags=["Upload Model"], status_code=200)
async def upload_model(file: UploadFile, model_name: str = Form()):
    artifact_file = file.filename
    file_obj = file.file
    logger.info(f"upload_model(): File to upload: {artifact_file}")

    if not artifact_file.endswith(".zip"):
        err_detail = {
            "err_message": "Bad Request. Only zipped model artifact files are accepted!",
            "err_detail": "Unable to process the request"
        }
        # return 415: Unsupported media type
        raise HTTPException(status_code=415, detail=err_detail)

    # Create the model artifact directory
    model_id = artifact_file[:artifact_file.index(".zip")]
    zfile_path =  "./" + model_id
    if not os.path.isdir(zfile_path):
        os.makedirs(zfile_path)
        update_model_cache(model_name,model_id)
        logger.debug("upload_model(): Created model artifact directory")
    else:
        shutil.rmtree(zfile_path)
        os.makedirs(zfile_path)
        update_model_cache(model_name,model_id,loaded=True)
        logger.debug("upload_model(): Deleted model artifact directory & recreated it")

    # Unzip the model artifact file into the model id folder -
    with ZipFile(file_obj,'r') as zfile:
        zfile.extractall(zfile_path)
    logger.debug(f"upload_model(): Extracted model artifacts from uploaded zip file into directory: {zfile_path}")

    # Check to see if the model directory contains a 'score.py' file
    score_file = Path("{}/score.py".format(zfile_path))
    if not score_file.is_file():
        shutil.rmtree(zfile_path)
        update_model_cache(model_name,model_id,delete=True)
        err_detail = {
            "err_message": "Bad Request. Zip file contents are corrupted and/or unrecognizable!",
            "err_detail": "Unable to process the request"
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)
        
    resp_dict = {
        "modelName": model_name,
        "fileName": file.filename,
        "contentType": file.content_type,
        "modelUploadStatus": "OK"
    }

    return resp_dict
