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
    An Inference Server which can serve multiple a) Machine learning (ML) models trained and registered in OCI Data Science Catalog & b) Large language models (LLM's) saved in OCI Object Storage.

Description:
    This server can be used to run inferences on multiple ML/LLM models. For ML models trained OCI Data Science, the models can be registered in Model Catalog. Large language models can be stored in OCI Object Storage and loaded into the inference server.  A single instance of this inference server can serve multiple models. However, the models must have been trained in (or use) the same conda environment.  The conda env must contain all the Python library dependencies required to run the model.

Author:
    Ganesh Radhakrishnan (ganrad01@gmail.com)
Dated:
    01-26-2023

Notes:
ID090223: ganrad: Fixed zip file upload issue/race-condition on multi-processors systems (GPU's + CPU's)
ID090423: ganrad: a) Model artifacts are saved in './models' directory. b) Support for serving large language models
ID090723: ganrad: model.metadata.category key should be all lowercase.
ID091023: ganrad: Added new api endpoint 'uploadllm' to load LLM's from OCI OS and save it to 'models' directory asynchronously (thru sidecar).  
ID092823: ganrad: Save the model registry file on add, delete operations.  On server restart, only load the models listed in the registry file.
ID093023: ganrad: Refactored API's to support multiple server instances.
ID100423: ganrad: Exposed API's for retrieving both instance and server info.
ID100623: ganrad: Introduced new API endpoints to deduce similarity scores by comparing expected and llm output results.
ID101423: ganrad: Introduced resource manager to handle lifecycle of server managed resources.
"""

from importlib.metadata import version
from enum import Enum
import aiofiles
import datetime
import glob
import importlib.util
import json
import logging
import os
import requests
import shutil
import sys
import time
import traceback
from pathlib import Path
import uuid
from zipfile import ZipFile

import oci
import yaml

from fastapi import Request, FastAPI, HTTPException, Form, Body, Header, File, UploadFile
from pydantic import BaseModel # ID091023.n

# ### Constants ###
API_VERSION="v1" # Published API Version
SERVER_VERSION="1.2.0" # Internal API version!
DATE_FORMAT="%Y-%m-%d %I:%M:%S %p"
START_TIME=datetime.datetime.now().strftime(DATE_FORMAT)
# ID092823.n
MODEL_REGISTRY_FNAME="model_registry.json"

# ### Global Vars ###
reqs_success = 0 # No. of scoring requests completed successfully
reqs_fail = 0 # No. of scoring requests which failed eg., due to incorrect data
uploads_success = 0 # No. of completed model uploads 
uploads_fail = 0 # No. of failed model uploads 
api_endpoint = "/api/" + API_VERSION # API Endpoint/Route
context_path = '/' + os.getenv('TARGET_ENV') + "/" + os.getenv('CONDA_HOME')
server_uuid = str(uuid.uuid4()) # ID091023.n; Generate a unique id for this server instance
sidecar_uuid = None # ID093023.n; The sidecar container's uuid

model_cache = [] # Model metadata cache. Stores loaded model artifact metadata in an Array/List.

# ### Inner Classes ###
#ID091023.sn
class UploadItem(BaseModel):
    model_display_name: str
    namespace: str
    bucket_name: str
    artifact_name: str
#ID091023.sn

# ID100623.sn
class OperationStatus(Enum):
    ACCEPTED = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4

class StorageItem(BaseModel):
    namespace: str
    bucket_name: str
    artifact_name: str

class BatchInferScoreRequest(BaseModel):
    ll_model: str
    measure_model: str
    input_storage: StorageItem
    output_storage: StorageItem
    llm_model_params: dict
    measure_model_params: dict
# ID100623.en

class ModelCache:
    def __init__(self, name, ocid):
        self.model_name = name
        self.model_ocid = ocid
        self.inf_calls = 0

    def __str__(self):
        return f"model_name: {self.model_name},model_ocid: {self.model_ocid},inf_calls: {self.inf_calls}"

# ### Module Functions ###
# ID093023.sn
def model_present_in_cache(model_id):
    """
       Returns True if model is present in cache else False
    """
    for entry in model_cache:
        if entry.model_ocid == model_id:
            return True
    return False

def model_present_in_registry(model_id):
    """
       Returns True if model is present in model registry else false
    """
    registry_file = model_directory + MODEL_REGISTRY_FNAME

    if Path(registry_file).is_file():
        with open(registry_file, "r") as reg_file:
            model_registry = json.loads(reg_file.read())
            if model_id in model_registry:
                return True
    else:
        return False

def save_model_in_cache(model_id, **kwargs):
    """
       Save the model in server cache after it has been saved to the registry
    """
    registry_file = model_directory + MODEL_REGISTRY_FNAME

    if "model_name" in kwargs:
        mname = kwargs["model_name"]
        model_cache.append(ModelCache(mname, model_id))
        return

    # Model registry is present, hence proceed to retrieve & cache model
    with open(registry_file, "r") as reg_file:
        model_registry = json.loads(reg_file.read())

        if model_id in model_registry:
            model_name = model_registry[model_id]
            model_cache.append(ModelCache(model_name, model_id))

def save_model_in_registry(model_id, model_name):
    """
       Save the model info. in the registry
    """
    registry_file = model_directory + MODEL_REGISTRY_FNAME

    model_registry = None
    if Path(registry_file).is_file():
        with open(registry_file, "r") as reg_file:
            model_registry = json.loads(reg_file.read())
            model_registry[model_id] = model_name
    else:
        model_registry = { model_id : model_name }

    with open(registry_file, "w") as reg_file:
        reg_str = json.dumps(model_registry)
        reg_file.write(reg_str)

def remove_model_from_registry(model_id):
    """
       Remove the model info. (denoted by model_id) from model registry
    """
    registry_file = model_directory + MODEL_REGISTRY_FNAME
    model_registry = None
    with open(registry_file, "r") as reg_file:
        model_registry = json.loads(reg_file.read())
    
    del model_registry[model_id]
        
    if bool(model_registry):
        with open(registry_file, "w") as reg_file:
            reg_str = json.dumps(model_registry)
            reg_file.write(reg_str)
    else:
        os.remove(registry_file)

def remove_model_from_cache(model_id):
    """
       Remove model info. from server cache
    """
    model_cache[:] = [model for model in model_cache if not model.model_ocid == model_id]

# ID093023.en

# ID090423.sn

def load_models_in_cache():
    """
      Loads the metadata for models present in './models' dir into the cache. This method is called once when the server is booting up.
    """
 
    dir = model_directory

    # Create the model directory
    if ( not os.path.exists(dir) ):
        os.makedirs(dir)
        logger.info(f"load_models_in_cache(): Models parent directory [{dir}] created.")

        return
    else:
        # If there are any residual 'temp' directories, delete them!
        for temp_dir in glob.glob(dir + "temp_*"):
            shutil.rmtree(temp_dir)
            logger.info("load_models_in_cache(): Deleted temp model directory [{temp_dir}]")

        # Read the model names (id's) and load into internal cache.
        model_names = [ name for name in os.listdir(dir) if os.path.isdir(os.path.join(dir, name)) ]

    # ID092823.sn
    # Check if the model registry file exists
    if not os.path.isfile(dir + MODEL_REGISTRY_FNAME):
        logger.warn(f"load_models_in_cache(): Registry file [{dir + MODEL_REGISTRY_FNAME}] not present in model directory.  Hence no models will be loaded!!")
        return
    else:
        logger.info(f"load_models_in_cache(): Registry file [{dir + MODEL_REGISTRY_FNAME}] present in model directory")
    
    # Read the model registry file
    model_registry = None
    try:
        f = open(model_directory + MODEL_REGISTRY_FNAME, "r")
        model_registry = json.loads(f.read())
        f.close()
        logger.info(f"load_models_in_cache(): Model registry file contents: {model_registry}")
    except Exception as e:
        logger.error(f"load_models_in_cache(): Error reading model registry file: {e}")
        return
    # ID092823.sn

    logger.info(f"load_models_in_cache(): Reading models from directory:{dir}")
    for mname in model_names:
        # ID092823.n Only load models that are present in the registry, with the same name!
        if mname in model_registry:
            dname = model_registry[mname]
            model_cache.append(ModelCache(dname, mname))
            logger.info(f"load_models_in_cache(): Cached model-id:{mname}, display-name:{dname}")
        else:
            # Delete the models that are not present in the model registry!
            # Delete the model directory contents 
            try:
                shutil.rmtree(os.path.join(dir, mname))
                logger.info(f"load_models_in_cache(): Model-id:{mname} artifact directory removed as it is not present in model registry")
            except Exception as e:
                logger.warn(f"load_models_in_cache(): Directory: {mname} could not be deleted!")

#ID090423.en

#ID100423.sn

def get_instance_info():
    ins_info = {
         "__server_info__": {
           "id": server_uuid[:6],
           "version": SERVER_VERSION,
           "endpoint": api_endpoint + context_path,
           "server_root": os.getcwd(),
           "model_directory": model_directory,
           "service_directory": services_directory,
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
           "uploads_completed": uploads_success,
           "uploads_failed": uploads_fail,
           "scored_requests": reqs_success,
           "failed_requests": reqs_fail
         },
         "model_info": model_cache
    }

    return ins_info

def get_srv_instances_info(instance_list):
    """
    Get runtime info. from each server instance that are part of server deployment
    """

    k8s_api_server = "https://kubernetes.default.svc"
    svc_account = "/var/run/secrets/kubernetes.io/serviceaccount"
    namespace = os.getenv("POD_NAMESPACE")
    deployment = os.getenv("DEPLOYMENT_NAME")

    try:
        with open(svc_account + "/token", "r") as token_f:
            access_token = token_f.read()

        oke_url = f"{k8s_api_server}/api/v1/namespaces/{namespace}/endpoints/{deployment}"
        response = requests.get(oke_url, headers={'Authorization': 'Bearer {}'.format(access_token)}, verify=f"{svc_account}/ca.crt")
        r_json = response.json()
        s_subsets = r_json["subsets"]
        response.close()

        t_pod_ip = os.getenv("POD_IP")
        for subset in s_subsets:
            addrs = subset["addresses"]
            for addr in addrs:
                pod_ip = addr["ip"]
                if pod_ip != t_pod_ip:
                    logger.info(f"get_srv_instances_info(): Node-Name:{addr['nodeName']}, Pod-IP:{pod_ip}, Pod-Name:{addr['targetRef']['name']}")
                
                    srv_url = f"http://{pod_ip}:{server_port}{api_endpoint}{context_path}/instanceinfo/"
                    resp = requests.get(srv_url)
                    instance_list.append(resp.json())
                    resp.close()
            break
    except Exception as e:
        traceback.print_exc()
        logger.error(f"get_srv_instances_info(): Encountered exception {e}")

    return instance_list

#ID100423.en

#ID100623.sn
def create_service_resources():
    """
    Create the pre-requisite resources for enabled services
    """

    # Loop thru the services dict and create respective service directories
    for svc in load_services:
        # Create the services parent directory if it doesn't exist
        svc_dir = services_directory + load_services[svc] + "/"
        if ( not os.path.exists(svc_dir) ):
            os.makedirs(svc_dir)
            logger.info(f"create_service_resources(): Parent directory [{svc_dir}] for service [{svc}] created.")
        else:
            logger.info(f"create_service_resources(): Parent directory [{svc_dir}] for service [{svc}] already exists.")
        
def object_to_dict(obj):
    """
    This recursive function converts a class object to a dictionary
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
#ID100623.en

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

# ### Initialize Inference Server ###
# ID090423.sn
# Models will be stored in a model directory within server root
model_directory = os.getcwd() + "/store/models/"

load_models_in_cache()
# ID090423.en

# ID100623.sn
services_directory = os.getcwd() + "/store/services/"

load_services = {
    "score_models" : "scoring"
}

create_service_resources()
# ID100623.sn

# ID101423.sn
# Set the resource manager service host
rm_service = os.getenv("MIS_RES_MGR_SERVICE_NAME", default=f"mis-res-mgr.{os.getenv('POD_NAMESPACE')}")
rm_service_port = os.getenv("MIS_RES_MGR_SERVICE_PORT", default=80)
# ID101423.en

# ### Configure FastAPI Server ###

api_description=f"""
<hr>

**Server Version:** {SERVER_VERSION}

**Environment:** {os.getenv('TARGET_ENV')}

**Conda Env./Slug Name:** {os.getenv('CONDA_HOME')}

**API Endpoint:** {api_endpoint}{context_path}/

### Description
A scalable inference (API) server which exposes endpoints for the following
<ul>
    <li>Loading Machine Learning and Large Language models into the inference server's model store. These models can be loaded either from OCI Data Science Model catalog or from OCI Object Store</li>
    <li>Performing inferences using model artifacts stored within the server's model store</li>
    <li>Assessing the performance/accuracy of model predictions using a scoring model</li>
</ul>

### Important Notes
<ul>
    <li>Large Language models (size >= 6GB) should be uploaded to the server from OCI Object Storage.</li>
</ul>
<hr>

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
        "name": "Upload LLM",
        "description": "**Upload** a large language model artifact (Zip file) from OCI Object Storage bucket to the Inference Server"
    },
    {
        "name": "Get Model Info.",
        "description": "**Get** a model's metadata from OCI Data Science Model Catalog"
    },
    {
        "name": "List Models",
        "description": "**List** model artifacts registered in a OCI Data Science Model Catalog"
    },
    {
        "name": "Predict Outcomes",
        "description": "Use inference data to run **predictions** against a trained machine learning (ML) model.  Alternatively, use a large language model (LLM) to recognize, vectorize, summarize, translate, predict, and generate content using large datasets."
    },
    {
        "name": "Run Batch Inferences And Score Results",
        "description": "Run batch inferences on a large data set and score results"
    },
    {
        "name": "Get Inference Job Details",
        "description": "Get async inference job details"
    },
    {
        "name": "Remove Model",
        "description": "**Remove** a ML model from Inference Server"
    },
    {
        "name": "Model Server Instance Info.",
        "description": "Get model server instance information"
    },
    {
        "name": "Model Server Info.",
        "description": "An inference server can be comprised of multiple model server instances.  This method retrieves the model server information"
    },
    {
        "name": "Register Large Language Model",
        "description": "Register a LLM with this inference server"
    },
    {
        "name": "Register Sidecar",
        "description": "Register the sidecar instance (model loader)"
    },
    {
        "name": "Health Check",
        "description": "Liveness probe - Check if the API Server is up and runnning (alive)"
    }
]

# Initialize the FastAPI Uvicorn Server
app = FastAPI(
    title="A scalable Model Inference Server for OCI Data Science",
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
    openapi_url=api_endpoint + context_path + "/openapi.json",
    docs_url=api_endpoint + context_path + "/docs",
    redoc_url=None,
    openapi_tags=tags_metadata
)

# ### Model Server API ###
@app.get(api_endpoint + context_path + "/healthcheck/", tags=["Health Check"], status_code=200)
#async def health_check(probe_type: str | None = Header(default=None)): # Works > Py 3.10+
async def health_check(probe_type: str = Header(default=None)): # =Py 3.8/3.9
    """Run a health check on this server instance

    HTTP Headers
    ------------
    probe-type : (str, optional)

        Any string value eg., readiness, liveness ...

    Returns
    -------
    result : dict

        A dictionary containing current health status of Model Inference Server

    """

    results = {
         "probe_type": probe_type,
         "oci_connectivity": "OK",
         "time": datetime.datetime.now().strftime(DATE_FORMAT),
         "operation": "health_check",
         "status": OperationStatus.COMPLETED.name
    }
    logger.info(f"health_check(): Probe={probe_type}")
    return results

#ID100423.sn

@app.get(api_endpoint + context_path + "/instanceinfo/", tags=["Model Server Instance Info."], status_code=200)
async def instance_info():
    """Retrieves this server's instance info.

    Returns
    -------
    result : dict

        A dictionary containing the inference server instance info.
    """

    return get_instance_info()
    
#ID100423.en

@app.get(api_endpoint + context_path + "/serverinfo/", tags=["Model Server Info."], status_code=200)
async def server_info():
    """Retrieves the server instance(s) runtime info.

    Returns
    -------
    result : dict

        A dictionary containing the inference server info.

    """

    #IMP: Set the host_type in the server deployment file!!
    host_type = os.getenv("PLATFORM_NAME")
    logger.info(f"server_info(): Host type={host_type}")

    if host_type and (host_type == 'Kubernetes' or host_type == 'OKE'):
        scale_type = "Auto"
    else:
        scale_type = "Manual"

    server_common_info = {
         "conda_environment": os.getenv("CONDA_HOME"),
         "python_version": sys.version,
         "web_server": "Uvicorn {ws_version}".format(ws_version = version('uvicorn')),
         "framework": "FastAPI {frm_version}".format(frm_version = version('fastapi')),
         "start_time": START_TIME,
         "platform": {
           "host_type": os.getenv("PLATFORM_NAME"),
           "compute_type": os.getenv("COMPUTE_TYPE"),
           "scaling": scale_type,
           "environment": os.getenv("TARGET_ENV")
         },
         "build_info": {
           "commit_hash": os.getenv("DEVOPS_COMMIT_ID"),
           "pipeline_ocid": os.getenv("DEVOPS_PIPELINE_ID"),
           "build_run_ocid": os.getenv("DEVOPS_BUILD_ID")
         },
         "deployment_info": {
           "pipeline_ocid": os.getenv("DEPLOYMENT_PIPELINE_OCID"),
           "deployment_name": os.getenv("DEPLOYMENT_NAME"),
           "deployment_id": os.getenv("DEPLOYMENT_ID")
         },
         "oci_client_info": {
           "profile": oci_cli_profile,
           "log_requests": oci_config.get('log_requests'),
           "tenancy": oci_config.get('tenancy'),
           "region": oci_config.get('region'),
           "key_file": oci_config.get('key_file')
         }
    }

    instance_list = []
    instance_list.append(get_instance_info())

    if scale_type == "Auto":
        instance_list = get_srv_instances_info(instance_list)
    server_common_info["server_instances"] = instance_list

    return server_common_info

@app.get(api_endpoint + context_path + "/loadmodel/{model_id}", tags=["Load Model"], status_code=200)
async def load_model(model_id):
    """Loads the ML model artifacts from OCI Data Science.  Call this function to pre-load the model into the Inference Server registry and cache.

    Parameters
    ----------
    model_id : str

        OCI Data Science Model OCID

    Raises
    ------
    Exception : HTTPException

        An exception is thrown when 

          - Model's metadata cannot be retrieved
          - Model is in 'In-Active' state
          - Model Slug name is NOT the same as this server instance's Conda env
          - Model's artifacts cannot be fetched from model catalog

    Returns
    -------
    result : dict

        A dictionary containing model load status

    """
    global uploads_success
    global uploads_fail

    # 1. Check model_cache. If model is already cached return
    if model_present_in_cache(model_id):
        logger.info(f"load_model(): Model ocid {model_id} already cached in server")
        err_detail = {
            "err_message": "Unable to process request as it conflicts with server's current state",
            "err_detail": f"Model [{model_id}] is already loaded and cached in server!"
        }
        # return 409: Request conflicts with server's current state 
        raise HTTPException(status_code=409, detail=err_detail)

    # 2. Check model registry.  If model was loaded by another server instance, load it into the cache of this instance and return
    if model_present_in_registry(model_id):
        save_model_in_cache(model_id)
        logger.info(f"load_model(): Model ocid {model_id} already cached in server")
        err_detail = {
            "err_message": "Unable to process request as it conflicts with server's current state",
            "err_detail": f"Model [{model_id}] is already loaded and cached in server!"
        }
        # return 409: Request conflicts with server's current state 
        raise HTTPException(status_code=409, detail=err_detail)

    # 3. Download the model artifact file & save it into the model id folder

    # Retrieve model metadata from OCI DS
    get_model_response = None
    try:
        get_model_response = data_science_client.get_model(model_id=model_id)
    except Exception as e:
        uploads_fail += 1
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": f"Encountered exception while fetching metadata for model [{model_id}].  Unable to process request.",
            "err_detail": str(e)
        }
        # return 500: Internal server error
        raise HTTPException(status_code=500, detail=err_detail)

    model_obj = get_model_response.data
    model_name = model_obj.display_name

    # Check to see if the model's lifecycle state is 'Active'
    if model_obj.lifecycle_state != oci.data_science.models.Model.LIFECYCLE_STATE_ACTIVE:
        err_detail = {
            "err_message": "Reactivate the model and then try loading it",
            "err_detail": f"Bad Request. Model : [{model_name}:{model_id}] is not in Active state"
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

    # Check if conda env matches model slug name if not raise an exception
    slug_name = None
    for mdata in model_obj.custom_metadata_list:
        # ID090723.o
        # if ( mdata.category == "Training Environment" and mdata.key == "SlugName" ):
        # ID090723.n
        if ( mdata.category == "training environment" and mdata.key == "SlugName" ):
            slug_name = mdata.value
            break

    # NOTE: slug_name should not be empty. Should be set to the conda env name!!

    logger.info(f"load_model(): SlugName from model metadata: {slug_name}")
    if slug_name != os.getenv('CONDA_HOME'):
        err_detail = {
            "err_message": f"Bad Request. Model Slug name: [{slug_name}] does not match Conda environment: [{os.getenv('CONDA_HOME')}]",
            "err_detail": "Check the Slug name in the model taxonomy. The slug name should match the Conda environment of the model server instance. You can check the Conda environment of this model server instance by invoking the '/serverinfo/' endpoint."
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

    st_time = time.time();
    try:
        # Fetch the model artifacts
        get_model_artifact_content_response = data_science_client.get_model_artifact_content(model_id=model_id, opc_request_id=os.getenv("POD_NAME"))
    except Exception as e:
        uploads_fail += 1
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": f"Encountered exception while fetching artifact for model [{model_id}]. Unable to process request.",
            "err_detail": str(e)
        }
        # return 500: Internal server error
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

    # Check if model directory doesn't exist, create it
    zfile_path =  model_directory + model_id
    if not os.path.isdir(zfile_path):
        os.makedirs(zfile_path)
        logger.debug("load_model(): Created model artifact directory")

    # Unzip the model artifact file into the model id folder -
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(zfile_path)
    logger.debug(f"load_model(): Extracted model artifacts from zip file into directory: {zfile_path}")

    # Delete the artifact zip file
    os.remove(artifact_file)
    logger.debug(f"load_model(): Deleted model artifact zip file: {artifact_file}")
    
    # 4. Save model info. in model registry file
    save_model_in_registry(model_id, model_name)

    # 5. Update server's model cache
    save_model_in_cache(model_id, model_name=model_name)

    uploads_success += 1

    en_time = time.time() - st_time
    resp_msg = {
        "model_name": model_name,
        "model_id": model_id,
        "loadtime" : en_time,
        "operation": "load_model",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg

@app.get(api_endpoint + context_path + "/getmodelinfo/{model_id}", tags=["Get Model Info."], status_code=200)
async def get_model_metadata(model_id):
    """Retrieves the model metadata

    Parameters
    ----------
    model_id : str

        Unique model ID or OCI Data Science Model OCID

    Returns
    -------
    result: dict

        The model artifact's runtime info. If the model is registered in OCI Data Science model catalog, then content of 'runtime.yaml' file will be returned.

    """

    metadata = ''
    if model_id.startswith("ocid"):
        file_path = model_directory + model_id + '/runtime.yaml'
        logger.debug(f"get_model_metadata(): File Path={file_path}")
    
        # Load the model artifacts if model runtime file is not present
        if not os.path.isfile(file_path):
            model_status = await load_model(model_id)
            logger.debug(f"get_model_metadata(): Load model status: {model_status['status']}")

        with open(file_path, 'r') as f:
            metadata = yaml.safe_load(f)
    else:
        # Load model from cache
        for entry in model_cache:
            if entry.model_ocid == model_id:
                metadata = object_to_dict(entry)
                break

    return metadata

@app.get(api_endpoint + context_path + "/listmodels/", tags=["List Models"], status_code=200)
async def list_models(compartment_id: str, project_id: str, no_of_models: int=400):
    """Retrieves the models for a given OCI Compartment and Data Science Project.

    Parameters
    ----------
    compartment_id : str

        OCI Compartment OCID

    project_id : str

        OCI Data Science Project OCID

    Raises
    ------
    Exception : HTTPException

        Any exception encountered while fetching the models is returned

    Returns
    -------
    result : dict

        A dictionary containing a list of model dictionaries - ocid's,name,state ...

    """

    logger.info(f"list_models(): Compartment ocid=[{compartment_id}, Project ocid=[{project_id}]")

    try:
        # Use DS API to fetch 'Active' model artifacts
        list_models_response = data_science_client.list_models(
            compartment_id=compartment_id,
            project_id=project_id,
            lifecycle_state=oci.data_science.models.Model.LIFECYCLE_STATE_ACTIVE,
            limit=no_of_models)
    except Exception as e:
        logger.error(f"load_model(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Encountered exception while fetching model list data. Unable to process request.",
            "err_detail": str(e)
        }
        # return 500: Internal Server Error
        raise HTTPException(status_code=500, detail=err_detail)

    model_list = list_models_response.data
    logger.info(f"list_models():\n{model_list}")

    return model_list

@app.post(api_endpoint + context_path + "/infer/", tags=["Predict Outcomes"], status_code=200)
#async def score(model_id: str, request: Request): (also works!)
async def infer_data(model_id: str, data: dict = Body()):
# async def infer_data(model_id: str, item: dict | None = None, file: UploadFile | None = None):
    """Infers the data sent in the request (payload) against the respective model and returns the model output.

    Parameters
    ----------
    model_id : str

        A model can be an ML, Large language or a scoring model. Model ID should be one of the following - 

          - OCI Data Science Model OCID or 
          - Large language model or scoring model id

    data : dict

        Inference data dictionary (JSON) structure is detailed below.
     
          - prompts : An array of input prompts.  Each prompt should not exceed the model's max context length.
          - params : A dictionary of key/value pairs to be passed to the model
          - references (Optional) : An array of desired/expected outputs
          - predictions (Optional) : An array of results output by the machine learning or large language model

    Raises
    ------
    HTTPException:

        Any exception encountered during inferencing is returned

    Returns
    -------
    dict:

        A dictionary containing inference results

    """

    # Get predictions and explanations for each data point
    # data = await request.json(); # returns body as dictionary
    # data = await request.body(); # returns body as string
    global reqs_success
    global reqs_fail

    if not data:
        reqs_fail += 1
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail="Bad Request. No data sent in the request body!")
    logger.info(f"infer_data(): Inference Inp. Data: {data}")

    file_path = model_directory + model_id + '/score.py'
    if not os.path.isfile(file_path):
        logger.info(f"infer_data(): Artifact directory for Model ocid {model_id} not found!")
        # Imp: Remove stale model from cache if present!
        remove_model_from_cache(model_id)

        err_detail = {
            "err_message": "Model artifact directory not found. Unable to process request.",
            "err_detail": f"Artifact directory for Model [{model_id}] not found. Load the model artifacts into the model server and then try again."
        }
        # return 400: Bad request
        raise HTTPException(status_code=400, detail=err_detail)

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
        logger.error(f"infer_data(): Encountered exception: {e}")
        err_detail = {
            "err_message": "Encountered an exception.  Unable to process the request. Refer to the error message (/server logs) for details.",
            "err_detail": str(e)
        }
        # return 422: Unprocessable Entity
        raise HTTPException(status_code=422, detail=err_detail)

    results_data = dict()
    results_data["data"] = results
    results_data["server_id"] = server_uuid[:6]
    results_data["inference_time"] = en_time
    results_data["operation"] = "infer_data"
    results_data["status"] = OperationStatus.COMPLETED.name
    logger.debug(f"infer_data(): Inference Out. Data: {results_data}")

    reqs_success += 1
    # Update no. of model inferences in cache
    model_found = False
    for meta in model_cache:
        if meta.model_ocid == model_id:
            meta.inf_calls += 1
            model_found = True
            break

    if not model_found:
        save_model_in_cache(model_id)
        for meta in model_cache:
            if meta.model_ocid == model_id:
                meta.inf_calls += 1
                break

    return results_data

# ID091023.sn

@app.post(api_endpoint + context_path + "/uploadllm/", tags=["Upload LLM"], status_code=201)
async def upload_large_language_model(item: UploadItem):

    """Upload a large language model (artifacts) to the inference server. 

    Parameters
    ----------
    item : UploadItem

        A json string that specifies the location of the LLM (zip) file on OCI Object Storage

    Raises
    -------
    Exception : HTTPException

        An exception is thrown if the server received a dulicate request for uploading the same model (identified by model name)

    Returns
    -------
    result : dict

        A dictionary containing model upload status

    """

    artifact_name = item.artifact_name
    if '.zip' not in artifact_name:
        err_detail = {
            "err_message": "Unable to process request",
            "err_detail": f"Model artifact file [{artifact_name}] should be a '.zip' file"
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)
    
    model_id = artifact_name[:artifact_name.index(".zip")]
    if os.path.isdir(f"{model_directory}{model_id}"):
        err_detail = {
            "err_message": "Delete the model first before reloading the model artifacts",
            "err_detail": f"Artifacts directory for model: [{model_id}], already exists"
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)

    # newpath = model_directory + "/temp_" + item.model_display_name
    newpath = model_directory + "/temp_" + model_id
    if not os.path.exists(newpath):
        os.makedirs(newpath)

        callback_uri = f"http://localhost:{server_port}{api_endpoint}{context_path}/registerllm/"
        # Create the request object dict
        req_obj = {
            "model_name": item.model_display_name,
            "model_id": model_id,
            "namespace": item.namespace,
            "bucket_name": item.bucket_name,
            "artifact_name": item.artifact_name,
            "server_env": os.getenv('CONDA_HOME'),
            "server_secret": server_uuid,
            "sidecar_secret": sidecar_uuid,
            "callback_uri": callback_uri
        }
        # Save the request dict as json
        with open(newpath + "/model_loc.json", "w") as outfile:
            json.dump(req_obj, outfile)
    else:
        err_detail = {
            "err_message": "Unable to process request",
            "err_detail": f"Previous upload request for model [{model_id}] is currently being processed"
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)

    resp_dict = {
        "uploaded_file": artifact_name,
        "model_name": item.model_display_name,
        "model_id": model_id,
        "request_time": START_TIME,
        "operation": "upload_large_language_model",
        "status": OperationStatus.ACCEPTED.name
    }

    return resp_dict

@app.post(api_endpoint + context_path + "/registerllm/", tags=["Register Large Language Model"], status_code=200)
async def register_llm(
    model_name: str, 
    model_id: str, 
    status: str, 
    secret: str):

    """This is an internal endpoint and not accessible for API consumers"""

    global uploads_success
    global uploads_fail

    if secret == server_uuid:
        if status == OperationStatus.COMPLETED.name:
            uploads_success += 1
            save_model_in_registry(model_id,model_name)
            save_model_in_cache(model_id,model_name=model_name)
            logger.info(f"register_llm(): Model ID: {model_id} registered in internal cache")
        elif status == OperationStatus.FAILED.name:
            uploads_fail += 1
            logger.info(f"register_llm(): Model ID: {model_id} upload failed")
    else:
        err_detail = {
            "err_message": "Not authorized",
            "err_detail": "This is an internal endpoint and not accessible by users!"
        }
        # return 401: Unauthorized
        raise HTTPException(status_code=401, detail=err_detail)

    resp_dict = {
        "message": f"Server context for Model: [{model_id}] updated",
        "operation": "register_llm",
        "status": OperationStatus.COMPLETED.name
    }
    return resp_dict

# ID091023.en

# ID093023.sn

@app.post(api_endpoint + context_path + "/registersc/", tags=["Register Sidecar"], status_code=200)
async def register_sidecar(api_secret: str, sidecar_id: str):

    """This is an internal endpoint and not accessible for API consumers"""

    global sidecar_uuid

    if api_secret == "oci-mmis-api-oct02":
        sidecar_uuid = sidecar_id
    else:
        err_detail = {
            "err_message": "Not authorized",
            "err_detail": "This is an internal endpoint and not accessible by users!"
        }
        # return 401: Unauthorized
        raise HTTPException(status_code=401, detail=err_detail)
        
    resp_dict = {
        "message": f"Sidecar instance [{sidecar_uuid}] registration was successful",
        "operation": "register_sidecar",
        "status": OperationStatus.COMPLETED.name
    }
    return resp_dict

# ID093023.sn

@app.post(api_endpoint + context_path + "/uploadmodel/", tags=["Upload Model"], status_code=201)
async def upload_model(file: UploadFile, model_name: str = Form()):
    """Upload model artifacts to the inference server.  Model artifacts will be stored in the server's registry (persistent store).

    Parameters
    ----------
    model_name : str

        Unique model name.

    file : file object

        Zipped archive file containing model artifacts. The zip file name will be used to uniquely identify the model (== Model ID).

    Raises
    -------
    Exception : HTTPException

        An exception is thrown when

          - Uploaded file is not a zip file
          - 'score.py' or 'runtime.yaml' is not present in the model artifact directory (after zip file is exploded)
          - Value of attribute 'inference_env_slug' in runtime.yaml is not the same as this server's conda env

    Returns
    -------
    result : dict

        A dictionary containing file upload status

    """
    global uploads_success
    global uploads_fail

    artifact_file = file.filename
    logger.info(f"upload_model(): File sent in upload: {artifact_file}")

    if not artifact_file.endswith(".zip"):
        err_detail = {
            "err_message": "Unable to process the request",
            "err_detail": f"Uploaded model file [{artifact_file}] is not a zip file. Only zipped model artifact files (.zip) are accepted!"
        }
        # return 415: Unsupported media type
        raise HTTPException(status_code=415, detail=err_detail)
    # model_id = artifact_file[:artifact_file.rindex(".zip")]
    model_id = artifact_file[:artifact_file.index(".zip")]

    # 1. Check model_cache. If model is already cached return
    if model_present_in_cache(model_id):
        logger.info(f"upload_model(): Model ocid {model_id} already cached in server")
        err_detail = {
            "err_message": "Unable to process request as it conflicts with server's current state",
            "err_detail": f"Model {model_id} is already loaded and cached in server!"
        }
        # return 409: Request conflicts with server's current state 
        raise HTTPException(status_code=409, detail=err_detail)

    # 2. Check model registry.  If model was loaded by another server instance, load it into the cache of this instance and return
    if model_present_in_registry(model_id):
        save_model_in_cache(model_id)
        logger.info(f"upload_model(): Model ocid {model_id} already cached in server")
        err_detail = {
            "err_message": "Unable to process request as it conflicts with server's current state",
            "err_detail": f"Model {model_id} is already loaded and cached in server!"
        }
        # return 409: Request conflicts with server's current state 
        raise HTTPException(status_code=409, detail=err_detail)

    file_content_type = file.content_type

    # 3. Save model artifacts into the model repository

    # Create the model artifact directory
    # zfile_path =  "./" + model_id
    zfile_path =  model_directory + model_id
    if not os.path.exists(zfile_path):
        os.makedirs(zfile_path)
        logger.info(f"upload_model(): Created model artifact directory {zfile_path}")

    st_time = time.time();
    # ID090223.sn
    try:
        async with aiofiles.open(artifact_file, 'wb') as f:
            while contents := await file.read(1024 * 1024):
                await f.write(contents)
    except Exception as e:
        uploads_fail += 1
        logger.error(f"upload_model(): Encountered exception: {e}")
        print(traceback.format_exc())
        err_detail = {
            "err_message": "Encountered error while uploading the model artifact file! Unable to process request.",
            "err_detail": str(e)
        }
        # return 500: Internal server error
        raise HTTPException(status_code=500, detail=err_detail)
    finally:
        await file.close()
    # ID090223.en

    # Unzip the model artifact file into the model id folder -
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(zfile_path)
        logger.info(f"upload_model(): Extracted model artifacts from uploaded zip file into directory: {zfile_path}")

    # Check to see if the model directory contains a 'score.py' and 
    # 'runtime.yaml' file
    score_file = Path("{}/score.py".format(zfile_path))
    rtime_file = Path("{}/runtime.yaml".format(zfile_path))
    if not score_file.is_file() or not rtime_file.is_file():
        shutil.rmtree(zfile_path)
        os.remove(artifact_file)
        err_detail = {
            "err_message": "Unable to process the request",
            "err_detail": "Zip file does not contain 'score.py' and/or 'runtime.yaml'!  These are required files.  Zip file contents could be corrupted!"
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)
        
    # Read the 'runtime.yaml' and check the inference_env_slug value. It should
    # match the conda env / runtime of this server.
    with open(rtime_file, 'r') as f:
        runtime_info = yaml.safe_load(f)
    
    slug_name = ""
    try:
        slug_name = runtime_info['MODEL_DEPLOYMENT']['INFERENCE_CONDA_ENV']['INFERENCE_ENV_SLUG']
        logger.info(f"upload_model(): INFERENCE_ENV_SLUG attribute value in runtime.yaml: {slug_name}")
    except Exception as e:
        logger.info(f"upload_model(): Encountered exception: {e}")
        shutil.rmtree(zfile_path)
        os.remove(artifact_file)
        err_detail = {
            "err_message": "INFERENCE_ENV_SLUG attribute is missing in 'runtime.yaml' file",
            "err_detail": str(e)
        }
        # return 422: Unprocessable content
        raise HTTPException(status_code=422, detail=err_detail)

    if slug_name != os.getenv('CONDA_HOME'):
        shutil.rmtree(zfile_path)
        os.remove(artifact_file)
        err_detail = {
            "err_message": f"Bad Request. Model Slug name: [{slug_name}] does not match Conda environment: [{os.getenv('CONDA_HOME')}]",
            "err_detail": "The 'INFERENCE_ENV_SLUG' value in 'runtime.yaml' file does not match the Conda environment of the model server instance. You can check the Conda environment of this model server instance by invoking the '/serverinfo/' endpoint."
        }
        # return 400: Bad Request
        raise HTTPException(status_code=400, detail=err_detail)

    # Delete the artifact / zip file - save space (server home directory)
    os.remove(artifact_file)

    # 4. Save model info. in model registry file
    save_model_in_registry(model_id, model_name)

    # 5. Update server's model cache
    save_model_in_cache(model_id, model_name=model_name)
    
    uploads_success += 1

    en_time = time.time() - st_time
    resp_msg = {
        "uploaded_file": artifact_file,
        "content_type": file_content_type,
        "slug_name": slug_name,
        "model_name": model_name,
        "model_ocid": model_id,
        "loadtime": en_time,
        "operation": "upload_model",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg

@app.delete(api_endpoint + context_path + "/removemodel/{model_id}", tags=["Remove Model"], status_code=200)
async def remove_model(model_id: str):
    """Removes the ML model artifacts from Inference Server.

    Parameters
    ----------
    model_id : str

    One of the following

        - OCI Data Science Model OCID
        - ML / Large language model id (~ Unique Identifier)

    Raises
    ------
    Exception : HTTPException

        An exception is thrown when the model artifact directory is not found

    Returns
    -------
    result : dict

        A dictionary containing the status of delete model operation

    """

    file_path =  model_directory + model_id
    if os.path.isdir(file_path):
        shutil.rmtree(file_path)
        remove_model_from_registry(model_id)
        remove_model_from_cache(model_id)

        logger.info(f"remove_model(): Deleted artifact directory for model ID:{model_id}")
    else:
        err_detail = {
            "err_message": "Unable to process the request",
            "err_detail": f"Model artifact directory for model [{model_id}] not found!"
        }
        # return 404: Not Found
        raise HTTPException(status_code=404, detail=err_detail)
        
    resp_msg = {
        "model_id": model_id,
        "file_path": file_path,
        "operation": "remove_model",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg

#ID100623.sn

@app.post(api_endpoint + context_path + "/infernscore/", tags=["Run Batch Inferences And Score Results"], status_code=201)
async def run_batch_inference_and_score(input: BatchInferScoreRequest):

    """Run batch inferences on a large data set and score the results

    Parameters
    ----------
    input : BatchInferScoreRequest

    A dict (json string) containing the following attributes. Either 'll_model' or 'measurement_model' has to be specified (non-empty).  Both of these attributes cannot be empty.

        - ll_model : (Optional) Unique ID of the large language model. This model must have been uploaded to the model server.
        - measurement_model : (Optional) Name/ID of the measurement model
        - input_storage : StorageItem
          - namespace : OCI Object Storage namespace ID
          - bucket_name : Name of the bucket
          - artifact_name : Name of the file containing the inputs, prompts and expected results
        - output_storage : StorageItem
          - namespace : OCI Object Storage namespace ID
          - bucket_name : Name of the bucket
          - artifact_name (Optional) : Name of the output file where the predictions and results (scores) are to be saved. Default: Input file name with suffix "_output".
        - llm_model_params : A dictionary containing keys and values to be used to configure the behavior of ll model
        - measure_model_params : A dictionary containing keys and values to be used to configure the behavior of measurement model

    Raises
    -------
    Exception : HTTPException

        An exception is thrown if the server is unable to process the request

    Returns
    -------
    result : str

        A unique job ID

    """
    
    request_dict = object_to_dict(input)
   
    # Validate inputs
    llm = request_dict["ll_model"]
    measure_model = request_dict["measure_model"]

    if not llm and not measure_model:
        err_detail = {
            "err_message": "Unable to process the request",
            "err_detail": "One of 'll_model' or 'measure_model' is required!"
        }
        # return 422: Unprocessable Content
        raise HTTPException(status_code=422, detail=err_detail)

    job_id = str(uuid.uuid4())
    request_dict["job_id"] = "ID-" + job_id[:8]
    request_dict["service_name"] = f"{os.getenv('MIS_SERVICE_NAME')}.{os.getenv('POD_NAMESPACE')}"
    request_dict["server_uri"] = f"{api_endpoint}{context_path}/infer/"
    request_dict["server_id"] = server_uuid
    request_dict["job_status"] = OperationStatus.ACCEPTED.name
    request_dict["job_receipt_time"] = START_TIME
    logger.info("run_batch_inference_and_score(): Job Data: \n{}".format(request_dict))

    """
    # Save job request in './services/scoring' directory
    j_req_file = f"{request_dict['job_id']}.json"
    scoring_job_f = f"{services_directory}scoring/{j_req_file}"
    with open(scoring_job_f, "w") as s_file:
        s_file.write(json.dumps(request_dict))
    """

    rm_svc_ep_uri = f"http://{rm_service}:{rm_service_port}/api/v1/create/infer-async"
    logger.info(f"run_batch_inference_and_score(): Resource manager ep-uri: {rm_svc_ep_uri}")
    rm_svc_resp = ""
    try:
        request_json = json.dumps(request_dict)
        resp = requests.post(rm_svc_ep_uri, data=request_json)

        if resp.status_code != requests.codes.created:
            resp.raise_for_status()

        rm_svc_resp = resp.json()
    except Exception as e:
        traceback.print_exc()
        logger.error(f"run_batch_inference_and_score(): Encountered exception {e}")
        err_detail = {
            "err_message": "Encountered exception while calling the resource manager. Unable to process the request",
            "err_detail": str(e)
        }
        # return 500: Internal server error!
        raise HTTPException(status_code=500, detail=err_detail)
    finally:
        resp.close()
    
    resp_msg = {
        "job_id": request_dict["job_id"],
        "operation": "run_batch_inference_and_score",
        "res_mgr_response": rm_svc_resp,
        "status": request_dict["job_status"]
    }

    return resp_msg

@app.get(api_endpoint + context_path + "/getjobdetails/{jobid}", tags=["Get Inference Job Details"], status_code=200)
async def get_inference_job(jobid: str):

    """Retrieve the batch inference job details

    Parameters
    ----------
    jobid : str

        The unique Job ID string

    Raises
    -------
    Exception : HTTPException

        An exception is thrown if the server is unable to process the request

    Returns
    -------
    result : dict

        A dictionary containing batch inference job details

    """

    rm_svc_ep_uri = f"http://{rm_service}:{rm_service_port}/api/v1/getresourceinfo/infer-async"
    logger.info(f"get_inference_job(): Resource manager ep-uri: {rm_svc_ep_uri}")
    try:
        payload = {"resource_id": jobid}
        rm_svc_resp = requests.get(rm_svc_ep_uri, params=payload)
        resp_dict = rm_svc_resp.json()

        # if rm_svc_resp.status_code != requests.codes.ok: # NOT == 200
            # resp.raise_for_status()
        result = resp_dict["job_details"]
    except Exception as e:
        traceback.print_exc()
        logger.error(f"get_inference_job(): Encountered exception {e}")
        err_detail = {
            "err_message": "Resource manager returned an exception. Unable to process the request",
            "err_detail": str(e)
        }
        # return 500: Internal server error!
        raise HTTPException(status_code=500, detail=err_detail)
    finally:
        rm_svc_resp.close()
    
    resp_msg = {
        "details": result,
        "operation": "get_inference_job",
        "status": OperationStatus.COMPLETED.name
    }

    return resp_msg
#ID100623.en
