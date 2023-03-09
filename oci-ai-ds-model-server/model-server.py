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
    An Inference Server which serves multiple ML models trained and registered in OCI Data Science Catalog.

Description:
    This server can be used to run inferences on multiple ML models trained and registered in OCI Data Science Model Catalog. A single instance of this inference server can serve multiple ML models registered in model catalog. However, the ML models must have been trained in the same conda environment requiring Python library dependencies contained within this environment.

Author:
    Ganesh Radhakrishnan (ganrad01@gmail.com)
Dated:
    01-26-2023

Notes:

"""

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
def update_model_cache(name, id, **kwargs):
    """
      Updates the server model cache
    """
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

# ### Configure logging for mmis ###
# Default log level is INFO. Can be set and injected at container runtime.
loglevel = os.getenv("LOG_LEVEL", default="INFO") # one of DEBUG,INFO,WARNING,ERROR,CRITICAL
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
# OCI Client API config profile.  Can be injected at container runtime.
oci_cli_profile = os.getenv("OCI_CONFIG_PROFILE",default="DEFAULT")

# NOTE: If OCI_CONFIG_FILE_LOCATION env var is not set in the container, an
# exception will be thrown.  Server will not start!
oci_config = oci.config.from_file(file_location=os.environ['OCI_CONFIG_FILE_LOCATION'], profile_name=oci_cli_profile)
logger.info("Main(): Loaded OCI client config file")

# Set the server port; Is optional, can be injected at container runtime.
server_port=int(os.getenv("UVICORN_PORT",default="8000"))

# Initialize data science service client with config file
data_science_client = oci.data_science.DataScienceClient(oci_config)

# ### Configure FastAPI Server
from fastapi import Request, FastAPI, HTTPException, Form, Body, Header, UploadFile

api_description=f"""
### Description
A REST API which allows users to load ML models and perform inferences on models
trained in OCI Data Science Platform.

### Environment
**Server Version:** {SERVER_VERSION}

**Conda Env./Slug Name:** {os.getenv('CONDA_HOME')}

### Notes
"""

tags_metadata = [
    {
        "name": "Load Model",
        "description": "**Load** a ML model registered in OCI Data Science Catalog into Inference Server"
    },
    {
        "name": "Upload Model",
        "description": "**Upload** a ML model artifact (Zip file) to the Inference Server"
    },
    {
        "name": "Get Model Info.",
        "description": "**Get** a registered model's metadata"
    },
    {
        "name": "List Models",
        "description": "**List** model artifacts registered in a OCI Data Science Model Catalog"
    },
    {
        "name": "Predict Outcomes",
        "description": "Use inference data to run **predictions** against a trained ML model"
    },
    {
        "name": "Remove Model",
        "description": "**Remove** a ML model from Inference Server"
    },
    {
        "name": "Model Server Info.",
        "description": "Get model server information"
    },
    {
        "name": "Health Check",
        "description": "Liveness probe - Check if the API is up and runnning (alive)"
    }
]

# Initialize the FastAPI Uvicorn Server
app = FastAPI(
    title="OCI Data Science Multi Model Inference Server",
    description=api_description,
    version=SERVER_VERSION,
    contact={
        "name": "OCI AI Services Customer Engineering",
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
@app.get("/healthcheck/", tags=["Health Check"], status_code=200)
#async def health_check(probe_type: str | None = Header(default=None)): # Works > Py 3.10+
async def health_check(probe_type: str = Header(default=None)): # =Py 3.8/3.9
    """Run a health check on this server instance

    HTTP Headers
    ------------
    probe-type : (str, optional)
        Any string value eg., readiness, liveness ...

    Returns
    -------
    dict: Current health status of Multi Model Inference Server

    """

    results = {
         "oci_connectivity": "OK",
         "health_status": "UP",
         "probe_type": probe_type,
         "time": datetime.datetime.now().strftime(DATE_FORMAT)
    }
    logger.info(f"health_check(): Probe={probe_type}")
    return results

@app.get("/serverinfo/", tags=["Model Server Info."], status_code=200)
async def server_info():
    """Retrieve the server instance runtime info.

    Returns
    -------
    dict: Inference Server info.

    """

    host_type = os.getenv("PLATFORM_NAME")
    logger.debug(f"server_info(): Host type={host_type}")
    if host_type and (host_type == 'Kubernetes' or host_type == 'OKE'):
        scale_type = "Auto"
    else:
        scale_type = "Manual"

    results = {
         "conda_environment": os.getenv("CONDA_HOME"),
         "python_version": sys.version,
         "web_server": "Uvicorn {ws_version}".format(ws_version = version('uvicorn')),
         "framework": "FastAPI {frm_version}".format(frm_version = version('fastapi')),
         "start_time": START_TIME,
         "platform": {
           "type": os.getenv("PLATFORM_NAME"),
           "scaling": scale_type
         },
         "build_info": {
           "commit_hash": os.getenv("DEVOPS_COMMIT_ID"),
           "pipeline_ocid": os.getenv("DEVOPS_PIPELINE_ID"),
           "build_run_ocid": os.getenv("DEVOPS_BUILD_ID")
         },
         "deployment_info": {
           "pipeline_ocid": os.getenv("DEPLOYMENT_PIPELINE_OCID"),
           "deployment_name": os.getenv("DEPLOYMENT_OCID")
         },
         "oci_client_info": {
           "profile": oci_cli_profile,
           "log_requests": oci_config.get('log_requests'),
           "tenancy": oci_config.get('tenancy'),
           "region": oci_config.get('region'),
           "key_file": oci_config.get('key_file')
         },
         "server_info": {
           "version": SERVER_VERSION,
           "root": os.getcwd(),
           "image_id": os.getenv("IMAGE_ID"),
           "node_name": os.getenv("NODE_NAME"),
           "pod_namespace": os.getenv("POD_NAMESPACE"),
           "pod_name": os.getenv("POD_NAME"),
           "pod_ip": os.getenv("POD_IP"),
           "port": server_port,
           "service_account": os.getenv("POD_SVC_ACCOUNT"),
           "log_level": os.getenv("UVICORN_LOG_LEVEL")
         },
         "runtime_info": {
           "scored_requests": reqs_success,
           "failed_requests": reqs_fail,
           "server_failures": reqs_failures
         },
         "model_info": model_cache
    }

    return results

@app.get("/loadmodel/{model_id}", tags=["Load Model"], status_code=200)
async def load_model(model_id):
    """Loads the ML model artifacts from OCI Data Science.  Call this function to pre-load the model into the Inference Server cache.

    Parameters
    ----------
    model_id : str
        OCI Data Science Model OCID

    Raises
    ------
    HTTPException: An exception is thrown when 1) Model's metadata cannot be retrieved 2) Model is in in-active state 3) Model Slug name is NOT the same as this server instance's Conda env 3) Model's artifacts cannot be fetched from model catalog

    Returns
    -------
    dict: Status upon loading the model

    """
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
    
    model_obj = get_model_response.data
    model_name = model_obj.display_name

    # Check to see if the model's lifecycle state is 'Active'
    if model_obj.lifecycle_state != oci.data_science.models.Model.LIFECYCLE_STATE_ACTIVE:
        err_detail = {
            "err_message": f"Bad Request. Model : [{model_name}:{model_id}] is not in Active state",
            "err_detail": "Reactivate the model and then try loading it"
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

    # Check if conda env matches model slug name if not raise an exception
    slug_name = None
    for mdata in model_obj.custom_metadata_list:
        if ( mdata.category == "Training Environment" and mdata.key == "SlugName" ):
            slug_name = mdata.value
            break

    # NOTE: slug_name should not be empty. Should be set to the conda env name!!

    logger.debug(f"load_model(): SlugName: {slug_name}")
    if slug_name != os.getenv('CONDA_HOME'):
        err_detail = {
            "err_message": f"Bad Request. Model Slug name: [{slug_name}] does not match Conda environment: [{os.getenv('CONDA_HOME')}]",
            "err_detail": "Check the Slug name in the model taxonomy. The slug name should match the Conda environment of the multi model server instance. You can check the Conda environment of this model server instance by invoking the '/serverinfo/' endpoint."
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

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

@app.get("/getmodelinfo/{model_id}", tags=["Get Model Info."], status_code=200)
async def get_model_metadata(model_id):
    """Retrieves the model metadata

    Parameters
    ----------
    model_id : str
        OCI Data Science Model OCID

    Returns
    -------
    dict: Model artifact's runtime.yaml

    """

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

@app.get("/listmodels/", tags=["List Models"], status_code=200)
async def list_models(compartment_id: str, project_id: str, no_of_models=400):
    """Retrieves the models for a given OCI Compartment and Data Science Project.

    Parameters
    ----------
    compartment_id : str
        OCI Compartment OCID

    project_id : str
        OCI Data Science Project OCID

    Raises
    ------
    HTTPException: Any exception encountered while fetching the models is returned

    Returns
    -------
    dict: A list containing model dictionaries - ocid's,name,state ...

    """
    global reqs_failures

    logger.info(f"list_models(): Compartment ocid=[{compartment_id}, Project ocid=[{project_id}]")

    try:
        # Use DS API to fetch 'Active' model artifacts
        list_models_response = data_science_client.list_models(
            compartment_id=compartment_id,
            project_id=project_id,
            lifecycle_state=oci.data_science.models.Model.LIFECYCLE_STATE_ACTIVE,
            limit=no_of_models)
    except Exception as e:
        reqs_failures += 1
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Internal server error",
            "err_detail": str(e)
        }
        # return 500: Internal Server Error
        raise HTTPException(status_code=500, detail=err_detail)

    model_list = list_models_response.data
    logger.debug(f"list_models():\n{model_list}")

    return model_list

@app.post("/score/", tags=["Predict Outcomes"], status_code=200)
#async def score(model_id: str, request: Request): (also works!)
async def score(model_id: str, data: dict = Body()):
    """Scores the data points sent in the payload using the respective model.

    Parameters
    ----------
    model_id : str
        OCI Data Science Model OCID

    data : dict
        Inference data in the format expected by the model object

    Raises
    ------
    HTTPException: Any exception encountered during inferencing is returned

    Returns
    -------
    dict: A dictionary containing inference results

    """

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
            "err_message": "Malformed data sent in the request body!",
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

@app.post("/uploadmodel/", tags=["Upload Model"], status_code=201)
async def upload_model(file: UploadFile, model_name: str = Form()):
    """Upload model artifacts to the inference server.  The server will cache it
    as long as it is alive.

    Parameters
    ----------
    model_name : str
        Unique model name.  Caution: If name is not unique, then already cached model (if any) will be overwritten.

    file : file object
        Zipped archive file containing model artifacts

    Raises
    -------
    HTTPException: An exception is thrown when 1) If uploaded file is not a zip file 2) If score.py or runtime.yaml is not present in the model artifact directory (after zip file is exploded) 3) If value of attribute 'inference_env_slug' in runtime.yaml is not the same as this server instance's conda env

    Returns
    -------
    dict: A dict containing file upload status

    """

    artifact_file = file.filename
    file_obj = file.file
    logger.info(f"upload_model(): File to upload: {artifact_file}")

    if not artifact_file.endswith(".zip"):
        err_detail = {
            "err_message": "Only zipped model artifact files (.zip) are accepted!",
            "err_detail": "Unable to process the request"
        }
        # return 415: Unsupported media type
        raise HTTPException(status_code=415, detail=err_detail)

    model_id = artifact_file[:artifact_file.index(".zip")]

    # Create the model artifact directory
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

    # Check to see if the model directory contains a 'score.py' and 
    # 'runtime.yaml' file
    score_file = Path("{}/score.py".format(zfile_path))
    rtime_file = Path("{}/runtime.yaml".format(zfile_path))
    if not score_file.is_file() or not rtime_file.is_file():
        shutil.rmtree(zfile_path)
        update_model_cache(model_name,model_id,delete=True)
        err_detail = {
            "err_message": "Zip file contents are corrupted and/or unrecognizable!",
            "err_detail": "Unable to process the request"
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)
        
    # Read the 'runtime.yaml' and check the inference_env_slug value. It should
    # match the conda env / runtime of this server.
    with open(rtime_file, 'r') as f:
        runtime_info = yaml.safe_load(f)
    
    slug_name = runtime_info['MODEL_DEPLOYMENT']['INFERENCE_CONDA_ENV']['INFERENCE_ENV_SLUG']
    # print(f"SLUG NAME: {slug_name}")
    if slug_name != os.getenv('CONDA_HOME'):
        shutil.rmtree(zfile_path)
        update_model_cache(model_name,model_id,delete=True)
        err_detail = {
            "err_message": f"Bad Request. Model Slug name: [{slug_name}] does not match Conda environment: [{os.getenv('CONDA_HOME')}]",
            "err_detail": "The 'INFERENCE_ENV_SLUG' value in 'runtime.yaml' file does not match the Conda environment of the multi model server instance. You can check the Conda environment of this model server instance by invoking the '/serverinfo/' endpoint."
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

    resp_dict = {
        "model_name": model_name,
        "model_ocid": model_id,
        "slug_name": slug_name,
        "filename": file.filename,
        "content_type": file.content_type,
        "model_upload_status": "OK"
    }

    return resp_dict

@app.delete("/removemodel/{model_id}", tags=["Remove Model"], status_code=200)
async def remove_model(model_id):
    """Removes the ML model artifacts from Inference Server.

    Parameters
    ----------
    model_id : str
        OCI Data Science Model OCID

    Raises
    ------
    HTTPException: An exception is thrown when the model artifact directory is not found

    Returns
    -------
    dict: Status of delete operation

    """

    zfile_path =  "./" + model_id
    if os.path.isdir(zfile_path):
        shutil.rmtree(zfile_path)
        update_model_cache("",model_id,delete=True)
        logger.info(f"remove_model(): Deleted artifact directory for model ID:{model_id}")
    else:
        err_detail = {
            "err_message": "Model artifact directory not found!",
            "err_detail": "Unable to process the request"
        }
        # return 404: Not Found
        raise HTTPException(status_code=404, detail=err_detail)
        
    resp_msg = {
        "model_id": model_id,
        "operation": "delete",
        "status": "succeeded" }

    return resp_msg
