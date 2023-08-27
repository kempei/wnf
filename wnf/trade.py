from wnf.wnf import WealthNavi
from wnf.sbi import SbiTrade
import wnf.simpleslack as simpleslack

from logzero import logger
import logzero, os, time

if __name__ == "__main__":
    start = time.time()

    if "LOG_LEVEL" in os.environ:
        logzero.loglevel(int(os.environ["LOG_LEVEL"]))

    try:
        logger.info("started collecting WealthNavi data")
        wn = WealthNavi()
        try:
            wn.login()
            wn.portfolio()
        except:
            wn.store_html_to_s3("wn_error")
            raise
        finally:
            wn.close()

        logger.info("started collecting SBITRADE data")
        sbi = SbiTrade()
        try:
            sbi.login()
            sbi.portfolio()
        except:
            sbi.store_html_to_s3("sbi_portfolio_error")
            raise
        finally:
            sbi.close()

        logger.info("started trading via SBITRADE")
        sbi = SbiTrade()
        try:
            sbi.login()
            sbi.trade()
        except:
            sbi.store_html_to_s3("sbi_trade_error")
            raise
        finally:
            sbi.close()

        elapsed_time = int(time.time() - start)
        simpleslack.send_to_slack(":high_brightness:正常に終了しました (処理時間={0}秒)".format(elapsed_time))
    except:
        import traceback

        simpleslack.send_to_slack(":x:エラーが発生しました\n\n```\n{0}\n```".format(traceback.format_exc()))
        raise
