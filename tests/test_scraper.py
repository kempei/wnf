from unittest import TestCase
from wnf.scraper import Scraper, DBScraper
import wnf.simpleslack as simpleslack

import os


class ScraperTest(TestCase):
    def test_selenium(self):
        scraper = Scraper()
        scraper.driver.get("http://www.yahoo.co.jp")

    def test_db(self):
        try:
            os.remove(f"/tmp/{DBScraper.DB_NAME}")
        except:
            pass
        scraper = DBScraper()
        scraper.conn.execute("BEGIN TRANSACTION wnf_portfolio")
        scraper.conn.execute("SELECT * FROM sbi_portfolio")
        scraper.conn.execute(
            "INSERT INTO wn_portfolio (log_date, usdrate, total_amount_jpy, total_amount_usd, total_deposit_jpy, total_withdraw_jpy) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "2100-01-01",
                0,
                0,
                0,
                0,
                0,
            ),
        )
        assert scraper.existance_check("wn_portfolio", ["log_date"], ["2100-01-01"])
        scraper.conn.execute("ROLLBACK TRANSACTION wnf_portfolio")
        assert not scraper.existance_check("wn_portfolio", ["log_date"], ["2100-01-01"])

    def test_slack(self):
        simpleslack.send_to_slack("slack unittest")
