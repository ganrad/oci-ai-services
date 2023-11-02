import psycopg2

class BaseDAO(object):
    def __init__(self, params: dict):
        self.params = params

    def get_connection(self):
        connection = psycopg2.connect(
            database=self.params["db_name"],
            user=self.params["db_uname"],
            password=self.params["db_password"],
            host=self.params["db_host"],
            port=self.params["db_host_port"]
        )
        
        return connection
