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
    A side-car server that retrieves ML/LLM model artifacts from OCI Object Storage and makes them available to the model server.

Description:
    A side-car server which periodically monitors a source/request directory and loads corresponding ML/LLM artifacts from OCI Object Storage into the model server's persistent backend. The backend for a single server instance can be an attached block volume device. For multiple server instances, a backend type such as OCI File system service / NFS is required.
    
Author:
    Ganesh Radhakrishnan (ganrad01@gmail.com)
Dated:
    09-11-2023 

Notes:
ID110123: ganrad: Check if model directory is already present before downloading model artifacts. 
"""

import os
import glob
import json
import logging
import requests
import time
import signal
import shutil
import uuid
from pathlib import Path
from zipfile import ZipFile

import oci
import yaml

## Set up global vars

API_VERSION="v1" # This is the API version of the inference server!
WAIT_TIME = 5 # Sleep for 5 seconds
CHUNK_SIZE = 1024 # Bytes to read from the stream
run = True
loop_var = True
model_directory = "./store/models" # Model directory
api_endpoint = "/api/" + API_VERSION # Inference server API Endpoint/Route
context_path = '/' + os.getenv('TARGET_ENV') + "/" + os.getenv('CONDA_HOME')
server_port = os.getenv('SERVER_PORT')
inf_server_uri = f"http://localhost:{server_port}{api_endpoint}{context_path}/"
api_secret = "oci-mmis-api-oct02" # This secret is used to hide the inf. server endpoint from being called by consumers!
sidecar_uuid = str(uuid.uuid4()) # Generate a unique id for this sidecar instance

## Set up logging

# Default log level is INFO. Can be set and injected at container runtime.
loglevel = os.getenv("LOG_LEVEL", default="INFO") # one of DEBUG,INFO,WARNING,ERROR,CRITICAL 
nloglevel = getattr(logging,loglevel.upper(),None) 
if not isinstance(nloglevel, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logger = logging.getLogger('sidecar-server')
logger.setLevel(nloglevel)
    
ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

## Server functions

def print_header(name):
    chars = int(90)
    print("")
    print('#' * chars)
    print("#" + name.center(chars - 2, " ") + "#")
    print('#' * chars)

def getModelConfig(srch_dir: str):
    ret_dir = None

    for file in glob.glob(srch_dir):
        ret_dir = file
        break

    if ret_dir is None:
        return None

    filename = ret_dir + "/model_loc.json"
    if os.path.isfile(filename):
        with open(filename, "r") as f:
            config = json.load(f)
            sc_id = config["sidecar_secret"]
            if sc_id == sidecar_uuid:
                config["temp_dir"] = ret_dir

                # print_header("getModelConfig()")
                logger.info("getModelConfig(): Model upload request:")
                logger.info(config)

                return config
            else:
                return None
    else:
        return None

    return ret_dir

# ID110123.sn

def isModelArtifactDirPresent(model_config):
    mfile_path =  f"{model_directory}/{model_config['model_id']}"
    return os.path.isdir(mfile_path)

# ID110123.en

def downloadModelArtifacts(model_config):
    # print_header("downloadModelArtifacts()")

    # ### Configure OCI client ###
    # OCI Client API config profile.  Can be injected at container runtime.
    oci_cli_profile = os.getenv("OCI_CONFIG_PROFILE",default="DEFAULT") 

    # NOTE: If OCI_CONFIG_FILE_LOCATION env var is not set in the container, an 
    # exception will be thrown.  Server will not start!
    oci_config = oci.config.from_file(file_location=os.environ['OCI_CONFIG_FILE_LOCATION'], profile_name=oci_cli_profile)
    logger.info("downloadModelArtifacts(): Loaded OCI client config file")

    oci_object_store_client = oci.object_storage.ObjectStorageClient(oci_config)
    
    os_object = oci_object_store_client.get_object(
        model_config["namespace"],
        model_config["bucket_name"],
        model_config["artifact_name"]
    )

    filename = f"{model_config['temp_dir']}/{model_config['artifact_name']}"
    file = open(filename, "wb")
    for chunk in os_object.data.raw.stream(CHUNK_SIZE * CHUNK_SIZE, decode_content=False):
        file.write(chunk)
    file.close()
    logger.info(f"downloadModelArtifacts(): Downloaded file: {filename}")

def saveModelArtifacts(model_config):
    # print_header("saveModelArtifacts()")

    mfile_path =  f"{model_directory}/{model_config['model_id']}"
    if not os.path.isdir(mfile_path):
        os.makedirs(mfile_path)
        logger.info(f"saveModelArtifacts(): Created model artifact directory: {mfile_path}")
    else: # This path should not be reached!
        shutil.rmtree(mfile_path)
        os.makedirs(mfile_path)
        logger.info(f"saveModelArtifacts(): Re-created model artifact directory: {mfile_path}")

    # Unzip the model artifact file into the model id folder -
    artifact_file = f"{model_config['temp_dir']}/{model_config['artifact_name']}"
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(mfile_path)
        logger.info(f"saveModelArtifacts(): Extracted model artifacts into directory: {mfile_path}")

    # Delete the temp. directory containing the zip file (save space)
    shutil.rmtree(model_config['temp_dir'])
    logger.info(f"saveModelArtifacts(): Deleted directory: {model_config['temp_dir']}")

    # Check to see if the model directory contains a 'score.py' and 'runtime.yaml' file
    score_file = Path("{}/score.py".format(mfile_path))
    rtime_file = Path("{}/runtime.yaml".format(mfile_path))
    # if not score_file.is_file() or not rtime_file.is_file():
    if not score_file.is_file():
        shutil.rmtree(mfile_path)
        logger.info("saveModelArtifacts(): 'runtime.yaml'/'score.py' not present in model artifact file!")
        return False
 
    """
    # Read the 'runtime.yaml' and check the inference_env_slug value. It should
    # match the conda env / runtime of this server.
    with open(rtime_file, 'r') as f:
        runtime_info = yaml.safe_load(f)

    slug_name = runtime_info['MODEL_DEPLOYMENT']['INFERENCE_CONDA_ENV']['INFERENCE_ENV_SLUG']
    logger.info(f"saveModelArtifacts(): INFERENCE_ENV_SLUG attribute value in runtime.yaml: {slug_name}")

    if slug_name != model_config["server_env"]:
        shutil.rmtree(mfile_path)
        shutil.rmtree(model_config['temp_dir'])
        logger.info(f"saveModelArtifacts(): Slug name of model: {slug_name} doesn't match server conda env: {model_config['server_env']}")
        return False
    """

    return True

def notifyModelServer(model_config):
    # print_header("notifyModelServer()")

    qparam = f"?model_name={model_config['model_name']}&"
    qparam += f"model_id={model_config['model_id']}&"
    qparam += f"status={model_config['status']}&"
    qparam += f"secret={model_config['server_secret']}"

    response = requests.post(model_config["callback_uri"] + qparam)

    data = response.json()
    logger.info(f"notifyModelServer(): Server status code: {response.status_code}")
    response.close()

    logger.info(f"notifyModelServer(): Server response:\n{data}")
    # print('#' * 90)

def registerSidecarContainerWithServer():
    global loop_var

    poll_time = 30 # Wait 30 seconds ~ 1 min. before checking to see if server is up!

    qparam = f"?api_secret={api_secret}&"
    qparam += f"sidecar_id={sidecar_uuid}"

    cpath = "registersc/"

    data = None
    while loop_var:
        try:
            response = requests.post(inf_server_uri + cpath + qparam)
            data = response.json()
            logger.info(f"registerSidecarContainerWithServer(): Server status code: {response.status_code}")
            response.close()

            loop_var = False
            continue
        except Exception as e:
            logger.info(f"registerSidecarContainerWithServer(): API Error: {e}, waiting {poll_time} seconds before retrying")

        # sleep for x seconds
        time.sleep(poll_time)

    logger.info(f"registerSidecarContainerWithServer(): Server response:\n{data}")

def interrupt_signal_handler(signum, frame):
    global run
    global loop_var

    run = False
    loop_var = False

signal.signal(signal.SIGINT, interrupt_signal_handler)
signal.signal(signal.SIGTERM, interrupt_signal_handler)
signal.signal(signal.SIGHUP, interrupt_signal_handler)

def main_loop():
    logger.info(f"main_loop(): Inference Server URI {inf_server_uri}")

    # Register sidecar with inference server
    registerSidecarContainerWithServer()

    while run:
        config_obj = getModelConfig(f"{model_directory}/temp_*")
        if config_obj is None:
            logger.info(f"main_loop(): No model upload request found hence sleeping for {WAIT_TIME} seconds ...")

            # sleep for x seconds
            time.sleep(WAIT_TIME)
        else:
            try:
                if not isModelArtifactDirPresent(config_obj): # ID110123.n
                    downloadModelArtifacts(config_obj)
                    if saveModelArtifacts(config_obj):
                        config_obj['status'] = "COMPLETED"
                        notifyModelServer(config_obj)
                else:
                    shutil.rmtree(config_obj['temp_dir'])
                    logger.info(f"main_loop(): Artifact directory for model [{config_obj['model_id']}] already present.  Nothing to do. Deleted directory: {config_obj['temp_dir']}")
            except Exception as e:
                shutil.rmtree(config_obj['temp_dir'])
                logger.error(f"main_loop(): Encountered exception: {e}")
                logger.warning(f"main_loop(): Unable to process model upload request. Deleted directory: {config_obj['temp_dir']}")
                config_obj['status'] = "FAILED"
                notifyModelServer(config_obj)

if __name__ == "__main__":
    logger.info("Entering main_loop() ....")
    main_loop()
    logger.info("Exited main_loop() ....")
