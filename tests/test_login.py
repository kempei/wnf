from unittest import TestCase
from wnf.sbi import SbiTrade

class LoginTest(TestCase):
    def test_sbi_login(self):
        sbi = SbiTrade()
        sbi.init()
        sbi.login()
        sbi.close()

