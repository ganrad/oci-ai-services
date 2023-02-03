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

# ### Model Scoring Server for models created using OCI Data Science ###

import importlib.util
import json
import logging
import os
import shutil
import time
from zipfile import ZipFile

import oci
import yaml

# ### Configure logging ###
loglevel = os.getenv('LOG_LEVEL', 'INFO') # one of DEBUG,INFO,WARNING,ERROR,CRITICAL
nloglevel = getattr(logging,loglevel.upper(),None)
if not isinstance(nloglevel, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logger = logging.getLogger('model-server')
logger.setLevel(nloglevel)

ch = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

# ### Configure OCI client ###
config = oci.config.from_file(os.environ['OCI_CONFIG_FILE_LOCATION'])
logger.info("Loaded OCI client config file")

# Set the server port
server_port=int(os.environ['MODEL_SERVER_PORT'])

# Initialize data science service client with config file
data_science_client = oci.data_science.DataScienceClient(config)

# ### Model Server API ###
from fastapi import Request, FastAPI, HTTPException, Body

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
        "name": "Load Model",
        "description": "Load a ML model registered in OCI Data Science Catalog"
    },
    {
        "name": "Get Model Info.",
        "description": "Get model metadata"
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

app = FastAPI(
    title="OCI Data Science ML Model Server",
    description=api_description,
    version="0.0.1",
    contact={
        "name": "Ganesh Radhakrishnan",
        "url": "https://github.com/ganrad",
        "email": "ganrad01@gmail.com"
    },
    license_info={
        "name": "The MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    openapi_tags=tags_metadata
)

"""
  Returns current health status of model server
"""
@app.get("/healthcheck/", tags=["Health Check"], status_code=200)
async def health_check():
    results = {
         "OCI Connectivity": "OK",
         "HealthStatus": "OK"
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
    st_time = time.time();

    # Use DS API to fetch the model artifact
    get_model_artifact_content_response = data_science_client.get_model_artifact_content(
    model_id=model_id,
    opc_request_id="mserver-001",
    allow_control_chars=False)

    # Get the data from response
    logger.debug(f"Resource URL: {get_model_artifact_content_response.request.url}")
    logger.info(f"Status: {get_model_artifact_content_response.status}")

    logger.debug(f"Current working directory: {os.getcwd()}")
    artifact_file = model_id + ".zip"
    # Save the downloaded model artifact zip file in current directory
    with open(artifact_file,'wb') as zfile:
        for chunk in get_model_artifact_content_response.data.raw.stream(1024 * 1024, decode_content=False):
            zfile.write(chunk)
    logger.debug(f"Saved model artifact zip file: {artifact_file}")

    # Check if model directory exists; if so delete and recreate it else create it
    zfile_path =  "./" + model_id
    if not os.path.isdir(zfile_path):
        os.makedirs(zfile_path)
        logger.debug("Created model artifact directory")
    else:
        shutil.rmtree(zfile_path)
        os.makedirs(zfile_path)
        logger.debug("Deleted model artifact directory & recreated it")

    # Unzip the model artifact file into the model id folder -
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(zfile_path)
    logger.debug(f"Extracted model artifacts from zip file into directory: {zfile_path}")

    # Delete the artifact zip file
    os.remove(artifact_file)
    logger.debug(f"Deleted model artifact zip file: {artifact_file}")

    en_time = time.time() - st_time
    resp_msg = {
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
    logger.debug(f"File Path={file_path}")
    
    # Load the model artifacts if model runtime file is not present
    # if not file_obj.is_file():
    if not os.path.isfile(file_path):
        model_status = await load_model(model_id)
        logger.debug(f"Load model results: {model_status}")

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
    logger.debug(model_list)

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
    logger.debug(f"Inference Inp. Data: {data}")
    if not data:
        raise HTTPException(status_code=400, detail="Bad Request. No data sent in the request body!")

    file_path = './' + model_id + '/score.py'
    # Load the model artifacts if model directory is not present
    if not os.path.isfile(file_path):
        model_status = await load_model(model_id)
        logger.debug(f"Load model results: {model_status}")

    module_name = 'score'

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    st_time = time.time()
    results = module.predict(data)
    en_time = time.time() - st_time

    results_data = dict()
    results_data["data"] = results
    results_data["time"] = en_time
    logger.debug(f"Inference Out. Data: {results_data}")

    return results_data
