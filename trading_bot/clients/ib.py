import time
from collections import defaultdict

import pandas as pd
import pytz
from dateutil.parser import parse

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.decoder import TagValue
from ibapi.order import Order
from ibapi.wrapper import EWrapper
from trading_bot.settings import TZ, logger


class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.orders = []
        self.exec_orders = []
        self.positions = []
        self.total_amount = 0
        self.data = defaultdict(list)
        self.contract_data = dict()
        self.options_data = defaultdict(dict)
        self.subscribed_symbols = dict()
        self.extended_hours_data = True
        self.time_frame = '1 min'
        self.option_computations = dict()
        self.ticks_data = defaultdict()
        self.data_frames = defaultdict(pd.DataFrame)

        self.expiries = {}
        self.variables = {}
        self.multipler = {}
        self.trading_class = {}

        self.filled_open_order_Ids = []
        self.exec_details_end = []
        self.executed_orders_list = []
        self.tickers_to_local_symbols = {}
        self.ticker_to_conId = {}
        self.tickers_to_local_symbol = {}
        self.contract_chain = {}
        self.sec_id_to_local_symbol = {}
        self.secContract_details_end = list()

        self.error_ids = list()
        self.contract_details_end = list()
        self.ltp_contract_started = set()
        self.reqId_to_ltp = {}

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
        logger.info(f'The next valid order id is: {self.nextorderId}')

    def error(self, reqId, errorCode, errorString, foo=""):
        self.error_ids.append(reqId)
        logger.debug(f'Error: {errorCode}, {errorString}')

    def contractDetails(self, reqId: int, contractDetails):
        super().contractDetails(reqId, contractDetails)
        symbol = contractDetails.contract.symbol
        conid = contractDetails.contract.conId
        self.ticker_to_conId[symbol] = conid

    def contractDetailsEnd(self, reqId: int):
        super().contractDetailsEnd(reqId)
        logger.debug(f'contract details end for :{reqId}')
        self.contract_details_end.append(reqId)

    def validate_opt_contract(self, contract_to_varify):
        try:
            self.nextorderId += 1
            reqId = self.nextorderId
            self.reqContractDetails(reqId, contract_to_varify)
            # in seconds
            TIME_OUT = 15
            start_time = time.time()
            while reqId not in self.contract_details_end + self.error_ids:
                if time.time() - start_time > TIME_OUT:
                    logger.debug(f'Error: Time out for :{reqId}')
                    return False
                time.sleep(0.1)
            if reqId in self.contract_details_end:
                return True
            logger.debug(f'Error: Wrong Contract Defination for {reqId}')
            return False
        except Exception as e:
            logger.exception(e)

    def validate_hist_data_reqId(self, reqId):
        try:
            TIME_OUT = 25
            start_time = time.time()
            while reqId not in list(self.data_frames.keys()) + self.error_ids:
                if time.time() - start_time > TIME_OUT:
                    return False
                time.sleep(0.1)
            if reqId in self.data_frames:
                return True
            return False
        except Exception as e:
            logger.exception(e)
            return False

    def securityDefinitionOptionParameter(self, reqId: int, exchange: str, underlyingConId: int,
                                          tradingClass: str, multiplier: str, expirations, strikes):
        super().securityDefinitionOptionParameter(reqId, exchange, underlyingConId, tradingClass, multiplier,
                                                  expirations, strikes)
        data = {'underlying_symbol': tradingClass, 'lot_size': int(multiplier), 'strikes': list(strikes),
                'expiry_dates': sorted([parse(d).date() for d in expirations])}
        self.options_data[reqId][exchange] = data
        local_symbol = self.sec_id_to_local_symbol[reqId].split()
        ticker, sec_type, curr, exch = local_symbol
        if str(exch) == str(exchange):
            if ticker not in self.contract_chain:
                self.contract_chain[ticker] = {}
                for expiry in sorted(expirations):
                    self.contract_chain[ticker][expiry] = sorted(strikes)
            self.secContract_details_end.append(ticker)

    def historicalData(self, reqId, bar):

        date_str = bar.date if len(bar.date.split()) < 2 else bar.date.split()[0] + ' ' + bar.date.split()[1]
        data = {'datetime': parse(date_str).astimezone(pytz.timezone('US/Eastern')), 'open': bar.open,
                'high': bar.high, 'low': bar.low,
                'close': bar.close, 'volume': bar.volume}
        self.data[reqId].append(data)

    def historicalDataUpdate(self, reqId, bar):
        date_str = bar.date if len(bar.date.split()) < 2 else bar.date.split()[0] + ' ' + bar.date.split()[1]
        bar_date_time = parse(date_str).astimezone(TZ)

        data = {'open': bar.open, 'high': bar.high, 'low': bar.low, 'close': bar.close, 'volume': bar.volume}

        if not len(self.data_frames[reqId]):
            df = pd.DataFrame(self.data[reqId])
            del self.data[reqId]
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
            if not self.extended_hours_data:
                df = df.between_time('09:30', '15:59')
            self.data_frames[reqId] = df
            logger.debug(f'{reqId}: Historical Data fetched for id: {reqId}')

        self.data_frames[reqId].loc[bar_date_time] = data

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        df = pd.DataFrame(self.data[reqId])
        del self.data[reqId]
        df = df.set_index('datetime')
        self.data_frames[reqId] = df
        logger.debug(f'{reqId}: Historical Data fetched for id: {reqId}')

    def stop_streaming(self, reqId):
        super().cancelMktData(reqId)

    def orderStatus(self, orderId, status, filled, remaining, avgFullPrice, permId, parentId, lastFillPrice, clientId,
                    whyHeld, mktCapPrice):
        self.orders.append({'order_id': orderId, 'status': status, 'avg_price': avgFullPrice, 'filled': filled})

    def execDetails(self, reqId, contract, execution):
        self.exec_orders.append({'order_id': reqId, 'symbol': contract.symbol, 'exec_order_id': execution.orderId,
                                 'exec_avg_price': execution.avgPrice, 'exec_qty': execution.cumQty,
                                 'exec_time': parse(
                                     execution.time.split()[0] + ' ' + execution.time.split()[1]).astimezone(TZ)})
        # if execution.orderId in self.filled_open_order_Ids:
        #     d = {'symbol': contract.symbol, 'right': contract.right, 'ltp': execution.price, 'side': execution.side,
        #          'expiry': contract.lastTradeDateOrContractMonth, 'order_id': execution.orderId,
        #          'curr': contract.currency, 'exch': contract.exchange}
        #     # d=pd.DataFrame(d,index=[0])
        #     self.executed_orders_list.append(d)

    def execDetailsEnd(self, reqId: int):
        super().contractDetailsEnd(reqId)
        self.exec_details_end.append(reqId)

    def position(self, account: str, contract: Contract, position, avgCost: float):
        super().position(account, contract, position, avgCost)
        for pos in self.positions:
            if pos['symbol'] == contract.symbol:
                pos['position'] = position
                pos['avg_cost'] = avgCost
                break
        else:
            self.positions.append({'symbol': contract.symbol, 'position': position, 'avg_cost': avgCost})

    def accountSummary(self, reqId: int, account: str, tag: str, value: str, currency: str):
        super().accountSummary(reqId, account, tag, value, currency)
        if tag == 'TotalCashBalance':
            self.total_amount = float(value)

    def tickOptionComputation(self, reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega,
                              theta, undPrice):
        super().tickOptionComputation(reqId, tickType, tickAttrib, impliedVol, delta, optPrice, pvDividend, gamma, vega,
                                      theta, undPrice)
        if optPrice and tickType == 12:
            self.reqId_to_ltp[reqId] = optPrice

    @staticmethod
    def make_contract(symbol, sec_type, exch='SMART', prim_exch=None, curr='USD', opt_type='C', expiry_date=None,
                      strike=None, multipler=100, tradingClass=None):
        contract = Contract()
        contract.symbol = symbol
        contract.secType = sec_type
        contract.exchange = exch
        contract.primaryExch = prim_exch
        contract.currency = curr
        if sec_type == 'OPT':
            contract.multiplier = multipler
            if symbol == 'DAX':
                contract.multiplier = 5
            elif symbol == 'ESTX50':
                contract.multiplier = 10
            if expiry_date is not None:
                contract.lastTradeDateOrContractMonth = expiry_date
            contract.right = opt_type
            if strike is not None:
                contract.strike = strike

            if tradingClass is not None:
                contract.tradingClass = tradingClass
        return contract

    @staticmethod
    def make_order(action, quantity, order_type, price=None, stop_price=None, spread_order=False):
        order = Order()
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        order.orderType = order_type
        order.totalQuantity = quantity
        order.action = action
        order.Transmit = True
        if spread_order:
            order.smartComboRoutingParams = []
            order.smartComboRoutingParams.append(TagValue("NonGuaranteed", "1"))
        else:
            order.tif = 'GTC'
            # order.goodTillDate = datetime.now().strftime('%Y%m%d 19:59:10 US/Eastern')

        if order_type in ['LMT']:
            order.lmtPrice = price
        elif order_type == 'STP':
            order.auxPrice = stop_price

        return order
