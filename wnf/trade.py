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
        if not "SKIP_WN" in os.environ:
            logger.info('started collecting WealthNavi data')
            wn = WealthNavi()
            try:
                wn.db_init()
                wn.init()
                wn.login()
                wn.portfolio()
            finally:
                wn.close()

        if not "SKIP_SBI" in os.environ:
            logger.info('started collecting SBITRADE data')
            sbi = SbiTrade()
            try:
                sbi.db_init()
                sbi.init()
                sbi.login()
                sbi.portfolio()
            finally:
                sbi.close()
    
        if not "SKIP_TRADE" in os.environ:
            logger.info('started trading via SBITRADE')
            sbi = SbiTrade()
            try:
                sbi.db_init()
                sbi.init()
                sbi.login()
                sbi.trade()
            finally:
                sbi.close()
        
        elapsed_time = int(time.time() - start)
        simpleslack.send_to_slack(':high_brightness:正常に終了しました (処理時間={0}秒)'.format(elapsed_time))
    except:
        import traceback
        simpleslack.send_to_slack(':x:エラーが発生しました\n\n```\n{0}\n```'.format(traceback.format_exc()))
        raise
