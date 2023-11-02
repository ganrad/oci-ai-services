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
# An API server for managing model inference server resources
#
# Description: This dockerfile builds an API container image. The application
# container is used for managing the lifecycle (CRUD) of model server resources.
#
# NOTES:
# -------------------------------------------
#
FROM public.ecr.aws/docker/library/oraclelinux:9
LABEL name="Model server resource manager"
LABEL version="1.0"
LABEL description="This container image exposes API endpoints for managing the lifecycle (CRUD) of model server resources"
LABEL author="Ganesh Radhakrishnan" email="ganrad01@gmail.com" dated="10-01-2023" license="MIT"

# Update yum, install curl, git
RUN yum -y update; \
    yum install -y curl; \
    yum install -y git; \
    yum clean all -y

# Install wget
RUN yum install -y wget

# Install python 3
Run yum install -y python3
RUN python3 --version
# Install python3-pip
RUN yum install -y python3-pip
# Install virtualenv
RUN pip install virtualenv

# Set cwd to /penvs
WORKDIR /penvs

# Create a virtual env for running the application
RUN virtualenv py_db_env

# ### Following env variables can be overriden by user at run time ###

# FastAPI Uvicorn log level - Default info
ENV UVICORN_LOG_LEVEL=info

# (Optional) Uvicorn Server listen port - Default 8000
ENV UVICORN_PORT=8000

# PGSQL Host
ENV PGSQL_DB_HOST=localhost

# Create the apps workdir = /apps, /apps/models
WORKDIR /apps
RUN mkdir models
# List the present working directory
RUN pwd

# Copy the API server artifacts to the container image
COPY ./requirements.txt .
COPY ./mis-resource-manager.py .

COPY ./models/*.py ./models
# List the contents of cwd recursively
RUN ls -ltR

# Listen on port ~ Resource manager listen port
EXPOSE $UVICORN_PORT/tcp

# Set the default shell (bash) and then run the resource manager
SHELL ["/bin/bash","-c"]
ENTRYPOINT source /penvs/py_db_env/bin/activate && \
           pip install -r /apps/requirements.txt && \
           uvicorn mis-resource-manager:app --host 0.0.0.0 --port $UVICORN_PORT --log-level $UVICORN_LOG_LEVEL
