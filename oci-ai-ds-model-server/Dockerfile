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

#
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
#
FROM oraclelinux:9
LABEL name="OCI Data Science model server"
LABEL version="1.0"
LABEL description="This container image exposes API endpoints for loading ML models registered in OCI Data Science and performing inference against them"
LABEL author="Ganesh Radhakrishnan" email="ganrad01@gmail.com" dated="02-01-2023" license="MIT"

# (Required) OCI Object store PAR URL for downloading the ML conda env. This
# value has to be passed in during container build time.
ARG condaurl

# (Optional) Conda environment name
ARG condaenv=generalml_p38_cpu_v1

# (Required) OCI CLI/SDK config & pem file paths have to passed in during 
# container build time
ARG oci_config_filepath
ARG oci_pem_filepath

# ### Following env variables can be overriden by user at run time ###

# (Optional) Uvicorn Server listen port.
ENV UVICORN_PORT=8000

# (Optional) FastAPI Uvicorn log level - Default info
ENV UVICORN_LOG_LEVEL=info

# (Optional) Uvicorn workers
ENV UVICORN_WORKERS=1

# (Optional) Uvicorn server concurrency
# ENV UVICORN_CONCURRENCY=

# Create the conda environment workdir = /envs
WORKDIR /envs

# Download the ML conda environment (tar file)
RUN curl -X GET $condaurl --output $condaenv.tar

# Create the conda env directory
RUN mkdir $condaenv 

# Unpack the conda env tar file
RUN tar -xvf $condaenv.tar --directory ./$condaenv

# List the contents of conda env directory
RUN ls -lt ./$condaenv

# Remove the downloaded conda env tar file
RUN rm $condaenv.tar

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
EXPOSE $MODEL_SERVER_PORT/tcp

# Set the default shell (bash) and then run the model server
SHELL ["/bin/bash","-c"]
ENTRYPOINT source /envs/$CONDA_HOME/bin/activate && \
           pip install -r /apps/requirements.txt && \
           uvicorn model-server:app --port $UVICORN_PORT --log-level $UVICORN_LOG_LEVEL --workers $UVICORN_WORKERS