import time as t
from datetime import datetime, timedelta, time

import dateutil.parser
import pandas_ta as ta

from trading_bot.settings import logger, TZ


class TSP:
    def __init__(self, client, local_symbol, unique_id_1, unique_id_2, below_vwap_per, above_vwap_std_per,
                 standard_deviation, start_time, end_time, day_down_percent, below_vwap_std_per, calc_method='pta',
                 contract_fetched=False):
        self.client = client
        self.local_symbol = local_symbol
        self.contract_id = unique_id_1
        self.id_2 = unique_id_2
        self.start_time = start_time
        self.end_time = end_time
        self.day_down_percent = day_down_percent
        self.below_vwap_std_per = below_vwap_std_per
        self.contract_fetched = contract_fetched
        self.ticker, self.sec_type, self.curr, self.exch = self.local_symbol.split()
        self.below_vwap_per = below_vwap_per
        self.above_vwap_std_per = above_vwap_std_per
        self.standard_deviation = standard_deviation
        self.calc_method = calc_method
        self.opt_type = 'C'
        self.today_open = None
        self.more_logs = False
        self.more_logs_time = None
        if not self.contract_fetched:
            self.log_info()

    def log_info(self):
        logger.debug(f"""Strategy instance started, symbol: {self.local_symbol}, start_time: {self.start_time}, 
                         end_time: {self.end_time}, day down percent: {self.day_down_percent}, 
                         below_vwap_std_per: {self.below_vwap_std_per}, below_vwap_per: {self.below_vwap_per}, 
                         above_vwap_std_per: {self.above_vwap_std_per}, 
                         standard_deviation multiplier: {self.standard_deviation}""")

    def print_more_logs(self, msg):
        if self.more_logs:
            logger.info(msg)

    @staticmethod
    def calculate_vwap_bands(df, curr_date, num_days):
        key = 'vwap'

        def stdev(df):
            return df[key].values.std(ddof=0)

        curr_position = datetime.combine(curr_date, time(hour=9, minute=31))
        df.loc[str(curr_position), 'UPPER_VWAP'] = None
        df.loc[str(curr_position), 'LOWER_VWAP'] = None
        df.loc[str(curr_position), 'STD_VWAP'] = None
        for _ in range(0, num_days):
            day_data = df[curr_date == df.index.date].copy()
            for _ in range(31, 60):
                try:
                    std = stdev(day_data[day_data.index.time <= curr_position.time()])
                    df.loc[str(curr_position), 'UPPER_VWAP'] = df.loc[str(curr_position), key] + (2 * std)
                    df.loc[str(curr_position), 'LOWER_VWAP'] = df.loc[str(curr_position), key] - (2 * std)
                    df.loc[str(curr_position), 'STD_VWAP'] = std
                except:
                    pass
                curr_position += timedelta(minutes=1)
            for _ in range(10, 17):
                while True:
                    if curr_position.time() >= time(hour=16, minute=1):
                        break
                    std = stdev(day_data[day_data.index.time <= curr_position.time()])
                    try:
                        df.loc[str(curr_position), 'UPPER_VWAP'] = df.loc[str(curr_position), key] + (2 * std)
                        df.loc[str(curr_position), 'LOWER_VWAP'] = df.loc[str(curr_position), key] - (2 * std)
                        df.loc[str(curr_position), 'STD_VWAP'] = std
                    except:
                        pass
                    curr_position += timedelta(minutes=1)
            curr_position += timedelta(days=1)
            curr_position = curr_position.replace(hour=9, minute=31)

    def run(self):
        if self.more_logs_time is None or datetime.now(tz=TZ) > self.more_logs_time:
            self.more_logs_time = datetime.now(tz=TZ) + timedelta(seconds=60)
            self.more_logs = True
            logger.debug(f'{self.local_symbol}: printing more logs in this iteration, '
                         f'next more logs time: {self.more_logs_time}')
        else:
            self.more_logs = False

        if not len(self.client.data_frames[self.id_2]):
            return
        if self.ticker not in self.client.secContract_details_end:
            return

        df = self.client.data_frames[self.id_2]
        if self.today_open is None:
            try:
                today_data = df[df.index.date == datetime.now(tz=TZ).date()]
            except ValueError as e:
                return
            if len(today_data):
                self.today_open = today_data.iloc[0]['open']
            else:
                return

        try:
            last_price = df.iloc[-1]['close']
            df['volume'] = df['volume'].astype(int)
            df['vwap'] = ta.vwap(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'])
            last_row = df.iloc[-1]
        except ValueError:
            return
        except Exception as e:
            logger.exception(e)
            t.sleep(3)
            return

        # vwap strategy
        vwap = last_row['vwap']

        if self.calc_method == 'pta':
            vwap_std = ta.stdev(close=df['close'])
            vwap_std = vwap_std.iloc[-1]
        else:
            try:
                num_days = df.index.normalize().nunique()
                self.calculate_vwap_bands(df=df, curr_date=datetime.now(tz=TZ).date(), num_days=num_days)
                vwap_std = df['STD_VWAP'].iloc[-1]
            except Exception as e:
                logger.exception(e)
                t.sleep(3)
                return

        if str(vwap).lower() == 'nan' or str(vwap_std).lower() == 'nan':
            return

        vwap_below = vwap - ((self.below_vwap_per * vwap) / 100)
        vwap_std_below = (vwap - (self.standard_deviation * vwap_std)) * (1 + (self.above_vwap_std_per / 100))
        final_value = min(vwap_below, vwap_std_below)
        self.print_more_logs(
            f'{self.local_symbol}: vwap: {vwap}, std: {vwap_std}, vwap_below: {vwap_below}, '
            f'vwap_std_val: {vwap_std_below}, final_value {final_value}, last_price : {last_price}')

        # Security should not be down more than 1 %
        if ((last_price - self.today_open) / self.today_open) * 100 < -self.day_down_percent:
            logger.info(f'{self.local_symbol}: is down more than {self.day_down_percent} % cant proceed further, '
                        f'stopping instance')
            self.contract_fetched = True
            return

        # Security should not be down more than below_vwap_std_per % from vwap_std_below
        if ((last_price - vwap_std_below) / vwap_below) * 100 < -self.below_vwap_std_per:
            self.print_more_logs(f'{self.local_symbol}: is down more than {self.below_vwap_std_per} % '
                                 f'from vwap_std_below: {vwap_std_below}, ltp: {last_price}, cant proceed further')
            return

        if datetime.now(tz=TZ).time() > self.end_time:
            logger.info(f'{self.local_symbol}: current time is after {self.end_time} Eastern, stopping instance')
            self.contract_fetched = True
            return

        # Strategy validate
        if last_price >= final_value:
            self.print_more_logs(f'{self.local_symbol}: last_price: {last_price} is greater than final_value: '
                                 f'{final_value}, cant proceed further')
            return

        # Time validate
        if datetime.now(tz=TZ).time() < self.start_time:
            self.print_more_logs(f'{self.local_symbol}: current time is not between {self.start_time} and '
                                 f'{self.end_time} Eastern')
            return

        self.contract_fetched = True
        logger.info(f'{self.local_symbol}: vwap: {vwap}, vwap_std: {vwap_std}, vwap_below: {vwap_below}, '
                    f'vwap_std_val: {vwap_std_below}, final_value {final_value}, last_price : {last_price}')

        try:
            # Strike finding
            expiries = sorted(self.client.contract_chain[self.ticker].keys())
            req_date = datetime.now(tz=TZ) + timedelta(days=0)
            expiries = sorted([dateutil.parser.parse(e).date() for e in expiries])
            expiry_found = [e for e in expiries if e >= req_date.date()]
            expiry_found = expiry_found[0].strftime('%Y%m%d')
            strikes = sorted(self.client.contract_chain[self.ticker][expiry_found])
        except Exception as e:
            logger.exception(e)
            return
        found_strike = None
        found_strike_index = None
        minn = float('inf')
        for i, strike in enumerate(sorted(strikes)):
            strike = float(strike)
            if strike % 1:
                continue
            if abs(strike - last_price) < minn:
                found_strike = strike
                found_strike_index = i
                minn = abs(strike - last_price)
        logger.info(f'{self.local_symbol}: found_strike: {found_strike}')

        contract = self.client.make_contract(symbol=self.ticker, sec_type='OPT', exch=self.exch, curr=self.curr,
                                             opt_type=self.opt_type, expiry_date=str(expiry_found),
                                             strike=float(found_strike))

        # Iterating till not found valid strike, sometimes tws server gives wrong strikes from server,
        # so for avoiding that
        for strike in sorted(strikes)[found_strike_index:]:
            contract = self.client.make_contract(symbol=self.ticker, sec_type='OPT', exch=self.exch, curr=self.curr,
                                                 opt_type=self.opt_type, expiry_date=str(expiry_found),
                                                 strike=float(strike))
            if self.client.validate_opt_contract(contract):
                break

        return contract
