from unittest import TestCase
from wnf.sbi import SbiTrade


class SbiTest(TestCase):
    def test_login_and_trade(self):
        sbi = SbiTrade()
        try:
            sbi.login()
            sbi.portfolio()
            sbi.trade()
        finally:
            sbi.close()
