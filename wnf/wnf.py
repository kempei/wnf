from wnf.scraper import DBScraper
import wnf.simpleslack as simpleslack

from logzero import logger
import logzero

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.remote.webelement import By, WebElement

import os, datetime, re

# 対象: 購入 リバランス DeTax


class WealthNavi(DBScraper):
    def __init__(self) -> None:
        super().__init__()
        self.target_type = {
            "DeTAX（税金最適化）": "DETAX",
            "購入": "BUY",
            "売却": "SELL",
        }
        self.nontarget_type = [
            "リバランス",
            "分配金",
            "クイック入金",
            "積立",
            "手数料",
            "資産運用開始キャンペーン",
            "積立開始キャンペーン",
            "入金",
        ]
        self.usdrate: str = None
        self.total_jpy: str = None
        self.total_usd: str = None
        self.history_usdrate: str = None

    def login(self, __force_important_page_for_test: bool = False):
        IMPORTANT_PAGE_TITLE = "DUMMY IMPORTANT PAGE TITLE"
        retry_count: int = 0

        self.driver.execute_script("window.open()")
        wn_id = self.config("wealthnavi-id")
        wn_pass = self.config("wealthnavi-pass")

        while retry_count < 3:
            retry_count += 1
            self.driver.get("https://invest.wealthnavi.com")
            self.wait.until(ec.presence_of_all_elements_located)

            self.send_to_element('//*[@id="username"]', wn_id)
            self.send_to_element('//*[@id="password"]', wn_pass)
            self.driver.find_element(by=By.XPATH, value='//button[@name="action" and @data-action-button-primary="true"]').click()
            self.wait.until(ec.presence_of_all_elements_located)
            title = self.driver.title
            if __force_important_page_for_test:
                title = IMPORTANT_PAGE_TITLE
            if title == "ホーム : WealthNavi":
                logger.info("successfully logged in.")
                return
            elif title == IMPORTANT_PAGE_TITLE:
                logger.info(f"important page {title}")
                # TODO: 重要ページの表示とクリック
                logger.info(f"retrying...")
            else:
                logger.error(f"invalid title: {self.driver.title}")
                raise ValueError(f"failed to log in. title = {self.driver.title}")
        raise RuntimeError("Giving up to retry for logging into WealthNavi with impotant information page.")

    def portfolio(self):
        self.begin_transaction()
        try:
            self.__delete_duplicated_portfolio()
            self.__process_portfolio()
            self.__process_service()
            self.__process_transaction()
            self.commit_transaction()
        except Exception as e:
            self.rollback_transaction()
            logger.error("completed transaction rollback")
            raise e

    ############################################################

    def __delete_duplicated_portfolio(self):
        log_date = self.get_local_date()
        logger.info(f"inserting data as {log_date}")
        if self.existance_check("wn_portfolio", ["log_date"], [log_date.isoformat()]):
            self.conn.execute("DELETE FROM wn_portfolio WHERE log_date = ?", (log_date.isoformat(),))
            self.conn.execute("DELETE FROM wn_portfolio_detail WHERE log_date = ?", (log_date.isoformat(),))
            logger.info("deleted today's data for inserting new one")

    def __process_portfolio(self):
        self.driver.get("https://invest.wealthnavi.com/service/portfolio")
        logger.debug(f"title: {self.driver.title}")
        trs = self.driver.find_elements(by=By.XPATH, value='//*[@id="assets-class-data"]/tbody/tr')
        for tr in trs:
            self.__parse_portfolio_detail(tr)
        logger.info(f"inserted wn_portfolio_detail for {self.get_local_date()}")
        self.usdrate = self.driver.find_element(by=By.XPATH, value='//*[@id="assets-class-data"]/caption/span[1]').get_attribute("textContent")

    def __process_service(self):
        self.driver.get("https://invest.wealthnavi.com/service")
        logger.debug(f"title: {self.driver.title}")
        self.total_jpy = self.__to_number(self.driver.find_element(by=By.XPATH, value='//*[@id="content"]/div/div[3]/section/div/div/div[1]/div[1]/dl[1]/dt/span').get_attribute("textContent"))
        self.total_usd = self.__to_number(self.driver.find_element(by=By.XPATH, value='//*[@id="content"]/div/div[3]/section/div/div/div[1]/div[1]/dl[2]/dt/span').get_attribute("textContent"))

    def __process_transaction(self):
        self.driver.get("https://invest.wealthnavi.com/service/transaction")
        logger.debug(f"title: {self.driver.title}")

        # 総入金額
        total_deposit = self.__to_number(self.driver.find_element(by=By.XPATH, value='//*[@class="transaction-money"]/div[1]/dd/span').get_attribute("textContent"))
        # 総出金額
        total_withdraw = self.__to_number(self.driver.find_element(by=By.XPATH, value='//*[@class="transaction-money"]/div[2]/dd/span').get_attribute("textContent"))

        last_page = int(
            self.__to_number(
                self.driver.find_element(
                    by=By.XPATH,
                    value='//*[@id="content"]/div/div/nav/ul/li[last()]',
                ).get_attribute("textContent")
            )
        )
        logger.info(f"{last_page} pages in transactions")

        end_flag = False
        for page in range(1, last_page + 1):
            if end_flag:
                break
            self.driver.get(f"https://invest.wealthnavi.com/service/transaction/{page}")
            entry_list = self.driver.find_element(by=By.CLASS_NAME, value="history-timeline").find_elements(by=By.TAG_NAME, value="li")
            for entry in entry_list:
                history_type = entry.find_element(by=By.CLASS_NAME, value="assets-type").get_attribute("textContent")
                if history_type in self.target_type:
                    end_flag = self.__process_history_data(entry, history_type)
                elif history_type not in self.nontarget_type:
                    logger.warning(f'unknown history type "{history_type}"')
            logger.info(f"processed No.{page} page")

        self.conn.execute(
            "INSERT INTO wn_portfolio (log_date, usdrate, total_amount_jpy, total_amount_usd, total_deposit_jpy, total_withdraw_jpy) VALUES (?, ?, ?, ?, ?, ?)",
            (
                self.get_local_date().isoformat(),
                float(self.usdrate),
                int(self.total_jpy),
                float(self.total_usd),
                int(total_deposit),
                int(total_withdraw),
            ),
        )
        logger.info(f"inserted wn_portfolio for {self.get_local_date().isoformat()}")

    def __process_history_data(self, entry: WebElement, history_type: str) -> bool:
        if len(entry.find_elements(by=By.CLASS_NAME, value="assets-detail")) > 0:
            total_trade_jpy = self.__to_number(entry.find_element(by=By.CLASS_NAME, value="assets-detail").get_attribute("textContent"))
        else:
            total_trade_jpy = 0

        date_root = entry.find_element(by=By.CLASS_NAME, value="date")
        start_date = self.__to_date(date_root.find_element(by=By.XPATH, value="time").get_attribute("textContent"))
        end_date = self.__to_date(date_root.find_element(by=By.XPATH, value="span[2]/time").get_attribute("textContent"))
        logger.debug(f"{history_type} {start_date}-{end_date} {total_trade_jpy}")
        slack_text = f":dollar:{history_type}を{start_date.strftime('%m月%d日')}に実施しました(受取日={end_date.strftime('%m月%d日')})"
        if self.existance_check("wn_history", ["start_date", "history_type"], [start_date.isoformat(), self.target_type[history_type]]):
            logger.info(f"loop break at {start_date} {history_type}")
            return True

        content_list = entry.find_element(by=By.CLASS_NAME, value="history-item-content").find_elements(by=By.TAG_NAME, value="h2")

        for i in range(0, len(content_list)):
            trade_type = content_list[i].get_attribute("textContent")
            trs = content_list[i].find_elements(
                by=By.XPATH,
                value="following-sibling::table[1]/tbody/tr",
            )
            for tr in trs:
                slack_text += self.__parse_history_detail(tr, start_date, history_type, trade_type)

        self.conn.execute(
            "INSERT INTO wn_history (start_date, end_date, history_type, total_jpy, usdrate) VALUES (?, ?, ?, ?, ?)",
            (
                start_date.isoformat(),
                end_date.isoformat(),
                self.target_type[history_type],
                int(total_trade_jpy),
                float(self.history_usdrate),
            ),
        )

        slack_text += f"\n(為替レート 1ドル={self.history_usdrate}円)"
        simpleslack.send_to_slack(slack_text)
        return False

    def __parse_portfolio_detail(self, tr: WebElement):
        brand = self.__to_brand(tr.find_element(by=By.TAG_NAME, value="th").get_attribute("textContent"))  # 銘柄
        tds = tr.find_elements(by=By.TAG_NAME, value="td")
        jpy = self.__to_number(tds[0].get_attribute("textContent"))
        jpy_delta = self.__to_number(tds[1].get_attribute("textContent"))
        usd = self.__to_number(tds[2].get_attribute("textContent"))
        usd_delta = self.__to_number(tds[3].get_attribute("textContent"))
        if brand != "CASH":
            price_usd = self.get_brand_price(brand)
            qty = float(usd) / price_usd
        else:
            price_usd = 0
            qty = 0
        self.conn.execute(
            "INSERT INTO wn_portfolio_detail (log_date, brand, amount_jpy, amount_jpy_delta, amount_usd, amount_usd_delta, price_usd, qty) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self.get_local_date().isoformat(),
                brand,
                int(jpy),
                int(jpy_delta),
                float(usd),
                float(usd_delta),
                float(price_usd),
                float(qty),
            ),
        )
        logger.debug(f"inserting wn_portfolio_detail for {self.get_local_date().isoformat()}, {brand}, {jpy}, {jpy_delta}, {usd}, {usd_delta}, {price_usd}, {qty}")

    def __parse_history_detail(self, tr: WebElement, start_date: str, history_type: str, trade_type: str) -> str:
        spans = tr.find_elements(by=By.XPATH, value="th/span")
        history_brand = spans[1].get_attribute("textContent")
        trade_qty = self.__to_number(spans[2].text)
        brand_price_usd = self.__to_number(spans[3].get_attribute("textContent"))
        self.history_usdrate = spans[4].get_attribute("textContent")
        spans = tr.find_elements(by=By.XPATH, value="td/span")
        trade_jpy = self.__to_number(spans[0].get_attribute("textContent"))
        trade_usd = self.__to_number(spans[1].get_attribute("textContent"))
        logger.debug(f"{history_brand} {trade_qty} {brand_price_usd} {self.history_usdrate} {trade_jpy} {trade_usd}")
        self.conn.execute(
            "INSERT INTO wn_history_detail (start_date, history_type, trade_type, brand, brand_price_usd, trade_qty, trade_jpy, trade_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                start_date.isoformat(),
                self.target_type[history_type],
                self.target_type[trade_type],
                history_brand,
                float(brand_price_usd),
                float(trade_qty),
                int(trade_jpy),
                float(trade_usd),
            ),
        )
        return f"\n - {history_brand}を${brand_price_usd}で{trade_qty}口{trade_type}しました(合計${trade_usd})"

    ############################################################

    def __to_date(self, text) -> datetime.date:
        return datetime.datetime.strptime(text, "%Y年%m月%d日").date()

    def __to_number(self, text) -> str:
        ret = text.replace(",", "").replace("$", "").replace("¥", "").replace("+", "").replace(" ", "").replace("\n", "").strip()
        if ret == "-":
            return "0"
        return ret

    def __to_brand(self, text) -> str:
        stripped_text = text.replace("\n", "").strip()
        result = re.match(r".*\((.+)\)", stripped_text)
        if result is None:
            logger.debug(f"__to_brand: {text}")
            return "CASH"
        else:
            return result.group(1)


if __name__ == "__main__":
    if "LOG_LEVEL" in os.environ:
        logzero.loglevel(int(os.environ["LOG_LEVEL"]))
    wn = WealthNavi()
    try:
        wn.login()
        wn.portfolio()
    finally:
        wn.close()
