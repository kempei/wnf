from wnf.scraper import DBScraper
import wnf.simpleslack as simpleslack

from logzero import logger
import logzero

from selenium.webdriver.remote.webelement import WebElement, By
from selenium.webdriver.support import expected_conditions as ec

import os, time, re

import math
from decimal import Decimal, ROUND_DOWN

from operator import add


class SbiTrade(DBScraper):
    def __init__(self) -> None:
        super().__init__()
        self.path_dict = {
            "backtohome": "?_ControlID=WPLEThmR001Control&_PageID=DefaultPID&_DataStoreID=DSWPLEThmR001Control&_ActionID=DefaultAID&getFlg=on",
            "inv_capacity": "?_ControlID=WPLETacR003Control&_PageID=DefaultPID&_DataStoreID=DSWPLETacR003Control&_SeqNo=1572738402951_default_task_39_DefaultPID_DefaultAID&getFlg=on&_ActionID=DefaultAID",
            "wallet": "?OutSide=on&_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&_PageID=WPLETsmR001Sdtl12&sw_page=BondFx&cat1=home&cat2=none&sw_param2=02_201&getFlg=on&int_pr1=150313_cmn_gnavi:2_dmenu_02",
            "add_inv_capacity": "?_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&sw_page=Banking&cat1=home&cat2=none&getFlg=on&int_ct=140318_in_btn_01",
            "global_trade": "?OutSide=on&_ControlID=WPLETsmR001Control&_DataStoreID=DSWPLETsmR001Control&sw_page=Foreign&cat1=home&cat2=none&sw_param1=GB&getFlg=on",
        }
        self.sbi_core_url = "https://www.sbisec.co.jp/ETGate/"
        self.direct_path_dict = {"bondlist": "https://global.sbisec.co.jp/account/assets"}

    def get_sbi_url(self, text):
        return f"{self.sbi_core_url}{self.path_dict[text]}"

    def login(self):
        sbi_id = self.config("sbi-id")
        sbi_pass = self.config("sbi-pass")

        self.driver.get(self.sbi_core_url)
        time.sleep(5)
        self.wait.until(ec.presence_of_all_elements_located)

        self.send_to_element('//*[@name="user_id"]', sbi_id)
        self.send_to_element('//*[@name="user_password"]', sbi_pass)
        self.driver.find_element(by=By.XPATH, value='//*[@name="ACT_login"]').click()
        time.sleep(5)
        self.wait.until(ec.presence_of_all_elements_located)
        mymenu = self.driver.find_elements(by=By.ID, value="mymenuSec")
        if not mymenu:
            # 重要なお知らせ
            title_text_elements = self.driver.find_elements(by=By.CLASS_NAME, value="title-text")
            if len(title_text_elements) == 0:
                raise ValueError("failed to log in.")
            if title_text_elements[0].text != "重要なお知らせ":
                raise ValueError(f"unknown message: {title_text_elements[0].text}")

            # 重要なお知らせのクリック
            form: WebElement = self.driver.find_element(by=By.NAME, value="FORM")
            link_elements: list[WebElement] = form.find_elements(by=By.XPATH, value="table//a")
            message = f":loudspeaker:重要なお知らせが{len(link_elements)}件届いています"
            links: list[str] = list()
            for link_element in link_elements:
                logger.info(f"Important information: {link_element.text}")
                links.append(link_element.get_attribute("href"))
                message += f"\n{link_element.text}"
            for link in links:
                logger.debug(f"get: {link}")
                self.driver.get(link)
                self.wait.until(ec.presence_of_all_elements_located)
                button_xpath = "//input[@type='submit']"
                button_element = self.driver.find_element(by=By.XPATH, value=button_xpath)[0]
                self.wait.until(ec.element_to_be_clickable(button_element))
                button_element.click()
                self.wait.until(ec.presence_of_all_elements_located)
            simpleslack.send_to_slack(message)
            # 再度メインページへ遷移
            self.driver.get(self.sbi_core_url)
            mymenu = self.driver.find_elements(by=By.ID, value="mymenuSec")
            if not mymenu:
                raise ValueError("failed to log in after clinking important information.")

        logger.info(f"successfully logged in. current_url = {self.driver.current_url}")
        self.sbi_core_url = self.driver.current_url

    def portfolio(self):
        logger.info("starting sbi portfolio")

        self.begin_transaction()

        log_date = self.get_local_date()
        logger.info(f"inserting data as {log_date}")
        if self.existance_check("sbi_portfolio", ["log_date"], [log_date.isoformat()]):
            self.conn.execute("DELETE FROM sbi_portfolio WHERE log_date = ?", (log_date.isoformat(),))
            self.conn.execute("DELETE FROM sbi_portfolio_detail WHERE log_date = ?", (log_date.isoformat(),))
            logger.info("deleted today's data for inserting new one")

        # 買付余力
        inv_capacity_jpy = self.get_inv_capacity()

        # 外貨建て口座 - 保有証券
        self.driver.get(self.get_sbi_url("global_trade"))  # 外貨建商品取引へ移動
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.get(self.direct_path_dict["bondlist"])  # 外貨建商品取引 - 保有証券・資産 (米国)
        self.wait.until(ec.presence_of_all_elements_located)
        lis = self.driver.find_elements(by=By.XPATH, value='//ul[contains(@class, "grid-table")]/li[@class="css-hopsx2"]/div/div/../..')
        if len(lis) == 0:
            self.print_html()
            raise AssertionError(f"no information at assets. - {self.direct_path_dict['bondlist']}")
        usdrate = self.driver.find_element(by=By.XPATH, value='//ul[contains(@class, "grid-table")]/../div[@class="wd-1-2"]/div/ul/li[2]/span').get_attribute("textContent")
        total_jpy = 0
        total_usd = 0
        detail_data: dict = {}
        for li in lis:
            divs = li.find_elements(by=By.XPATH, value='div[contains(@class, "table-item")]')
            if len(divs) == 0:
                continue
            ticker = divs[0].find_element(by=By.TAG_NAME, value="div").get_attribute("data-security-code")
            if self.check_etf(ticker):
                logger.debug(f"checking {ticker}...")
            else:
                logger.debug(f"skipped (not ETF): {ticker}")
                continue
            qty_text = divs[2].find_element(by=By.XPATH, value="div/p[1]").get_attribute("textContent")
            qty = self.to_number(qty_text)
            price_usd = self.to_number(divs[1].find_element(by=By.XPATH, value="div/p[1]").get_attribute("textContent"))
            amount_usd = self.to_number(divs[5].find_element(by=By.XPATH, value="div/p[1]").get_attribute("textContent"))
            amount_jpy = self.to_number(divs[5].find_element(by=By.XPATH, value="div/p[2]").get_attribute("textContent"))
            total_jpy += int(amount_jpy)
            total_usd += float(amount_usd)
            amount_usd_delta = self.to_number(divs[6].find_element(by=By.XPATH, value="div/p[1]").get_attribute("textContent"))
            amount_jpy_delta = self.to_number(divs[6].find_element(by=By.XPATH, value="div/p[2]").get_attribute("textContent"))

            dict_key = (log_date.isoformat(), ticker)
            if not dict_key in detail_data:
                detail_data[dict_key] = [float(0), 0, 0, 0, float(0), float(0)]
            current_data = [float(price_usd), int(qty), int(amount_jpy), int(amount_jpy_delta), float(amount_usd), float(amount_usd_delta)]
            detail_data[dict_key] = list(map(add, detail_data[dict_key], current_data))

        for key, value in detail_data.items():
            combined_value = key + tuple(value)
            self.conn.execute(
                "INSERT INTO sbi_portfolio_detail (log_date, brand, price_usd, qty, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", combined_value
            )
        logger.info(f"inserted sbi_portfolio_detail for {log_date}")

        self.conn.execute(
            "INSERT INTO sbi_portfolio (log_date, usdrate, total_amount_jpy, total_amount_usd, inv_capacity_jpy) VALUES (?, ?, ?, ?, ?)",
            (
                log_date.isoformat(),
                float(usdrate),
                int(total_jpy),
                float(total_usd),
                int(inv_capacity_jpy),
            ),
        )

        logger.info("inserted sbi_portfolio for {0}".format(log_date))

        self.commit_transaction()

    def __exist_current_orders(self):
        self.driver.get(self.get_sbi_url("global_trade"))
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.get("https://global.sbisec.co.jp/refer/us/stock")
        self.wait.until(ec.presence_of_all_elements_located)
        time.sleep(5)
        lis = self.driver.find_elements(by=By.XPATH, value='//div[@id="refer-stock"]/div/ul/li')
        if len(lis) == 0:
            logger.debug("no today's orders.")
            return False
        for li in lis:
            status_text = li.find_element(by=By.XPATH, value="div[2]").get_attribute("textContent")
            if not status_text in ("取消済", "注文状況"):
                logger.debug(f"detected {status_text}")
                return True
        return False

    def trade(self):
        if self.__exist_current_orders():
            logger.info("already ordered. no orders in this transaction.")
            return

        logger.info("starting sbi trade")
        log_date = self.get_local_date()

        check_sql = """SELECT *
FROM (SELECT COUNT(*) FROM wn_portfolio where log_date = ?) w
   , (SELECT COUNT(*) FROM sbi_portfolio where log_date = ?) s"""
        cursor = self.conn.cursor()
        rows = list(cursor.execute(check_sql, (log_date.isoformat(), log_date.isoformat())))
        logger.debug(f"WN count = {rows[0][0]}, SBI count = {rows[0][1]}")
        assert int(rows[0][0]) == 1 and int(rows[0][1]) == 1

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
WHERE m_log_date = ?
  AND brand != 'CASH'"""
        cursor = self.conn.cursor()
        rows = list(cursor.execute(diff_sql, (log_date.isoformat(),)))
        buy_list = []
        for row in rows:
            brand: str = row[4]
            usdrate: float = float(row[0])
            wn_qty: int = int(row[2])
            sbi_qty: int = int(row[3])
            diff_qty: int = wn_qty - sbi_qty
            flag: str = ""
            if diff_qty >= 1:
                buy_list.append({"brand": brand, "qty": diff_qty})
                flag = "*"
            logger.debug(f"{flag}{brand}: WN={wn_qty}, SBI={sbi_qty}, diffrence={diff_qty}, usdrate={usdrate}")

        if len(buy_list) > 0:
            self.buy_from_list(buy_list, usdrate)

    def buy_from_list(self, buy_list, usdrate):
        # make price list
        for item in buy_list:
            item["price"] = self.get_brand_price(item["brand"])

        # calc inv. capacity
        required_ic: float = 0
        for item in buy_list:
            required_ic += item["price"] * item["qty"] * usdrate
        required_ic += required_ic * 0.06  # 手数料0.49%と為替分を加味して6%を足しておく
        required_ic = int(math.ceil(required_ic))  # 切り上げ
        current_ic: int = int(self.get_inv_capacity())
        desired_ic = required_ic - current_ic
        logger.info(f"current investment capacity: {current_ic}, required: {required_ic}, desired: {desired_ic}")
        if desired_ic > 0:
            if desired_ic < 1000:
                desired_ic = 1000
            self.add_inv_capacity(desired_ic)

        for item in buy_list:
            self.buy(item, usdrate)

    def add_inv_capacity(self, ic):
        logger.info("adding investment capacity {0} JPY".format(ic))
        self.driver.get(self.get_sbi_url("add_inv_capacity"))
        logger.debug(self.driver.title)
        self.wait.until(ec.presence_of_all_elements_located)
        self.send_to_element('//input[@id="ReceiptInputLabel-input"]', str(int(ic)))
        self.send_to_element('//input[@aria-label="tadepassword"]', self.config("sbi-trade-pass"))
        self.driver.find_element(by=By.XPATH, value='//button[text()="入金指示確認"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element(by=By.XPATH, value='//button[@id="targetButton"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        time.sleep(5)

        handle = self.driver.current_window_handle
        self.driver.switch_to.window(self.get_handle_with_xpath('//*[@id="sbi-login"]'))
        self.title_check("即時決済サービス(ログイン)｜住信SBIネット銀行")
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.find_element(by=By.XPATH, value='//*[@id="sbi-login"]/..').click()  # 口座支店名を選択
        time.sleep(1)
        self.send_to_element('//*[@name="userNameNewLogin"]', self.config("sbi-bank-id"))
        self.send_to_element('//*[@id="loginPwdSet"]', self.config("sbi-bank-pass"))
        self.driver.find_element(by=By.XPATH, value='//*[@nblabel="ログイン"]').click()
        self.wait.until(ec.presence_of_all_elements_located)
        time.sleep(5)

        self.title_check("即時決済サービス(確認)｜住信SBIネット銀行")
        # 出金口座の選択は行わない (デフォルトで普通預金口座)
        if len(self.driver.find_elements(by=By.XPATH, value='//*[@id="toriPwd"]')) == 0:
            self.driver.find_element(by=By.XPATH, value="/html/body/app/div/ng-component/div/main/ng-component/div/form/section/div/div[3]/p/a/span").click()  # キャンセル
            self.wait.until(ec.presence_of_all_elements_located)
            raise RuntimeError("failed login to SBIBANK")
        self.send_to_element('//*[@id="toriPwd"]', self.config("sbi-bank-trade-pass"))
        self.driver.find_element(by=By.XPATH, value="/html/body/app/div/ng-component/div/main/ng-component/section[2]/div/ul/li/nb-button/a").click()
        time.sleep(5)

        self.wait.until(ec.presence_of_all_elements_located)
        logger.debug("processed bank wallet")
        self.driver.switch_to.window(handle)  # 元のウインドウに戻る
        logger.debug("added investment capacity {0} JPY".format(ic))
        simpleslack.send_to_slack(":moneybag:買付余力を増やしました({0}円)".format(ic))

    def buy(self, item, usdrate):
        # NISA 投資枠の確認
        self.driver.get(self.get_sbi_url("global_trade"))
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.get("https://global.sbisec.co.jp/account/summary")
        self.wait.until(ec.presence_of_all_elements_located)
        time.sleep(5)
        nisa_capacity = int(self.to_number(self.driver.find_element(by=By.XPATH, value='//ul[@id="nisa-buy-table"]/li/div[2]').get_attribute("textContent")))
        yen_total_limit = int(item["price"] * item["qty"] * usdrate) + 1

        # 購入
        logger.info(f'buy {item["brand"],}({item["price"]} USD) x {item["qty"]} = {item["price"] * item["qty"]} (USD rate: {usdrate}) = {yen_total_limit}円 / NISA残り枠 {nisa_capacity}円')
        self.driver.get(self.get_sbi_url("global_trade"))
        self.wait.until(ec.presence_of_all_elements_located)
        self.driver.get("https://global.sbisec.co.jp/trade/spot/us")
        self.wait.until(ec.presence_of_all_elements_located)

        self.driver.find_element(by=By.XPATH, value='//label[@for="buy"]').click()  # 現物買付
        self.driver.find_element(by=By.XPATH, value='//label[@for="limit"]').click()  # 指値
        self.send_to_element('//label[@for="limit"]/../div//input', str(item["price"]))  # 指値値

        self.driver.find_element(by=By.XPATH, value='//label[@for="today"]').click()  # 当日中

        self.driver.find_element(by=By.XPATH, value='//label[@for="yen"]').click()  # 円貨
        self.send_to_element('//span[@class="i-minus"]/../../input', str(item["qty"]))  # 口数

        self.send_to_element('//input[@id="trade-password"]', self.config("sbi-trade-pass"))  # 取引パスワード

        self.send_to_element('//input[@id="stock-ticker"]', item["brand"])  # ティッカー
        self.driver.find_element(by=By.XPATH, value='//button[@data-ga-button="ticker"]').click()  # 表示ボタンをクリックして NISA が可能かを判定させる
        time.sleep(1)

        nisa_option_button = self.driver.find_elements(by=By.XPATH, value='//label[@for="growth-investment"]')
        if nisa_capacity >= yen_total_limit and len(nisa_option_button) > 0:  # NISA選択肢がない場合を考慮 (債権など)
            nisa_option_button[0].click()  # NISA預かり(2023年新NISA 成長株)
        else:
            self.driver.find_element(by=By.XPATH, value='//label[@for="specific"]').click()  # 特定預かり

        self.driver.find_element(by=By.XPATH, value='//button[@id="password-button"]').click()
        self.wait.until(ec.presence_of_all_elements_located)

        self.driver.find_element(by=By.XPATH, value='//button[@data-ga-button="trade_order"]').click()  # 注文発注

        logger.info(f'bought {item["brand"]}({item["price"]} USD) x {item["qty"]} = {item["price"] * item["qty"]} (USD rate: {usdrate})')
        simpleslack.send_to_slack(f':moneybag:{item["brand"]}(単価${item["price"]})を{item["qty"]}口購入しました(合計金額${item["price"] * item["qty"]}/レート$1={usdrate}円)')

    def get_inv_capacity(self) -> str:
        self.driver.get(self.get_sbi_url("inv_capacity"))
        return self.to_number(
            self.driver.find_element(
                by=By.XPATH, value="/html/body/div/table/tbody/tr/td[1]/table/tbody/tr[2]/td/form/table[2]/tbody/tr[1]/td[2]/table[10]/tbody/tr/td/table/tbody/tr[17]/td[2]/font"
            ).text
        )

    def check_etf(self, ticker: str):
        self.driver.execute_script("window.open()")
        time.sleep(1)
        self.driver.switch_to.window(self.driver.window_handles[1])
        self.driver.get(f"https://global.sbisec.co.jp/invest/us/stock/{ticker}")
        time.sleep(1)
        etf_button_count = len(self.driver.find_elements(by=By.XPATH, value='//button[@data-ga-tab="etfInformation"]'))
        self.driver.close()
        time.sleep(1)
        self.driver.switch_to.window(self.driver.window_handles[0])
        return etf_button_count > 0

    def to_number(self, text):
        return text.replace(",", "").replace(" ", "").replace("\n", " ").replace("+", "").replace("円", "").replace("USD", "")

    def to_number_array(self, text):
        result = re.match(r"[^0-9\-\.]*([0-9\-\.]+)[^0-9\-\.]+([0-9\-\.]+)", self.to_number(text))
        if result is None:
            raise AssertionError(f"cannot parse for number array: {text}")
        else:
            return [result.group(1), result.group(2)]

    def to_brand(self, text):
        result = re.match("([A-Z]*)[^A-Z].*", text)
        if result is None:
            raise AssertionError(f"cannot parse for brand: {text}")
        else:
            return result.group(1)


if __name__ == "__main__":
    if "LOG_LEVEL" in os.environ:
        logzero.loglevel(int(os.environ["LOG_LEVEL"]))
    sbi = SbiTrade()
    try:
        sbi.login()
        sbi.portfolio()
    finally:
        sbi.close()
