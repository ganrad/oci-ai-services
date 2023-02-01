# An API server for running inferences against ML models created in OCI Data
# Science
#
# Description: This dockerfile builds an generic API container image.  The API
# server is a Python Flask-RESTful application and exposes an endpoint for
# inferring on OCI ML models and predicting outcomes.
#
# NOTES:
#
#
FROM oraclelinux:9
LABEL name="OCI Data Science model server"
LABEL version="1.0"
LABEL description="A generic model server container image for OCI Data Science"
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

# (Optional) Model Server listen port. Can be overriden by user at build time.
ENV MODEL_SERVER_PORT=5000

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

# Set the default shell (bash) and run the model server
SHELL ["/bin/bash","-c"]
ENTRYPOINT source /envs/$CONDA_HOME/bin/activate && \
           pip install -r /apps/requirements.txt && \
           python /apps/model-server.py
