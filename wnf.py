from logzero import logger
import logzero
import re
import psycopg2
from prepare import PreparingCursor

import selenium 
from selenium import webdriver 
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

import requests

import os, time, datetime
import imaplib, email, re, pytz

# 対象: 購入 リバランス DeTax

class WealthNavi():
    def db_init(self):
        logger.info("postgresql initializing...")
        db_user = os.environ['DB_USER']
        db_endpoint = os.environ['DB_ENDPOINT']
        db_pass = os.environ['DB_PASS']
        dsn = "postgresql://{0}:{1}@{2}:5432/money".format(db_user, db_pass, db_endpoint) 
        self.conn = psycopg2.connect(dsn)
        
    def init(self):
        logger.info("selenium initializing...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280x3200")
        options.add_argument("--disable-application-cache")
        options.add_argument("--disable-infobars")
        options.add_argument("--no-sandbox")
        options.add_argument("--hide-scrollbars")
        options.add_argument("--v=99")
        options.add_argument("--single-process")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument("--homedir=/tmp")
        options.add_argument('--user-agent=Mozilla/5.0')
        options.add_experimental_option("prefs", {'profile.managed_default_content_settings.images':2})
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 5)

    def login(self):
        self.driver.execute_script("window.open()")
        if not 'WN_ID' in os.environ or not 'WN_PASS' in os.environ:
            raise ValueError("env WN_ID and/or WN_PASS are not found.")
        wn_id = os.environ['WN_ID']
        wn_pass = os.environ['WN_PASS']
        
        self.driver.get('https://invest.wealthnavi.com')
        self.wait.until(ec.presence_of_all_elements_located)
        
        login_time = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
        self.send_to_element('//*[@id="username"]', wn_id)
        self.send_to_element('//*[@id="password"]', wn_pass)
        self.driver.find_element_by_xpath('//*[@id="login"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        if self.driver.find_elements_by_id("menu-dashboard"):
            logger.info("successfully logged in.")
        else:
            raise ValueError("failed to log in.")
            
    def existance_check(self, con, table_name, cols, values):
        cur_check = con.cursor(cursor_factory=PreparingCursor)
        sql = 'SELECT COUNT(*) FROM wn_{0} WHERE {1} = %s'.format(table_name, cols[0])
        for i in range(1, len(cols)):
            sql = sql + ' AND {0} = %s'.format(cols[i])
        cur_check.prepare(sql)
        cur_check.execute(values)
        return not cur_check.fetchone() == (0,)

    def portfolio(self):
        log_date = datetime.datetime.now(pytz.timezone('Asia/Tokyo'))
        with self.conn as con:
            if self.existance_check(con, 'portfolio', ['log_date'], [log_date]):
                cur_delete = con.cursor(cursor_factory=PreparingCursor)
                cur_delete.prepare('DELETE FROM wn_portfolio WHERE log_date = %s')
                cur_delete.execute((log_date,))
                cur_delete.prepare('DELETE FROM wn_portfolio_detail WHERE log_date = %s')
                cur_delete.execute((log_date,))
                logger.info("deleted today's data for inserting new one")

            cur_p = con.cursor(cursor_factory=PreparingCursor)
            cur_p.prepare('INSERT INTO wn_portfolio ' +
                          '(log_date, usdrate, total_amount_jpy, total_amount_usd, total_deposit_jpy, total_withdraw_jpy) ' +
                          'VALUES (%s, %s, %s, %s, %s, %s)')
            cur_pd = con.cursor(cursor_factory=PreparingCursor)
            cur_pd.prepare('INSERT INTO wn_portfolio_detail ' +
                           '(log_date, brand, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta) ' +
                           'VALUES (%s, %s, %s, %s, %s, %s)')
            cur_h = con.cursor(cursor_factory=PreparingCursor)
            cur_h.prepare('INSERT INTO wn_history ' +
                           '(start_date, end_date, history_type, total_jpy, usdrate) ' +
                           'VALUES (%s, %s, %s, %s, %s)')
            cur_hd = con.cursor(cursor_factory=PreparingCursor)
            cur_hd.prepare('INSERT INTO wn_history_detail ' +
                           '(start_date, history_type, trade_type, brand, brand_price_usd, trade_qty, trade_jpy, trade_usd) ' +
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)')

            
            self.driver.get('https://invest.wealthnavi.com/service/portfolio')
            trs = self.driver.find_elements_by_xpath('//*[@id="assets-class-data"]/tbody/tr')
            for tr in trs:
                brand = self.to_brand(tr.find_element_by_tag_name('th').text) # 銘柄
                tds = tr.find_elements_by_tag_name('td')
                self.driver.find_element_by_xpath('//*[@id="content"]/div/div/section[1]/header/div/dl/dd[1]/label/span').click() # 円
                jpy = self.to_number(tds[0].text)
                jpy_delta = self.to_number(tds[1].text)
                self.driver.find_element_by_xpath('//*[@id="content"]/div/div/section[1]/header/div/dl/dd[2]/label/span').click() # ドル
                usd = self.to_number(tds[2].text)
                usd_delta = self.to_number(tds[3].text)
                cur_pd.execute((log_date, brand, jpy, jpy_delta, usd, usd_delta))
            logger.info("inserted wn_portfolio_detail for {0}".format(log_date))

            total_jpy = self.to_number(self.driver.find_element_by_xpath('//*[@id="content"]/div/div/section[2]/div/div/div[1]/div[1]/dl[1]/dt').text)
            total_usd = self.to_number(self.driver.find_element_by_xpath('//*[@id="content"]/div/div/section[2]/div/div/div[1]/div[1]/dl[2]/dt').text)
            usdrate = self.driver.find_element_by_xpath('//*[@id="assets-class-data"]/caption/span[1]').text
            
            self.driver.get('https://invest.wealthnavi.com/service/transaction')
            total_deposit = self.to_number(self.driver.find_element_by_xpath('//*[@id="transaction-total"]/dd[1]/span').text)
            total_withdraw = self.to_number(self.driver.find_element_by_xpath('//*[@id="transaction-total"]/dd[2]/span').text)
            
            last_page = int(self.driver.find_element_by_class_name('last-page').text)
            logger.info("{0} pages in transactions".format(last_page))
            
            target_type = {
                'DeTAX（税金最適化）': 'DETAX',
                '購入': 'BUY',
                'リバランス': 'BAL',
                '売却': 'SELL'
            }
            nontarget_type = ['分配金','クイック入金','積立','手数料','資産運用開始キャンペーン','積立開始キャンペーン','入金']
            end_flag = False
            for page in range(1, last_page+1):
                if end_flag:
                    break
                self.driver.get('https://invest.wealthnavi.com/service/transaction/{0}'.format(page))
                entry_list = self.driver.find_element_by_class_name('history-timeline').find_elements_by_tag_name('li')
                for entry in entry_list:
                    history_type = entry.find_element_by_class_name('assets-type').text
                    if history_type in target_type:
                        if len(entry.find_elements_by_class_name('assets-detail')) > 0:
                            total_jpy = self.to_number(entry.find_element_by_class_name('assets-detail').text)
                        else:
                            total_jpy = None
                        date_root = entry.find_element_by_class_name('date')
                        start_date = self.to_date(date_root.find_element_by_xpath('time').text)
                        end_date = self.to_date(date_root.find_element_by_xpath('span[2]/time').text)
                        logger.debug("{0} {1}-{2} {3}".format(history_type, start_date, end_date, total_jpy))
                        if self.existance_check(con, 'history', ['start_date', 'history_type'], [start_date, target_type[history_type]]):
                            end_flag = True
                            logger.info("loop break at {0} {1}".format(start_date, history_type))
                            break
                        else:
                            content_list = entry.find_element_by_class_name('history-item-content').find_elements_by_tag_name('h2')
                            for i in range(0, len(content_list)):
                                trade_type = content_list[i].text
                                trs = content_list[i].find_elements_by_xpath('following-sibling::table[1]/tbody/tr')
                                for tr in trs:
                                    spans = tr.find_elements_by_xpath('th/span')
                                    history_brand = spans[1].text
                                    trade_qty = spans[2].text
                                    brand_price_usd = self.to_number(spans[3].text)
                                    history_usdrate = spans[4].text
                                    spans = tr.find_elements_by_xpath('td/span')
                                    trade_jpy = self.to_number(spans[0].text)
                                    trade_usd = self.to_number(spans[1].text)
                                    logger.debug("{0} {1} {2} {3} {4} {5}".format(history_brand, trade_qty, brand_price_usd, history_usdrate, trade_jpy, trade_usd))
                                    cur_hd.execute((start_date, target_type[history_type], target_type[trade_type], history_brand, brand_price_usd, trade_qty, trade_jpy, trade_usd))
                            cur_h.execute((start_date, end_date, target_type[history_type], total_jpy, history_usdrate))
                    elif history_type not in nontarget_type:
                        logger.warning('unknown history type "{0}"'.format(history_type))
                logger.info("processed No.{0} page".format(page))

            cur_p.execute((log_date, usdrate, total_jpy, total_usd, total_deposit, total_withdraw))
            logger.info("inserted wn_portfolio for {0}".format(log_date))
            con.commit()
            logger.info("transaction committed")
    
        
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


############################################################

    def to_date(self, text):
        return datetime.datetime.strptime(text, '%Y年%m月%d日')
    
    def to_number(self, text):
        if text == '-':
            return None;
        return text.replace(',','').replace('$','').replace('¥','').replace('+','')
    
    def to_brand(self, text):
        result = re.match('.*\((.+)\)', text)
        if result is None:
            return 'CASH'
        else:
            return result.group(1)
        
    def print_html(self):
        html = self.driver.execute_script("return document.getElementsByTagName('html')[0].innerHTML")
        print(html)

    def send_to_element(self, xpath, keys):
        element = self.driver.find_element_by_xpath(xpath)
        element.clear()
        logger.debug("[send_to_element] " + xpath)
        element.send_keys(keys)

    def send_to_element_direct(self, element, keys):
        element.clear()
        logger.debug("[send_to_element] " + element.get_attribute('id'))
        element.send_keys(keys)

if __name__ == "__main__":
    if "LOG_LEVEL" in os.environ:
        logzero.loglevel(int(os.environ["LOG_LEVEL"]))
    wn = WealthNavi()
    try:
        wn.db_init()
        wn.init()
        wn.login()
        wn.portfolio()
    finally:
        wn.close()
