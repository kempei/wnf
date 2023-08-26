from unittest import TestCase
from wnf.wnf import WealthNavi


class WealthNaviTest(TestCase):
    def test_login_and_portfolio(self):
        wn = WealthNavi()
        try:
            wn.login()
            wn.portfolio()
        finally:
            wn.close()

    def test_force_importance_page(self):
        wn = WealthNavi()
        try:
            wn.login(True)
            raise RuntimeError("invalid processing.")
        except:
            pass
        finally:
            wn.close()
