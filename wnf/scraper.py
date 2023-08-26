from logzero import logger
import apsw

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import By
from selenium.webdriver.support import expected_conditions as ec

import boto3
from ssm_cache import SSMParameter
import json

import os
import datetime
import time
import pytz

import requests


class Configure:
    def __init__(self) -> None:
        self.__config = None

    def config(self, key: str) -> dict:
        if self.__config is None:
            self.__config = json.loads(SSMParameter("wnf_config").value)
        return self.__config[key]


class Scraper(Configure):
    def __init__(self) -> None:
        super().__init__()

        self.alphavantage_apikey = self.config("alphavantage_api_key")

        logger.info("selenium initializing...")

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=800x1000")
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-sandbox")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--lang=ja-JP")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36")
        options.binary_location = "/usr/bin/chromium-browser"
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 5)
        self.driver.implicitly_wait(10)

    def close(self):
        try:
            self.driver.close()
        except:
            logger.debug("Ignore exception (driver close)")

        try:
            self.driver.quit()
        except:
            logger.debug("Ignore exception (driver quit)")

    def print_html(self):
        html = self.driver.execute_script("return document.getElementsByTagName('html')[0].innerHTML")
        print(html)

    def send_to_element(self, xpath, keys):
        element = self.driver.find_element(by=By.XPATH, value=xpath)
        element.clear()
        logger.debug("[send_to_element] " + xpath)
        element.send_keys(keys)

    def send_to_element_direct(self, element, keys):
        element.clear()
        logger.debug("[send_to_element] " + element.get_attribute("id"))
        element.send_keys(keys)

    def get_local_date(self):
        return datetime.datetime.now(pytz.timezone("Asia/Tokyo")).date()

    def get_brand_price(self, brand) -> float:
        r = requests.get("https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={0}&apikey={1}".format(brand, self.alphavantage_apikey))
        if r.status_code >= 500 and r.status_code < 600:
            logger.warn("alphavantage invalid http status {0}".format(r.status_code))
            time.sleep(3)
            return self.get_brand_price(brand)
        elif r.status_code != 200:
            logger.error("alphavantage invalid http status {0}".format(r.status_code))
            raise ConnectionRefusedError()
        else:
            data = r.json()
            if "Note" in data:
                # API throttle
                logger.info("sleeping 60 secs to avoid alphavantage api throttle...")
                time.sleep(60)
                return self.get_brand_price(brand)
            return float(data["Global Quote"]["05. price"])

    def get_handle_with_xpath(self, xpath):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            logger.debug(self.driver.title)
            self.wait.until(ec.presence_of_all_elements_located)
            if len(self.driver.find_elements(by=By.XPATH, value=xpath)):
                return handle
        raise ValueError(f"cannot find xpath: {xpath} in {len(self.driver.window_handles)} handles")

    def title_check(self, title):
        if self.driver.title != title:
            raise AssertionError(f"title must be {title} but {self.driver.title}")


class DBScraper(Scraper):
    DB_NAME = "wnf.db"

    def __init__(self) -> None:
        super().__init__()
        self.conn: apsw.Connection = self.__get_sqlite3_connection()
        self.committed_db: bool = False

    def begin_transaction(self, transaction_id: int = 1):
        self.conn.execute(f"BEGIN TRANSACTION transaction_{transaction_id}")

    def commit_transaction(self, transaction_id: int = 1):
        self.conn.execute(f"COMMIT TRANSACTION transaction_{transaction_id}")
        self.committed_db = True

    def rollback_transaction(self, transaction_id: int = 1):
        self.conn.execute(f"ROLLBACK TRANSACTION transaction_{transaction_id}")

    def __has_file(self, bucket_name: str, target_key: str, is_allowed_zero_byte: bool = True) -> bool:
        """Check to exist a file in S3.
        Args:
            bucket_name (str): S3 bucket name
            target_key (str): target of S3 key
            is_allowed_zero_byte (bool, optional): True: Allow an empty file, False: Not allow. Defaults to True.
        Returns:
            bool: True: Exists file. False: Not exists.
        """
        s3_client = boto3.client("s3")
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            Prefix=target_key,
        )
        key_count: int = response["KeyCount"]
        return key_count > 0

    def get_sql_from_file(self, sql_file_path: str) -> str:
        with open(sql_file_path, "r", encoding="utf-8") as f:
            sql = f.read()
        return sql

    def __get_sqlite3_connection(self) -> apsw.Connection:
        logger.info("sqlite3 initializing...")
        local_db_file = f"/tmp/{self.DB_NAME}"
        db_on_local = os.path.isfile(local_db_file)
        db_on_s3 = False
        if not db_on_local:
            s3_bucket_name = self.config("s3-bucket")
            s3_resource = boto3.resource("s3")
            bucket = s3_resource.Bucket(s3_bucket_name)
            db_on_s3 = self.__has_file(s3_bucket_name, self.DB_NAME)
            if db_on_s3:
                bucket.download_file(self.DB_NAME, local_db_file)
                logger.info("Downloaded sqlite3 database file.")
        conn = apsw.Connection(local_db_file)
        if not db_on_local and not db_on_s3:
            conn.execute(self.get_sql_from_file("sql/sbi_ctab.sql"))
            conn.execute(self.get_sql_from_file("sql/wn_ctab.sql"))
            logger.info("Created sqlite3 database.")
        return conn

    def __store_db_to_s3(self):
        s3_bucket_name = self.config("s3-bucket")
        s3_resource = boto3.resource("s3")
        bucket = s3_resource.Bucket(s3_bucket_name)
        bucket.upload_file(Filename=f"/tmp/{self.DB_NAME}", Key=self.DB_NAME)
        logger.info("Uploaded sqlite3 database file.")

    def existance_check(self, table_name, cols, values):
        cursor = self.conn.cursor()
        sql = f"SELECT COUNT(*) FROM {table_name} WHERE {cols[0]} = ?"
        for i in range(1, len(cols)):
            sql = sql + f" AND {cols[i]} = ?"
        rows = list(cursor.execute(sql, values))
        return rows[0][0] > 0

    def close(self):
        try:
            self.conn.close()
            if self.committed_db:
                self.__store_db_to_s3()
        except:
            logger.debug("Ignore exception (conn close)")
        super().close()
