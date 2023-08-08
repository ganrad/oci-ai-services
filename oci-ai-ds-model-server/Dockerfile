# -------------------------------------------
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

# -------------------------------------------
# An API server for running inferences against ML models created in OCI Data
# Science.
#
# Description: This dockerfile builds an generic API container image for a) 
# loading ML models trained and registered in OCI Data Science Model Catalog & 
# b) performing inference against the pre-trained models.
# The underlying Web server used is Uvicron and web framework is FastAPI. The 
# API server exposes endpoints for loading OCI ML models and predicting 
# outcomes.
#
# NOTES:
#
# -------------------------------------------
#
# FROM oraclelinux:9
FROM public.ecr.aws/docker/library/oraclelinux:9
LABEL name="OCI Data Science model server"
LABEL version="1.0"
LABEL description="This container image exposes API endpoints for a) Loading pre-trained ML models registered in OCI Data Science Model Catalog and b) Performing inference with live data"
LABEL author="Ganesh Radhakrishnan" email="ganrad01@gmail.com" dated="02-01-2023" license="MIT"

# (Required) OCI Object store PAR URL for downloading the ML conda env. This
# value has to be passed in during container build time.
ARG condaurl

# (Required) Conda environment name
ARG condaenv

# (Required) OCI CLI/SDK config & pem file paths have to passed in during 
# container build time
ARG oci_config_filepath # Path to OCI Client Config file
ARG oci_pem_filepath # Path to OCI Client PEM file

# Container host type.  Can be Kubernetes, OKE, VM Instance ..
ARG host_type=OKE 

# (Optional) DevOps build info.
ARG commit_hash=None #
ARG pipeline_id=None #
ARG build_id=None #

# ### These env variables are included for info. only
ENV DEVOPS_COMMIT_ID=$commit_hash
ENV DEVOPS_PIPELINE_ID=$pipeline_id
ENV DEVOPS_BUILD_ID=$build_id

# ### Following env variables can be overriden by user at run time ###

# OCI Config file location
ENV OCI_CONFIG_FILE_LOCATION=$oci_config_filepath

# Target runtime/platform
ENV PLATFORM_NAME=$host_type

# FastAPI Uvicorn log level - Default info
ENV UVICORN_LOG_LEVEL=info

# (Optional) Uvicorn Server listen port - Default 8000
ENV UVICORN_PORT=8000

# Create the conda environment workdir = /envs
WORKDIR /envs

# Download the ML conda environment (gzip tar file) using OCI Obj. Storage PAR 
# URL
# RUN curl -X GET $condaurl --output $condaenv.tar.gz
RUN curl -X GET "https://get.helm.sh/helm-v3.12.2-linux-amd64.tar.gz" --output $condaenv.tar.gz

# Create the conda env directory
RUN mkdir $condaenv 

# Unpack the conda env tar file
RUN tar -xvzf $condaenv.tar.gz --directory ./$condaenv

# List the contents of conda env directory
RUN ls -lt ./$condaenv

# Remove the downloaded conda env tar file
RUN rm $condaenv.tar.gz

# Set conda home (env variable)
ENV CONDA_HOME=$condaenv

# Create the apps workdir = /apps
WORKDIR /apps

# Copy the API server to the container image
COPY ./requirements.txt .
COPY ./model-server.py .

# Copy the OCI config and pem file to the container image
COPY $oci_config_filepath .
COPY $oci_pem_filepath .

# Listen on port ~ MODEL_SERVER_PORT
EXPOSE $UVICORN_PORT/tcp

# Set the default shell (bash) and then run the model server
SHELL ["/bin/bash","-c"]
ENTRYPOINT source /envs/$CONDA_HOME/bin/activate && \
           pip install -r /apps/requirements.txt && \
           uvicorn model-server:app --host 0.0.0.0 --port $UVICORN_PORT --log-level $UVICORN_LOG_LEVEL
