import time as t
from datetime import datetime

import schedule

from trading_bot.controller import run
from trading_bot.settings import TZ


def is_holiday():
    today = datetime.now(tz=TZ).date()
    if today.weekday() >= 5:
        return True
    return False


def scheduled_run():
    if not is_holiday():
        from main import symbols, account_mode
        run(symbols=symbols, account_mode=account_mode, cycle='C')


# Set time in HH:MM format for daily run
# Schedule update for trading
schedule.every().day.at("09:35:00").do(scheduled_run)

while True:
    # Checks whether a scheduled task
    # is pending to run or not
    schedule.run_pending()
    t.sleep(1)
