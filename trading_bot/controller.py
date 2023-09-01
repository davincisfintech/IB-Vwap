import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from dateutil.parser import parse

from ibapi.client import ExecutionFilter
from trading_bot.clients.ib import IBapi
from trading_bot.database.db import engine, OptTradesData
from trading_bot.database.db_handler import save_trade
from trading_bot.settings import logger, TZ
from trading_bot.stretegies.tsp import TSP
from trading_bot.trade_managers.opt_trade_manager import OptTradeManager


class Controller:
    def __init__(self, client):
        self.client = client
        self.strats = dict()
        self.trade_managers = list()

    @staticmethod
    def run_instance(obj):
        return obj.trade()

    def run(self):
        with ThreadPoolExecutor() as executor:
            res = executor.map(self.run_instance, self.trade_managers)
        res = [r for r in res if r is not None]
        for r in res:
            if isinstance(r, dict):
                if r['msg']:
                    model_class = OptTradesData
                    for i in r['msg']:
                        if i:
                            for k, v in i.items():
                                save_trade(model_class, k, v)
            else:
                if r.trade_ended:
                    self.trade_managers.remove(r)
                    self.client.cancelMktData(r.id)
                    # del self.strats[self.symbol]
                    logger.debug(f'{r.identifier} instance removed from trading manager')
                    if not r.time_based_exit:
                        self.strats[r.symbol].contract_fetched = False
                        self.strats[r.symbol].log_info()

        tsp_obj_list = [obj for obj in self.strats.values() if not obj.contract_fetched]
        if not len(self.trade_managers) and not len(tsp_obj_list):
            logger.debug('All instances closed, Trading ended')
            return 'trade_ended'


def run(symbols, account_mode, time_frame, below_vwap_per, above_vwap_std_per, standard_deviation, trade_size,
        start_time, end_time, day_down_percent, stop_loss, tighter_stop_loss, trade_end_time, total_loss_amount,
        below_vwap_std_per, calc_method):
    calc_method = calc_method.strip().lower()
    try:
        start_time, end_time, trade_end_time = parse(start_time).time(), parse(end_time).time(), \
                                               parse(trade_end_time).time()
    except Exception as e:
        logger.exception(e)
        logger.debug(f'Invalid start time: {start_time} or end time: {end_time} or trade end time: {trade_end_time}')
        return

    if end_time <= start_time:
        logger.debug(f'end time: {end_time} must be greater than start time: {start_time} and '
                     f'trade end time must be greater than end time')
        return

    if trade_end_time < end_time:
        logger.debug(f'trade end time: {trade_end_time} must be greater than end time: {end_time}')
        return

    if tighter_stop_loss > stop_loss:
        logger.debug(f'tighter stop loss: {tighter_stop_loss} must be less stop loss: {stop_loss}')
        return

    table_name = 'opt_trades_data'
    time_frame = time_frame if calc_method == 'pta' else '1 min'
    duration = '1 Y' if calc_method == 'pta' else '1 M'

    # OPEN & NON-EXPIRED
    pos_stock_list = pd.read_sql(table_name, engine)
    mask = (pos_stock_list['trading_mode'].str.upper() == account_mode.upper()) & \
           (pos_stock_list['position_status'] == "CLOSED") & \
           (pos_stock_list['exit_time'].dt.date == datetime.now(tz=TZ).date())
    closed_pos_stock_list = pos_stock_list[mask]
    exit_value = closed_pos_stock_list['exit_price'] * closed_pos_stock_list['quantity'] * 100
    entry_value = closed_pos_stock_list['entry_price'] * closed_pos_stock_list['quantity'] * 100
    closed_pnl = (exit_value - entry_value).sum()
    if closed_pnl <= -total_loss_amount:
        logger.debug(f'Daily loss: {closed_pnl} is more than specified loss amount: {total_loss_amount}, '
                     f'so cannot trade further today')
        return

    # Connection
    what_type = 'TRADES'  # Type of data required, i.e. TRADES, BID_ASK, BID, ASK, MIDPOINT etc
    client = IBapi()
    socket_port = 7497 if account_mode.lower() == 'paper' else 7496
    client.connect('127.0.0.1', socket_port, 1)
    client_thread = threading.Thread(target=client.run, daemon=True)
    client_thread.start()
    time.sleep(3)

    # controller
    controller = Controller(client=client)

    # Orders Requests
    client.reqAllOpenOrders()
    client.reqExecutions(10001, ExecutionFilter())

    mask = (pos_stock_list['trading_mode'].str.upper() == account_mode.upper()) & \
           ((pos_stock_list['position_status'] == "OPEN") | (pos_stock_list['entry_order_status'] == 'OPEN'))
    open_pos_stock_list = pos_stock_list[mask]
    open_pos_stock_list = list(open_pos_stock_list.T.to_dict().values())
    open_pos_symbols = {s['symbol']: s for s in open_pos_stock_list}

    for i, trade in enumerate(open_pos_stock_list, start=client.nextorderId):
        logger.info(f"Open position/order found in {trade['symbol']} {trade['opt_type']} "
                    f"option, reading parameters...")
        entry_order_filled = False if trade['entry_order_status'] == 'OPEN' else True
        bought = True if trade['side'] == 'LONG' else False
        sold = True if trade['side'] == 'SHORT' else False
        exit_pending = True if trade['exit_order_status'] == 'OPEN' else False
        contract = client.make_contract(symbol=trade['symbol'],
                                        sec_type=trade['symbol_type'], exch=trade['exchange'],
                                        prim_exch=trade['exchange'], curr='USD',
                                        opt_type=trade['opt_type'],
                                        expiry_date=trade['expiry_date'], strike=float(trade['strike']))
        contract.lot_size = trade['lot_size']
        client.reqMktData(reqId=i, contract=contract, genericTickList="106,100,101",
                          snapshot=False, regulatorySnapshot=False, mktDataOptions=[])
        kwargs = {
            'client': client, 'unique_id': i, 'trading_mode': account_mode, 'contract': contract,
            'side': trade['side'], 'entered': True, 'entry_order_filled': entry_order_filled,
            'bought': bought, 'sold': sold, 'instruction': trade['instruction'], 'qty': trade['quantity'],
            'trade_id': trade['trade_id'], 'entry_order_id': trade['entry_order_id'],
            'entry_price': trade['entry_price'], 'sl': trade['stop_loss'],
            'final_sl': trade['final_stop_loss'], 'ref_price': trade['reference_price'],
            'trade_size': trade_size, 'exit_pending': exit_pending, 'exit_order_id': trade['exit_order_id'],
            'exit_order_price': trade['exit_order_price'], 'stop_loss': stop_loss,
            'tighter_stop_loss': tighter_stop_loss, 'current_loss': closed_pnl, 'total_loss_amount': total_loss_amount,
            'trade_end_time': trade_end_time}

        controller.trade_managers.append(OptTradeManager(**kwargs))
        client.nextorderId += 1

    for symbol in symbols:
        ticker, sec_type, curr, exch = symbol, 'STK', 'USD', 'SMART'
        local_symbol = f'{ticker} {sec_type} {curr} {exch}'

        # Open symbols validation
        if ticker in open_pos_symbols:
            logger.info(f'{ticker}: already have open order/position so trading existing instance and '
                        f'not starting strategy instance')
            contract_fetched = True
        else:
            contract_fetched = False

        # contract id of stock
        client.nextorderId += 1
        contract_id = client.nextorderId
        contract_1 = client.make_contract(symbol=ticker, sec_type=sec_type, exch=exch, curr=curr)
        if not client.validate_opt_contract(contract_1):
            continue
        client.reqContractDetails(contract_id, contract_1)
        logger.debug(f'waiting For con id to be fetched for {ticker}')
        while ticker not in client.ticker_to_conId:
            pass
        con_id = client.ticker_to_conId[ticker]

        # reqSecDefOptParams
        client.nextorderId += 1
        reqId = client.nextorderId
        client.sec_id_to_local_symbol[reqId] = local_symbol
        client.reqSecDefOptParams(reqId=reqId,
                                  underlyingSymbol=ticker,
                                  futFopExchange="",
                                  underlyingSecType=sec_type,
                                  underlyingConId=con_id)

        # reqHistoricalData
        client.nextorderId += 1
        contract_2 = client.make_contract(symbol=ticker, sec_type=sec_type, curr=curr, exch=exch)
        if not client.validate_opt_contract(contract_2):
            continue
        id_2 = client.nextorderId
        client.reqHistoricalData(reqId=id_2, contract=contract_2, durationStr=duration, barSizeSetting=time_frame,
                                 whatToShow=what_type, useRTH=1, endDateTime='', formatDate=1, keepUpToDate=True,
                                 chartOptions=[])

        controller.strats[ticker] = TSP(client=client, local_symbol=local_symbol, unique_id_1=contract_id,
                                        unique_id_2=id_2, below_vwap_per=below_vwap_per,
                                        above_vwap_std_per=above_vwap_std_per, standard_deviation=standard_deviation,
                                        start_time=start_time, end_time=end_time, day_down_percent=day_down_percent,
                                        contract_fetched=contract_fetched, below_vwap_std_per=below_vwap_std_per,
                                        calc_method=calc_method)

    def run_instance(obj):
        return obj.run()

    while True:
        tsp_obj_list = [obj for obj in controller.strats.values() if not obj.contract_fetched]
        for tsp_obj in tsp_obj_list:
            tsp_return_contract = run_instance(tsp_obj)
            if tsp_return_contract:
                # option ltp request sent
                client.nextorderId += 1
                reqId = client.nextorderId
                client.reqMktData(reqId=reqId, contract=tsp_return_contract, genericTickList="106,100,101",
                                  snapshot=False, regulatorySnapshot=False, mktDataOptions=[])

                # TradeManager instance
                client = tsp_obj.client
                order_obj = OptTradeManager(client=client, unique_id=reqId, trading_mode=account_mode,
                                            contract=tsp_return_contract, side='LONG', trade_size=trade_size,
                                            stop_loss=stop_loss, tighter_stop_loss=tighter_stop_loss,
                                            current_loss=closed_pnl, total_loss_amount=total_loss_amount,
                                            trade_end_time=trade_end_time)
                controller.trade_managers.append(order_obj)

        if len(controller.trade_managers):
            msg = controller.run()
            if msg == 'trade_ended':
                break
        elif not len(tsp_obj_list):
            break

    client.disconnect()
    client_thread.join()

    # os.kill(os.getpid(), signal.SIGTERM)
