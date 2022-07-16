"""
   Author: ganrad01@gmail.com
   Description: Exception module. Defines an exception class which can be used to return the error response received from
   the AD Service REST API.
   Dated: 07-06-2022

   Notes:
"""

class StreamApiException(Exception):

    def __init__(self,clientid,ocid,service,status,code,error_message,operation,endpoint,client_version,timestamp):
        self.client_id = clientid
        self.model_ocid = ocid
        self.service = service
        self.status = status
        self.code = code
        self.error_message = error_message
        self.operation = operation
        self.endpoint = endpoint
        self.client_version = client_version
        self.timestamp = timestamp
