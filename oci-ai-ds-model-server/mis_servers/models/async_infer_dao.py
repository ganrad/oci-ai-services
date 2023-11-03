# import json
import logging
import os
import psycopg2
from psycopg2.extras import Json

from .base_dao import BaseDAO

# Set up logging for this module
loglevel = os.getenv("LOG_LEVEL", default="DEBUG") # one of DEBUG,INFO,WARNING,ERROR,CRITICAL

logger = logging.getLogger('models.async_infer_dao')
logger.setLevel(loglevel)

ch = logging.StreamHandler()
formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

class AsyncInferenceRequest(BaseDAO):
    def __init__(self, data: dict):
        super().__init__(data)

    def create_entity(self, data: dict):
        logger.debug(f"create_entity(): Data:\n{data}")

        try:
            insert_query = "INSERT INTO INF_JOBS(data) VALUES (%s)"
            conn = self.get_connection()

            with conn.cursor() as cursor:
                cursor.execute(insert_query,[Json(data)])
                count = cursor.rowcount

            conn.commit()

            logger.info(f"create_entity(): Record [{count}] inserted into INF_JOBS table successfully")
        except (psycopg2.Error) as error:
            logger.error(f"create_entity(): Failed to insert record into INF_JOBS table. PGCode: {error.pgcode}; PGError: {error.pgerror}")
            raise error
        except (Exception) as error:
            logger.error(f"create_entity(): Failed to insert record into INF_JOBS table. Exception: {error}")
            raise error
        finally:
            conn.close()
            logger.info("create_entity(): DB Connection closed")

        return count

    def get_entity_by_id(self, jobid: str):
        logger.debug(f"get_entity_by_id(): Job id: {jobid}")

        try:
            query = "SELECT data FROM INF_JOBS WHERE (data ->> 'job_id') = %s"
            conn = self.get_connection()

            with conn.cursor() as cursor:
                cursor.execute(query,[jobid])
                count = cursor.rowcount
                if count == 1:
                    job_detail = cursor.fetchone()[0]
                else:
                    job_detail = {
                        "db_msg" : f"Inference Job id: [{jobid}] not found!"
                    }
            conn.commit()

            logger.info(f"get_entity_by_id(): [{count}] record retrieved from INF_JOBS table")
        except (psycopg2.Error) as error:
            logger.error(f"get_entity_by_id(): Failed to read record from INF_JOBS table. PGCode: {error.pgcode}; PGError: {error.pgerror}")
            raise error
        except (Exception) as error:
            logger.error(f"get_entity_by_id(): Encountered exception: {error}")
            raise error
        finally:
            conn.close()
            logger.info("get_entity_by_id(): DB Connection closed")

        return job_detail
