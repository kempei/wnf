from scraper import Scraper

from logzero import logger
import logzero

from selenium.webdriver.support import expected_conditions as ec
import psycopg2
from prepare import PreparingCursor

import os, time, datetime, re

from decimal import Decimal, ROUND_UP, ROUND_DOWN

import simpleslack

class SbiTrade(Scraper):

    direct_path_dict = {
        'bondlist': 'https://trading0.sbisec.co.jp/bff/fbonds/BffPossessionBondList.do'
    }
    def get_sbi_url(self, text):
        path_dict = {
            'backtohome': '?_ControlID=WPLEThmR001Control&_PageID=DefaultPID&_DataStoreID=DSWPLEThmR001Control&_ActionID=DefaultAID&getFlg=on',
            'inv_capacity': '?_ControlID=WPLETacR003Control&_PageID=DefaultPID&_DataStoreID=DSWPLETacR003Control&_SeqNo=1572738402951_default_task_39_DefaultPID_DefaultAID&getFlg=on&_ActionID=DefaultAID',
            'wallet': '?OutSide=on&_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&_PageID=WPLETsmR001Sdtl12&sw_page=BondFx&cat1=home&cat2=none&sw_param2=02_201&getFlg=on&int_pr1=150313_cmn_gnavi:2_dmenu_02',
            'add_inv_capacity': '?_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&sw_page=Banking&cat1=home&cat2=none&getFlg=on&int_ct=140318_in_btn_01',
            'global_trade': '?OutSide=on&_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&sw_page=Foreign&cat1=home&cat2=none&sw_param1=GB&getFlg=on'
        }
        return self.sbi_core_url + path_dict[text]
        
    def login(self):
        self.sbi_core_url = 'https://www.sbisec.co.jp/ETGate/'
        self.driver.execute_script("window.open()")
        if not 'SBI_ID' in os.environ or not 'SBI_PASS' or not 'SBI_TRADE_PASS' in os.environ:
            raise ValueError("env SBI_ID and/or SBI_PASS and/or SBI_TRADE_PASS are not found.")
        sbi_id = os.environ['SBI_ID']
        sbi_pass = os.environ['SBI_PASS']

        if not 'SBI_BANK_ID' in os.environ or not 'SBI_BANK_PASS' or not 'SBI_BANK_TRADE_PASS' in os.environ:
            raise ValueError("env SBI_BANK_ID and/or SBI_BANK_PASS and/or SBI_BANK_TRADE_PASS are not found.")

        self.driver.get(self.sbi_core_url)
        self.wait.until(ec.presence_of_all_elements_located)
        
        self.send_to_element('//*[@name="user_id"]', sbi_id)
        self.send_to_element('//*[@name="user_password"]', sbi_pass)
        self.driver.find_element_by_xpath('//*[@name="ACT_login"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        if self.driver.find_elements_by_xpath('//*[@id="MAINAREA01"]/div[1]/div/div/p[1]'):
            logger.info("successfully logged in. current_url = {0}".format(self.driver.current_url))
            self.sbi_core_url = self.driver.current_url
        else:
            raise ValueError("failed to log in.")

    def portfolio(self):
        log_date = self.get_local_date()
        logger.info('inserting data as {0}'.format(log_date))
        with self.conn as con:
            if self.existance_check(con, 'sbi_portfolio', ['log_date'], [log_date]):
                cur_delete = con.cursor(cursor_factory=PreparingCursor)
                cur_delete.prepare('DELETE FROM sbi_portfolio WHERE log_date = %s')
                cur_delete.execute((log_date,))
                cur_delete.prepare('DELETE FROM sbi_portfolio_detail WHERE log_date = %s')
                cur_delete.execute((log_date,))
                logger.info("deleted today's data for inserting new one")

            cur_p = con.cursor(cursor_factory=PreparingCursor)
            cur_p.prepare('INSERT INTO sbi_portfolio ' +
                          '(log_date, usdrate, total_amount_jpy, total_amount_usd, inv_capacity_jpy) ' +
                          'VALUES (%s, %s, %s, %s, %s)')
            cur_pd = con.cursor(cursor_factory=PreparingCursor)
            cur_pd.prepare('INSERT INTO sbi_portfolio_detail ' +
                           '(log_date, brand, price_usd, qty, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta) ' +
                           'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)')
            
            # 買付余力
            inv_capacity_jpy = self.get_inv_capacity()

            # 外貨建て口座 - 保有証券 / NISA は見ていない
            self.driver.get(self.get_sbi_url('wallet')) # 口座へ移動
            self.driver.get(self.direct_path_dict['bondlist'])
            trs = self.driver.find_elements_by_xpath('//*[@id="id2"]/tbody/tr')
            if len(trs) == 0:
                self.print_html()
                raise AssertionError('no information at bondlist')
            total_jpy = 0
            total_usd = 0
            for tr in trs:
                if tr.get_attribute('class') != 'mtext':
                    continue
                brand = self.to_brand(tr.find_element_by_xpath('td[1]/a').get_attribute("textContent"))
                brand_link = tr.find_element_by_xpath('td[1]/a').get_attribute('href')
                if not self.check_etf(brand_link):
                    logger.debug('skipped brand: {0}'.format(brand))
                    continue
                qty_text = tr.find_element_by_xpath('td[2]').get_attribute("textContent")
                if '（' in qty_text:
                    qty_array = self.to_number_array(qty_text)
                    qty = int(qty_array[0]) - int(qty_array[1])
                else:
                    qty = self.to_number(qty_text)
                price_usd = self.to_number_array(tr.find_element_by_xpath('td[3]').get_attribute("textContent"))[1]
                amount_usd = self.to_number_array(tr.find_element_by_xpath('td[4]').get_attribute("textContent"))[0]
                amount_jpy = self.to_number_array(tr.find_element_by_xpath('td[4]').get_attribute("textContent"))[1]
                total_jpy += int(amount_jpy)
                total_usd += float(amount_usd)
                amount_usd_delta = self.to_number_array(tr.find_element_by_xpath('td[5]').get_attribute("textContent"))[0]
                amount_jpy_delta = self.to_number_array(tr.find_element_by_xpath('td[5]').get_attribute("textContent"))[1]
                cur_pd.execute((log_date, brand, price_usd, qty, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta))

            logger.info("inserted sbi_portfolio_detail for {0}".format(log_date))
            usdrate = self.driver.find_element_by_xpath('//*[@id="id2"]/../../../../following-sibling::table/tbody/tr[2]/td[2]').text
            cur_p.execute((log_date, usdrate, total_jpy, total_usd, inv_capacity_jpy))

            logger.info("inserted sbi_portfolio for {0}".format(log_date))

            con.commit()
            logger.info("transaction committed")
    
    def trade(self):
        log_date = self.get_local_date()
        
        check_sql = """SELECT *
FROM (SELECT COUNT(*) FROM wn_portfolio where log_date = %s) w
   , (SELECT COUNT(*) FROM sbi_portfolio where log_date = %s) s"""
        cur_check = self.conn.cursor(cursor_factory=PreparingCursor)
        cur_check.prepare(check_sql)
        cur_check.execute((log_date,log_date))
        row = cur_check.fetchone()
        assert row[0] >= Decimal('0') and row[1] >= Decimal('0')

        diff_sql = """SELECT *
FROM (SELECT s.usdrate usdrate
           , w.log_date m_log_date
        FROM wn_portfolio w
             INNER JOIN sbi_portfolio s
                     ON w.log_date = s.log_date) m
      INNER JOIN (
        SELECT coalesce(trunc(wd.qty+0.999), 0) w_qty
             , coalesce(sd.qty, 0) s_qty
             , coalesce(wd.brand, sd.brand) brand
             , coalesce(wd.log_date, sd.log_date) d_log_date
          FROM wn_portfolio_detail wd
               FULL OUTER JOIN sbi_portfolio_detail sd
                            ON wd.log_date = sd.log_date AND wd.brand = sd.brand) d
               ON m_log_date =  d_log_date
WHERE m_log_date = %s
  AND brand != 'CASH'"""
        cur_diff = self.conn.cursor(cursor_factory=PreparingCursor)
        cur_diff.prepare(diff_sql)
        cur_diff.execute((log_date,))
        buy_list = []
        for row in cur_diff:
            logger.debug(row)
            brand = row[4]
            usdrate = row[0] # Decimal
            wn_qty = row[2] # Decimal
            sbi_qty = row[3] # Decimal
            diff_qty = wn_qty - sbi_qty
            if diff_qty >= 1:
                buy_list.append({'brand': brand, 'qty': diff_qty})
        
        if len(buy_list) > 0:
            self.buy_from_list(buy_list, usdrate)

    def buy_from_list(self, buy_list, usdrate):
        # make price list
        for item in buy_list:
            item['price'] = self.get_brand_price(item['brand']) #Decimal

        # calc inv. capacity
        required_ic = Decimal(0)
        for item in buy_list:
            required_ic += item['price'] * item['qty'] * usdrate
        required_ic += required_ic * Decimal('0.01') # 手数料0.49%を加味して1%を足しておく
        required_ic = required_ic.to_integral_value(rounding=ROUND_UP) # 切り上げる
        current_ic = Decimal(self.get_inv_capacity())
        desired_ic = required_ic - current_ic + 100000 # 10万円余分に入れておく
        logger.info('current investment capacity: {0}, required: {1}, desired: {2}'.format(current_ic, required_ic, desired_ic))
        if desired_ic > 0:
            self.add_inv_capacity(desired_ic)
        
        for item in buy_list:
            self.buy(item, usdrate)

    def get_handle_with_xpath(self, xpath):
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            logger.debug(self.driver.title)
            self.wait.until(ec.presence_of_all_elements_located)
            if len(self.driver.find_elements_by_xpath(xpath)):
                return handle
        raise ValueError('cannot find xpath: {0} in {1} handles'.format(xpath, len(self.driver.window_handles)))

    def add_inv_capacity(self, ic):
        logger.info('adding investment capacity {0} JPY'.format(ic))
        self.driver.get(self.get_sbi_url('add_inv_capacity'))
        logger.debug(self.driver.title)
        #self.wait.until(ec.presence_of_all_elements_located)
        #self.driver.find_element_by_xpath('//*[@id="MAINAREA01"]/div[5]/div/div/div/div/table/tbody/tr/td[3]/ul/li[1]').click() #入金
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element_by_xpath('//*[@id="MAINAREA02_780"]/div[4]/ul/form[1]/li/a').click() #住信SBI銀行
        self.wait.until(ec.presence_of_all_elements_located)
        self.send_to_element('//*[@name="FML_TRANSFER_AMOUNT"]', str(ic))
        self.send_to_element('//*[@name="transefer_pass"]', os.environ['SBI_TRADE_PASS'])
        self.driver.find_element_by_xpath('//*[@id="MAINAREA02_780"]/form/div[2]/ul/li[1]/a/input').click()
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element_by_xpath('//*[@id="MAINAREA02_780"]/div[4]/ul/li[1]/form/a/input').click()
        self.wait.until(ec.presence_of_all_elements_located)
        logger.debug('processing bank...')
        time.sleep(5)

        handle = self.driver.current_window_handle
        self.driver.switch_to.window(self.get_handle_with_xpath('//*[@id="sbi-login"]'))
        self.title_check('即時決済サービス(ログイン)｜住信SBIネット銀行')
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element_by_xpath('//*[@class="neo-sbiLogo"]').click()
        time.sleep(1)
        self.send_to_element('//*[@id="userName"]', os.environ['SBI_BANK_ID'])
        self.send_to_element('//*[@id="loginPwdSet"]', os.environ['SBI_BANK_PASS'])
        self.driver.find_element_by_xpath('/html/body/app/div/ng-component/div/main/ng-component/div/form/section/div/ul/li/nb-button-login').click()
        self.wait.until(ec.presence_of_all_elements_located)
        time.sleep(5)
        self.title_check('即時決済サービス(確認)｜住信SBIネット銀行')
        # 出勤口座の選択は行わない (デフォルトで普通預金口座)
        if len(self.driver.find_elements_by_xpath('//*[@id="toriPwd"]')) == 0:
            self.driver.find_element_by_xpath('/html/body/app/div/ng-component/div/main/ng-component/div/form/section/div/div[3]/p/a/span').click() #キャンセル
            self.wait.until(ec.presence_of_all_elements_located)
            raise RuntimeError('failed login to SBIBANK')
        self.send_to_element('//*[@id="toriPwd"]', os.environ['SBI_BANK_TRADE_PASS'])
        self.driver.find_element_by_xpath('/html/body/app/div/ng-component/div/main/ng-component/section[2]/div/ul/li/nb-button/a').click()
        time.sleep(5)
        self.wait.until(ec.presence_of_all_elements_located)
        logger.debug('processed bank wallet')
        self.driver.switch_to.window(handle) #元のウインドウに戻る
        logger.debug('added investment capacity {0} JPY'.format(ic))
        simpleslack.send_to_slack(':moneybag:買付余力を増やしました({0}円)'.format(ic))

    def buy(self, item, usdrate):
        logger.info('buy {0}({1} USD) x {2} = {3} (USD rate: {4})'.format(item['brand'], item['price'], item['qty'], item['price'] * item['qty'], usdrate))
        self.driver.get(self.get_sbi_url('global_trade'))
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.get('https://global.sbisec.co.jp/Fpts/kbt/fbOrder/')
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element_by_xpath('//*[@id="main"]/div[4]/table[1]/tbody/tr[1]/td/label[1]').click() #買付
        self.driver.find_element_by_xpath('//*[@id="main"]/div[4]/table[2]/tbody/tr[2]/td/table/tbody/tr[1]/td/div/div[1]/label').click() #指値
        self.driver.find_element_by_xpath('//*[@id="main"]/div[4]/table[2]/tbody/tr[3]/td/div/label[1]').click() #当日中
        self.driver.find_element_by_xpath('//*[@id="main"]/div[4]/table[2]/tbody/tr[4]/td/label[1]').click() #一般預かり
        self.driver.find_element_by_xpath('//*[@id="main"]/div[4]/table[2]/tbody/tr[5]/td/label[2]').click() #円貨
        self.send_to_element('//*[@name="ticker"]', item['brand']) #ティッカー
        self.send_to_element('//*[@name="shares"]', "{0}".format(item['qty'])) #口数
        price_dollar = "{0}".format(item['price'].quantize(Decimal('1.'), rounding=ROUND_DOWN))
        self.send_to_element('//*[@name="priceDollar"]', price_dollar)
        price_cent = "{0}".format(((item['price'] - item['price'].quantize(Decimal('1.'), rounding=ROUND_DOWN)) * Decimal('100')).quantize(Decimal('1.'), rounding=ROUND_DOWN))
        self.send_to_element('//*[@name="priceCent"]', price_cent)
        self.send_to_element('//*[@name="password"]', os.environ['SBI_TRADE_PASS'])
        self.driver.find_element_by_xpath('//*[@name="tranConfirm"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element_by_xpath('//*[@name="tranAccept"]').click()
        logger.info('bought {0}({1} USD) x {2} = {3} (USD rate: {4})'.format(item['brand'], item['price'], item['qty'], item['price'] * item['qty'], usdrate))
        simpleslack.send_to_slack(':moneybag:{0}(単価${1})を{2}口購入しました(合計金額${3}/レート$1={4}円)'.format(item['brand'], item['price'], item['qty'], item['price'] * item['qty'], usdrate))

    def get_inv_capacity(self):
        self.driver.get(self.get_sbi_url('inv_capacity'))
        return self.to_number(self.driver.find_element_by_xpath('/html/body/div/table/tbody/tr/td[1]/table/tbody/tr[2]/td/form/table[2]/tbody/tr[1]/td[2]/table[10]/tbody/tr/td/table/tbody/tr[17]/td[2]/font').text)

    def title_check(self, title):
        if self.driver.title != title:
            raise AssertionError('title must be {0} but {1}'.format(title, self.driver.title))

    def check_etf(self, link):
        self.driver.execute_script("window.open()")
        self.driver.switch_to.window(self.driver.window_handles[1])
        self.driver.get(link)
        detail = self.driver.find_element_by_xpath('//*[@id="main"]/div[3]/table/tbody/tr[2]/td/table/tbody/tr/td[3]/font/a').get_attribute("textContent")[:3]
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0]) 
        return detail == 'ETF'

    def to_number(self, text):
        return text.replace(',','').replace(' ','').replace('\n',' ').replace('+','')

    def to_number_array(self, text):
        result = re.match('[^0-9\-\.]*([0-9\-\.]+)[^0-9\-\.]+([0-9\-\.]+)', self.to_number(text))
        if result is None:
            raise AssertionError('cannot parse for number array: {0}'.format(text))
        else:
            return [result.group(1), result.group(2)]

    def to_brand(self, text):
        result = re.match('([A-Z]*)[^A-Z].*', text)
        if result is None:
            raise AssertionError('cannot parse for brand: {0}'.format(text))
        else:
            return result.group(1)

if __name__ == "__main__":
    if "LOG_LEVEL" in os.environ:
        logzero.loglevel(int(os.environ["LOG_LEVEL"]))
    sbi = SbiTrade()
    try:
        sbi.db_init()
        sbi.init()
        sbi.login()
        sbi.portfolio()
    finally:
        sbi.close()
