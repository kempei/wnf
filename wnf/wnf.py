from wnf.scraper import Scraper
from wnf.prepare import PreparingCursor
import wnf.simpleslack as simpleslack

from logzero import logger
import logzero

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.remote.webelement import By

import os, datetime, re

from decimal import Decimal


# 対象: 購入 リバランス DeTax

class WealthNavi(Scraper):

    def login(self):
        self.driver.execute_script("window.open()")
        if not 'WN_ID' in os.environ or not 'WN_PASS' in os.environ:
            raise ValueError("env WN_ID and/or WN_PASS are not found.")
        wn_id = os.environ['WN_ID']
        wn_pass = os.environ['WN_PASS']
        
        self.driver.get('https://invest.wealthnavi.com')
        self.wait.until(ec.presence_of_all_elements_located)
        
        self.send_to_element('//*[@id="username"]', wn_id)
        self.send_to_element('//*[@id="password"]', wn_pass)
        self.driver.find_element(by=By.XPATH, value='//*[@id="login"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        if self.driver.title == "ホーム : WealthNavi":
            logger.info("successfully logged in.")
        else:
            logger.error("invalid title: {0}".format(self.driver.title))
            raise ValueError("failed to log in. title = {0}".format(self.driver.title))
            
    def portfolio(self):
        log_date = self.get_local_date()
        logger.info('inserting data as {0}'.format(log_date))
        with self.conn as con:
            if self.existance_check(con, 'wn_portfolio', ['log_date'], [log_date]):
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
                           '(log_date, brand, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta, price_usd, qty) ' +
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)')
            cur_h = con.cursor(cursor_factory=PreparingCursor)
            cur_h.prepare('INSERT INTO wn_history ' +
                           '(start_date, end_date, history_type, total_jpy, usdrate) ' +
                           'VALUES (%s, %s, %s, %s, %s)')
            cur_hd = con.cursor(cursor_factory=PreparingCursor)
            cur_hd.prepare('INSERT INTO wn_history_detail ' +
                           '(start_date, history_type, trade_type, brand, brand_price_usd, trade_qty, trade_jpy, trade_usd) ' +
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)')

            
            self.driver.get('https://invest.wealthnavi.com/service/portfolio')
            logger.debug("title: {0}".format(self.driver.title))
            trs = self.driver.find_elements(by=By.XPATH, value='//*[@id="assets-class-data"]/tbody/tr')
            for tr in trs:
                brand = self.to_brand(tr.find_element(by=By.TAG_NAME, value='th').get_attribute("textContent")) # 銘柄
                tds = tr.find_elements(by=By.TAG_NAME, value='td')
                jpy = self.to_number(tds[0].get_attribute("textContent"))
                jpy_delta = self.to_number(tds[1].get_attribute("textContent"))
                usd = self.to_number(tds[2].get_attribute("textContent"))
                usd_delta = self.to_number(tds[3].get_attribute("textContent"))
                if brand != 'CASH':
                    price_usd = self.get_brand_price(brand) #Decimal
                    qty = Decimal(usd) / price_usd
                else:
                    price_usd = Decimal('0')
                    qty = Decimal('0')
                cur_pd.execute((log_date, brand, jpy, jpy_delta, usd, usd_delta, price_usd, qty))
                logger.debug("inserting wn_portfolio_detail for {0},{1},{2},{3},{4},{5},{6},{7}".format(log_date, brand, jpy, jpy_delta, usd, usd_delta, price_usd, qty))
            logger.info("inserted wn_portfolio_detail for {0}".format(log_date))
            usdrate = self.driver.find_element(by=By.XPATH, value='//*[@id="assets-class-data"]/caption/span[1]').get_attribute("textContent")
    
            self.driver.get('https://invest.wealthnavi.com/service')
            logger.debug("title: {0}".format(self.driver.title))
            total_jpy = self.to_number(self.driver.find_element(by=By.XPATH, value='//*[@id="content"]/div/div[3]/section/div/div/div[1]/div[1]/dl[1]/dt/span').get_attribute("textContent"))
            total_usd = self.to_number(self.driver.find_element(by=By.XPATH, value='//*[@id="content"]/div/div[3]/section/div/div/div[1]/div[1]/dl[2]/dt/span').get_attribute("textContent"))

            self.driver.get('https://invest.wealthnavi.com/service/transaction')
            logger.debug("title: {0}".format(self.driver.title))

            # 総入金額
            total_deposit = self.to_number(self.driver.find_element(by=By.XPATH, value='//*[@class="transaction-money"]/div[1]/dd/span').get_attribute("textContent"))
            # 総出金額
            total_withdraw = self.to_number(self.driver.find_element(by=By.XPATH, value='//*[@class="transaction-money"]/div[2]/dd/span').get_attribute("textContent"))
            
            last_page = int(self.to_number(self.driver.find_element(by=By.XPATH, value='//*[@id="content"]/div/div/nav/ul/li[last()]').get_attribute("textContent")))
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
                entry_list = self.driver.find_element(by=By.CLASS_NAME, value='history-timeline').find_elements(by=By.TAG_NAME, value='li')
                for entry in entry_list:
                    history_type = entry.find_element(by=By.CLASS_NAME, value='assets-type').get_attribute("textContent")
                    if history_type in target_type:
                        if len(entry.find_elements(by=By.CLASS_NAME, value='assets-detail')) > 0:
                            total_trade_jpy = self.to_number(entry.find_element(by=By.CLASS_NAME, value='assets-detail').get_attribute("textContent"))
                        else:
                            total_trade_jpy = None
                        date_root = entry.find_element(by=By.CLASS_NAME, value='date')
                        start_date = self.to_date(date_root.find_element(by=By.XPATH, value='time').get_attribute("textContent"))
                        end_date = self.to_date(date_root.find_element(by=By.XPATH, value='span[2]/time').get_attribute("textContent"))
                        logger.debug("{0} {1}-{2} {3}".format(history_type, start_date, end_date, total_trade_jpy))
                        slack_text = ':dollar:{0}を{1}に実施しました(受取日={2})'.format(history_type, start_date.strftime('%m月%d日'), end_date.strftime('%m月%d日'))
                        if self.existance_check(con, 'wn_history', ['start_date', 'history_type'], [start_date, target_type[history_type]]):
                            end_flag = True
                            logger.info("loop break at {0} {1}".format(start_date, history_type))
                            break
                        else:
                            content_list = entry.find_element(by=By.CLASS_NAME, value='history-item-content').find_elements(by=By.TAG_NAME, value='h2')
                            for i in range(0, len(content_list)):
                                trade_type = content_list[i].get_attribute("textContent")
                                trs = content_list[i].find_elements(by=By.XPATH, value='following-sibling::table[1]/tbody/tr')
                                for tr in trs:
                                    spans = tr.find_elements(by=By.XPATH, value='th/span')
                                    history_brand = spans[1].get_attribute("textContent")
                                    trade_qty = self.to_number(spans[2].text)
                                    brand_price_usd = self.to_number(spans[3].get_attribute("textContent"))
                                    history_usdrate = spans[4].get_attribute("textContent")
                                    spans = tr.find_elements(by=By.XPATH, value='td/span')
                                    trade_jpy = self.to_number(spans[0].get_attribute("textContent"))
                                    trade_usd = self.to_number(spans[1].get_attribute("textContent"))
                                    logger.debug("{0} {1} {2} {3} {4} {5}".format(history_brand, trade_qty, brand_price_usd, history_usdrate, trade_jpy, trade_usd))
                                    cur_hd.execute((start_date, target_type[history_type], target_type[trade_type], history_brand, brand_price_usd, trade_qty, trade_jpy, trade_usd))
                                    slack_text += '\n - {0}を${1}で{2}口{3}しました(合計${4})'.format(history_brand, brand_price_usd, trade_qty, trade_type, trade_usd)
                            cur_h.execute((start_date, end_date, target_type[history_type], total_trade_jpy, history_usdrate))
                            slack_text += '\n(為替レート 1ドル={0}円)'.format(history_usdrate)
                            simpleslack.send_to_slack(slack_text)
                    elif history_type not in nontarget_type:
                        logger.warning('unknown history type "{0}"'.format(history_type))
                logger.info("processed No.{0} page".format(page))

            cur_p.execute((log_date, usdrate, total_jpy, total_usd, total_deposit, total_withdraw))
            logger.info("inserted wn_portfolio for {0}".format(log_date))
            con.commit()
            logger.info("transaction committed")

############################################################
    def to_date(self, text):
        return datetime.datetime.strptime(text, '%Y年%m月%d日')
    
    def to_number(self, text):
        ret = text.replace(',','').replace('$','').replace('¥','').replace('+','').replace(' ','').replace('\n','').strip()
        if ret == '-':
            return None;
        return ret
    
    def to_brand(self, text):
        result = re.match('.*\((.+)\)', text)
        if result is None:
            logger.debug('to_brand: {0}'.format(text))
            return 'CASH'
        else:
            return result.group(1)

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
