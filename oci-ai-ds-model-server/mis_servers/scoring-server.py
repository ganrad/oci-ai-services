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
A Scoring Server for the model inference server

Description:
A server that 
    - Retrieves scoring job requests from a persistent store (postgres DB)
    - Retrieves data files from an input OCI Object Store bucket
    - Performs inferencing and scoring, and 
    - Publishes the results to an output OCI Object Storage bucket.
   
Author:
    Ganesh Radhakrishnan (ganrad01@gmail.com)
Dated:
    10-20-2023 

Notes:
"""

import os
import glob
import json
import logging
import requests
import time
import signal
from pathlib import Path
from zipfile import ZipFile

import oci

### Set up global vars and constants ###

WAIT_TIME = 5 # Sleep for 5 seconds
run = True

### Set up logging ###

# Default log level is INFO. Can be set and injected at container runtime.
loglevel = os.getenv("LOG_LEVEL", default="INFO") # one of DEBUG,INFO,WARNING,ERROR,CRITICAL 
nloglevel = getattr(logging,loglevel.upper(),None) 
if not isinstance(nloglevel, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logger = logging.getLogger('scoring-server')
logger.setLevel(nloglevel)
    
ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)

logger.addHandler(ch)

### Server functions ###

def getAsyncInferenceRequest():
    # Fetch async request from DB - status = ACCEPTED
    # Update request in DB - status = INPROGRESS
    # Convert request into a dict object and return
    # If no async request is found in DB (query returns empty), return None

def processAsyncRequest():
    try:
    # 1. Read input data file and save in temp location within container or pv
    # 2. Open temp data file and convert the json to dict. Read the 'prompts'
    #  array in a loop.  If this array is empty, go to step 4.
    # 3. For each prompt, invoke inference server and receive the prediction.
    #  Add the prediction to the 'predictions' array.
    # 4. Read the 'references' array in a loop. For each reference and
    #  prediction, invoke inference server and receive the score.  Add the 
    #  precision, recall and f1 score values to the 'scores' array. 
    # 5. Convert the dict into json and invoke 'writeOutputDataFile()'
    # 6. Invoke 'uploadOutputDataFile()'
    # 7. Update async request in DB - status = COMPLETED
    except Exception as e:
    # 8. If there was a fatal error, update async request in DB - status=FAILED
        logger.error(f"main_loop(): Encountered exception: {e}")
        logger.warning(f"main_loop(): Unable to process async request.")

    # 9. Return

def writeOutputDataFile():
    # Write output file to a temp location within the container or pv

def uploadOutputDataFile():
    # Finally, read the output data file from temp location and upload it to 
    #  OCI Obj. Store bucket

def interrupt_signal_handler(signum, frame):
    global run
    global loop_var

    run = False
    loop_var = False

signal.signal(signal.SIGINT, interrupt_signal_handler)
signal.signal(signal.SIGTERM, interrupt_signal_handler)
signal.signal(signal.SIGHUP, interrupt_signal_handler)

def main_loop():
    logger.info(f"main_loop(): Start ...")

    while run:
        async_request = getAsyncInferenceRequest()
        if async_request is None:
            logger.info(f"main_loop(): No async request found hence sleeping for {WAIT_TIME} seconds ...")

            # sleep for x seconds
            time.sleep(WAIT_TIME)
        else:
            processAsyncRequest()

    logger.info(f"main_loop(): End ...")

if __name__ == "__main__":
    main_loop()
