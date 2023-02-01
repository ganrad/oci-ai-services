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
MAINTAINER Ganesh Radhakrishnan ganrad01@gmail.com

ARG condaurl
ARG condaenv=generalml_p38_cpu_v1

# Create the workdir = /envs
WORKDIR /envs

# Download the ML conda environment (tar file)
RUN curl -X GET $condaurl --output $condaenv.tar

# Create the conda env directory
RUN mkdir $condaenv 

RUN ls -lt

# Unpack the conda env tar file
RUN tar -xvf $condaenv.tar --directory ./$condaenv

# Remove the tar file
RUN rm $condaenv.tar

ENV CONDA_HOME=$condaenv

SHELL ["/bin/bash","-c"]
ENTRYPOINT source /envs/$CONDA_HOME/bin/activate && \
           python -c "import sys; print(sys.version)"

#python -c "import numpy; print('success!')"
