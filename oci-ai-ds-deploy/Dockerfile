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
FROM oraclelinux
MAINTAINER Ganesh Radhakrishnan ganrad01@gmail.com

ARG condaurl
ARG condaenv=generalml_p38_cpu_v1

# Install curl
RUN yum install curl

# Create the workdir = /envs
WORKDIR /envs

# Download and install the ML conda environment
RUN curl -X GET $condaurl --output $condaenv.tar

# Unpack the conda env
RUN mkdir $condaenv && tar -xvf $condaenv.tar -C $condaenv

# Activate the conda env
RUN source activate /envs/$condaenv/bin/activate

# Print the python version
RUN python --version
