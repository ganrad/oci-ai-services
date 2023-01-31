#!/usr/bin/env python
# coding: utf-8
# MIT License

# Copyright (c) 2021 HZ-MS-CSA

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

# ### Model Scoring Server for models created using OCI Data Science

import json
import os
import importlib.util
import shutil
from zipfile import ZipFile

import oci
import yaml

# Configure OCI client
config = oci.config.from_file(os.environ['OCI_CONFIG_FILE_LOCATION'])
print("Loaded OCI client file")

# Initialize data science service client with config file
data_science_client = oci.data_science.DataScienceClient(config)

"""
  Loads the ML model artifacts from OCI Data Science.  Call this function to
  pre-load the model into the cache.

  Parameters:
  model_id: OCI Data Science Model OCID
"""
def load_model(model_id):
    # Send the request to service, some parameters are not required, see API
    # doc for more info
    get_model_artifact_content_response = data_science_client.get_model_artifact_content(
    model_id=model_id,
    opc_request_id="mserver-001",
    allow_control_chars=True)

    # Get the data from response
    print(f"Resource URL: {get_model_artifact_content_response.request.url}")
    print(f"Status: {get_model_artifact_content_response.status}")

    print(f"Current working directory: {os.getcwd()}")
    artifact_file = model_id + ".zip"
    # Save the downloaded model artifact zip file in current directory
    with open(artifact_file,'wb') as zfile:
        for chunk in get_model_artifact_content_response.data.raw.stream(1024 * 1024, decode_content=False):
            zfile.write(chunk)
    print(f"Saved model artifact zip file: {artifact_file}")

    # Check if model directory exists; if so delete and recreate it else create it
    zfile_path =  "./" + model_id
    if not os.path.isdir(zfile_path):
        os.makedirs(zfile_path)
        print("Created model artifact directory")
    else:
        shutil.rmtree(zfile_path)
        os.makedirs(zfile_path)
        print("Deleted model artifact directory & recreated it")

    # Unzip the model artifact file into the model id folder -
    with ZipFile(artifact_file,'r') as zfile:
        zfile.extractall(zfile_path)
    print(f"Extracted model artifacts from zip file into directory: {zfile_path}")

    # Delete the artifact zip file
    os.remove(artifact_file)
    print(f"Deleted model artifact zip file: {artifact_file}")

"""
  Retrieves the model metadata

  Parameters:
  model_id: OCI Data Science Model OCID
"""
def get_model_metadata(model_id):
    file_path = './' + model_id + '/runtime.yaml'
    
    # Load the model artifacts if model directory is not present
    if not os.path.isfile(file_path):
        load_model(model_id)

    metadata = ''
    with open(file_path, 'r') as f:
        metadata = yaml.safe_load(f)

    return metadata

"""
  Scores the data points sent in the payload using the respective model.

  Parameters:
  raw_data: Data in the format expected by the model object
  model_id: OCI Data Science Model OCID
"""
def score(raw_data, model_id):
    file_path = './' + model_id + '/score.py'
    
    # Load the model artifacts if model directory is not present
    if not os.path.isfile(file_path):
        load_model(model_id)

    module_name = 'score'

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Get predictions and explanations for each data point
    results = module.predict(raw_data)
    results_data = dict()
    results_data["data"] = results

    return results_data

# ### API

from flask import Flask
from flask_restful import Resource, Api, reqparse
app = Flask(__name__)
api = Api(app)

parser = reqparse.RequestParser()
parser.add_argument('data', location='json')
parser.add_argument('model_id', required=True)

# ### API Resource Handler Classes

class LoadModel(Resource):
    def get(self, model_id):
        load_model(model_id)

        results = { 
            "status": "Model loaded OK"
        }
        return results, 200  # return data with 200 OK

class GetModelMetadata(Resource):
    def get(self, model_id):
        results = get_model_metadata(model_id)
        return results, 200  # return data with 200 OK

class Score(Resource):
    def post(self):
        args = parser.parse_args()
        data = args['data']
        model_id = args['model_id']
        print(f"model_id: {model_id}; data={data}")
        results = score(data, model_id)
        return results, 200  # return data with 200 OK

class HealthCheck(Resource):
    def get(self):
        results = {
            "OCI Connectivity": "OK",
            "HealthStatus": "OK"
        }
        return results, 200

# ### API Resource URIs

api.add_resource(LoadModel, '/loadmodel/<string:model_id>')
api.add_resource(GetModelMetadata, '/getmodelinfo/<string:model_id>')
api.add_resource(Score, '/score')
api.add_resource(HealthCheck, '/healthcheck')

if __name__ == '__main__':
    #app.run(host='0.0.0.0', debug=True, port=8080)
    app.run(host='0.0.0.0', port=8080)
