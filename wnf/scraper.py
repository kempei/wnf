from logzero import logger
import psycopg2

from wnf.prepare import PreparingCursor

from selenium import webdriver 
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement, By

import os, datetime, time, pytz, requests

from decimal import Decimal

class Scraper():
    def db_init(self):
        logger.info("postgresql initializing...")
        db_user = os.environ['DB_USER']
        db_endpoint = os.environ['DB_ENDPOINT']
        db_pass = os.environ['DB_PASS']
        dsn = "postgresql://{0}:{1}@{2}:5432/money".format(db_user, db_pass, db_endpoint) 
        self.conn = psycopg2.connect(dsn)
        
    def init(self):
        logger.info("selenium initializing...")

        if not 'ALPHAVANTAGE_API_KEY' in os.environ:
            raise ValueError("env ALPHAVANTAGE_API_KEY is not found.")
        self.alphavantage_apikey = os.environ['ALPHAVANTAGE_API_KEY']

        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=600x1000")
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-sandbox")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--v=99")
        # options.add_argument("--single-process")
        options.add_argument("--ignore-certificate-errors")
        # options.add_argument("--homedir=/tmp")
        options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36')
        options.add_experimental_option("prefs", {'profile.managed_default_content_settings.images':2})
        self.driver = webdriver.Chrome(options=options)
        self.driver.implicitly_wait(10)
        self.wait = WebDriverWait(self.driver, 10)

    def close(self):
        try:
            self.conn.close()
        except:
            logger.debug("Ignore exception (conn close)")

        try:
            self.driver.close()
        except:
            logger.debug("Ignore exception (driver close)")

        try:
            self.driver.quit()
        except:
            logger.debug("Ignore exception (driver quit)")

    def existance_check(self, con, table_name, cols, values):
        cur_check = con.cursor(cursor_factory=PreparingCursor)
        sql = 'SELECT COUNT(*) FROM {0} WHERE {1} = %s'.format(table_name, cols[0])
        for i in range(1, len(cols)):
            sql = sql + ' AND {0} = %s'.format(cols[i])
        cur_check.prepare(sql)
        cur_check.execute(values)
        return not cur_check.fetchone() == (0,)

    def print_html(self):
        html = self.driver.execute_script("return document.getElementsByTagName('html')[0].innerHTML")
        print(html)

    def send_to_element(self, xpath, keys):
        element = self.driver.find_element(by=By.XPATH, value=xpath)
        element.clear()
        logger.debug("[send_to_element] " + xpath)
        time.sleep(0.5)
        element.send_keys(keys)

    def send_to_element_direct(self, element, keys):
        element.clear()
        logger.debug("[send_to_element] " + element.get_attribute('id'))
        element.send_keys(keys)

    def get_local_date(self):
        d = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
        return datetime.date(d.year, d.month, d.day)

    def get_brand_price(self, brand):
        r = requests.get('https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={0}&apikey={1}'.format(brand,  self.alphavantage_apikey))
        if r.status_code >= 500 and r.status_code < 600:
            logger.warn('alphavantage invalid http status {0}'.format(r.status_code))
            time.sleep(3)
            return self.get_brand_price(brand)
        elif r.status_code != 200:
            logger.error('alphavantage invalid http status {0}'.format(r.status_code))
            raise ConnectionRefusedError()
        else:
            data = r.json()
            if 'Note' in data:
                # API throttle
                logger.info('sleeping 60 secs to avoid alphavantage api throttle...')
                time.sleep(60)
                return self.get_brand_price(brand)
            return Decimal(data['Global Quote']['05. price'])

