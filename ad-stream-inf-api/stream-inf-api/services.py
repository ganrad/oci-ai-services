"""
   Author: ganrad01@gmail.com
   Description: Streaming service module. Defines service operations.
   Dated: 07-06-2022

   Notes:
"""

import base64
import csv
import datetime
import logging

from io import StringIO
import pandas as pd

from oci.config import from_file
from oci.ai_anomaly_detection.anomaly_detection_client import AnomalyDetectionClient
from oci.ai_anomaly_detection.models.embedded_detect_anomalies_request import EmbeddedDetectAnomaliesRequest
from oci.exceptions import ServiceError
from .errors import StreamApiException
from .backend.factory import StoreProviderFactory

logger = logging.getLogger(__name__)

class AdService:

    def __init__(self, conf_file, api_endpoint, compartment_id, stream_context):
        self.conf_file = conf_file
        self.api_endpoint = api_endpoint
        self.compartment_id = compartment_id
        self.stream_context = stream_context

    # Function to insert row in the dataframe
    def insertRow(self,row_number, df, row_value):
        # Slice the upper half of the dataframe
        df1 = df[0:row_number]
  
        # Store the result of lower half of the dataframe
        df2 = df[row_number:]
  
        # Insert the row in the upper half dataframe
        df1.loc[row_number]=row_value
  
        # Concat the two dataframes
        df_result = pd.concat([df1, df2])
  
        # Reassign the index labels
        df_result.index = [*range(df_result.shape[0])]
  
        # Return the updated dataframe
        return df_result

    def executeInference(
        self,
        clientid,
        ocid,
        window_s,
        sensitivity,
        ctnt_type,
        data):

        logger.info(f"executeInference: - BEGIN\nClient ID = {clientid}\nOCID = {ocid}")
        # Set the cache key
        cache_key = clientid + ":" + ocid

        # retrieve window size dp's from backend store / cache
        _backend_store = StoreProviderFactory(self.stream_context)
        cache_str = """0,853,9.8,2.7
1,856,13.6,2.7
2,853,11.8,2.7
3,853,11.8,2.7
4,853,7.9,2.7
5,853,13.7,2.7
6,853,11.8,2.7
7,853,9.8,2.7
8,853,17.7,2.7
9,853,11.8,2.7
10,853,11.8,2.7
11,853,23.5,2.7
12,853,9.8,2.7
13,853,13.7,2.7
14,853,23.5,2.7
15,853,11.8,2.7
16,853,11.8,2.7
17,856,17.6,2.7
18,856,17.7,2.7
19,853,9.8,2.7"""

        pd.set_option("mode.chained_assignment",None) # Pandas: Ignore chained assignment warnings!

        # Convert request data (bytes) to string so csv data can be read into a data frame
        data_str_io = StringIO(str(data,"utf-8"))
        df_data = pd.read_csv(data_str_io,sep=",")

        # Use StringIO to read in cached (window size dp's) csv data
        reader = csv.reader(StringIO(cache_str), delimiter=",")

        logger.info(f"executeInference: Client ID=[{clientid}] - No. of rows received in request=[{df_data.shape[0]}]")
        #print(f"executeInference: --- df_data.info() ---\n{df_data.info()}")
        buffer = StringIO()
        df_data.info(buf=buffer)
        logger.debug(f"executeInference: --- Client ID=[{clientid}] ---\nData.info:\n{buffer.getvalue()}")

        idx = 0
        cols = df_data.dtypes
        for row in reader:
            rowf = []
            for index, value in enumerate(row):
                if cols[index] == "int64":
                    rowf.append(int(value))
                elif cols[index] == "float64":
                    rowf.append(float(value))
                else:
                    rowf.append(value) 

            # print(f"Window row: Index={idx}, Row={rowf}")
            df_data = self.insertRow(idx,df_data,rowf)
            idx += 1
        logger.info(f"executeInference: Client ID={[clientid]} - No. of rows in inference data set after inserting window rows=[{df_data.shape[0]}]")

        config = from_file(self.conf_file)
        ad_client = AnomalyDetectionClient(config,service_endpoint=self.api_endpoint)

        window_size = None
        service_obj = None
        # Only retrieve the window size from AD model if the input window size was null
        if window_s == None:
            try:
                service_obj = ad_client.get_model(ocid)
                window_size = service_obj.data.model_training_results.window_size
                logger.info(f"executeInference: Client ID=[{clientid}] - Window Size (from model def)=[{window_size}]")
            except ServiceError as se:
                logger.error(f"executeInference: Client ID=[{clientid}] - Encountered Exception",exc_info=True)
                raise StreamApiException(clientid,ocid,se.target_service,se.status,se.code,se.message,se.operation_name,se.request_endpoint,se.client_version,se.timestamp)
        else:
            window_size = window_s
            logger.info(f"executeInference: Client ID=[{clientid}] - Window Size=[{window_size}]")

        df_window_data = df_data.iloc[(df_data.shape[0] - window_size):]
        logger.info(f"executeInference: Client ID=[{clientid}] - No. of rows in window data frame=[{df_window_data.shape[0]}]")

        cache_str = df_window_data.to_csv(header=False,index=False)
        logger.debug(f"executeInference: Client ID=[{clientid}] - Window data set (string) to cache:\n{cache_str}")

        data = str.encode(df_data.to_csv(header=True,index=False))
        logger.debug(f"executeInference: Client ID=[{clientid}] - Inference data set:\n" + df_data.to_csv(header=True,index=False))

        data_base64 = str(base64.b64encode(data),"utf-8")
        embedded_request = EmbeddedDetectAnomaliesRequest(
            model_id=ocid,
            sensitivity=sensitivity,
            request_type="BASE64_ENCODED",
            content_type=ctnt_type,
            content=data_base64)

        service_obj = None
        try:
            service_obj = ad_client.detect_anomalies(detect_anomalies_details=embedded_request)
            # print(inf_response)
        except ServiceError as se:
            logger.error(f"executeInference: Client ID=[{clientid}] - Encountered Exception",exc_info=True)
            raise StreamApiException(clientid,ocid,se.target_service,se.status,se.code,se.message,se.operation_name,se.request_endpoint,se.client_version,se.timestamp)

        # Cache the window data set

        # Print the request id for troubleshooting issues
        logger.info(f"executeInference: - End\nClient ID = {clientid}\nOCID = {ocid}\nRequestId = {service_obj.request_id}")
        return (service_obj.data)

    def getAdServiceHealth(self):
        logger.debug("getAdServiceHealth: - End")
        dt = datetime.datetime.now()

        return ({
		  "time": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
		  "config": {
		       "oci_conf_file": self.conf_file,
		       "api_endpoint": self.api_endpoint,
		       "compartment_id": self.compartment_id},
		  "status": "OK"})

