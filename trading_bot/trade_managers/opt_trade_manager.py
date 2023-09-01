import uuid
from datetime import datetime

from trading_bot.settings import logger, TZ


class OptTradeManager:
    def __init__(self, client, unique_id, trading_mode, contract, trade_size, stop_loss, tighter_stop_loss,
                 trade_end_time, total_loss_amount, current_loss, side=None, entered=False, entry_order_filled=False,
                 exit_order_filled=False, bought=False, sold=False, instruction=None, qty=None, sl=None, final_sl=None,
                 trade_id=None, entry_order_id=None, entry_order_price=None, exit_pending=False,
                 entry_order_status=None, exit_order_id=None, exit_order_price=None, entry_price=None, ref_price=None):
        self.ltp = None
        self.client = client
        self.id = unique_id
        self.trading_mode = trading_mode
        self.contract = contract
        self.trade_size = trade_size
        self.symbol = contract.symbol
        self.symbol_type = contract.secType
        self.exchange = contract.exchange
        self.expiry_date = contract.lastTradeDateOrContractMonth
        self.strike = contract.strike
        self.opt_type = contract.right
        self.stop_loss = stop_loss
        self.tighter_stop_loss = tighter_stop_loss
        self.trade_end_time = trade_end_time
        self.total_loss_amount = total_loss_amount
        self.current_loss = current_loss
        self.side = side.upper()
        self.entered = entered
        self.bought = bought
        self.sold = sold
        self.instruction = instruction
        self.qty = qty
        self.sl = sl
        self.final_sl = final_sl
        self.ref_price = ref_price
        self.entry_order_price = entry_order_price
        self.entry_order_time = None
        self.entry_order_id = entry_order_id
        self.entry_order_filled = entry_order_filled
        self.entry_order_status = entry_order_status
        self.entry_price = entry_price
        self.entry_time = None
        self.exit_order_time = None
        self.exit_order_price = exit_order_price
        self.exit_order_id = exit_order_id
        self.exit_order_status = None
        self.exit_order_filled = exit_order_filled
        self.exit_pending = exit_pending
        self.exit_time = None
        self.exit_price = None
        self.exit_type = None
        self.position_status = None
        self.trade_ended = False
        self.ltp = None
        self.position_check = True
        self.time_based_exit = False
        self.live_pnl = 0
        self.messages = []
        self.trade_id = str(uuid.uuid4()) if trade_id is None else trade_id
        self.identifier = f'{self.symbol} {self.opt_type} {self.expiry_date} {self.strike}'
        logger.debug(f"""{trading_mode} Trading bot {self.identifier} instance started, 
                         parameters: unique ID: {self.id}, side: {self.side},  option type: {self.opt_type}, 
                         expiry date: {self.expiry_date}, strike: {self.strike}, trade_id: {self.trade_id}, 
                         entered: {self.entered}, exit pending: {self.exit_pending}, sl: {self.final_sl}, 
                         entry_price:{self.entry_price}, ref price: {self.ref_price}, 
                         trade end time: {self.trade_end_time}, total loss amount: {self.total_loss_amount}, 
                         current pnl: {self.current_loss}""")

    def __repr__(self):
        return f"trading_mode: {self.trading_mode}, id: {self.id}, instrument: {self.identifier}"

    def trade(self):
        if self.trade_ended:
            return self

        # Waiting for ltp of option
        if self.id not in self.client.reqId_to_ltp:
            return
        self.ltp = self.client.reqId_to_ltp[self.id]
        if self.entered and self.entry_order_filled:
            self.live_pnl = (self.ltp - self.entry_price) * self.qty * 100

        self.messages = []
        if self.is_valid_entry():
            self.make_entry()
        if self.entered and not self.entry_order_filled:
            self.confirm_entry()
        if self.is_valid_exit():
            self.make_exit()
        if self.entered and self.exit_pending:
            self.confirm_exit()
            if self.entered and self.exit_pending:
                if not self.is_valid_time_based_exit() and not self.is_total_loss_based_exit():
                    self.trail_sl()
                self.confirm_exit()

        return {'msg': self.messages}

    def is_total_loss_based_exit(self):
        if not self.time_based_exit and (self.live_pnl + self.current_loss) <= -self.total_loss_amount:
            self.time_based_exit = True
            logger.debug(f'total current loss: {self.live_pnl + self.current_loss} is more than total loss amount: '
                         f'{self.total_loss_amount}, so cancelling SL and exiting through market order')
            self.client.cancelOrder(self.exit_order_id,
                                    str(datetime.now(tz=TZ).replace(microsecond=0, tzinfo=None)).replace('-', ''))

            return True

    def is_valid_time_based_exit(self):
        if not self.time_based_exit and self.trade_end_time <= datetime.now(tz=TZ).time():
            self.time_based_exit = True
            logger.debug(f'{self.identifier}: end time: {self.trade_end_time} reached, '
                         f'cancelling SL order and exiting through market order')
            self.client.cancelOrder(self.exit_order_id,
                                    str(datetime.now(tz=TZ).replace(microsecond=0, tzinfo=None)).replace('-', ''))
            return True

    def trail_sl(self):
        if not self.time_based_exit and self.ltp > self.ref_price:
            init_sl = self.final_sl
            final_sl = self.final_sl + (self.ltp - self.ref_price)
            if self.ltp >= (self.entry_price * (1 + 20 / 100)) > self.ref_price:
                final_sl = self.ltp * (1 - (self.tighter_stop_loss / 100))
                if final_sl > self.final_sl:
                    self.final_sl = final_sl
                    logger.debug(f'{self.identifier}: SL trailed to {self.tighter_stop_loss}% after 20% move in price, '
                                 f'new sl: {self.final_sl}, before sl: {init_sl}, ltp: {self.ltp}')
            else:
                self.final_sl = final_sl
                logger.debug(f'{self.identifier}: SL trailed new sl: {self.final_sl}, before sl: {init_sl}, '
                             f'ltp: {self.ltp}')

            self.ref_price = self.ltp
            self.client.cancelOrder(self.exit_order_id,
                                    str(datetime.now(tz=TZ).replace(microsecond=0, tzinfo=None)).replace('-', ''))

    def is_valid_entry(self):
        if self.entered:
            return False
        if self.side == 'LONG':
            logger.info(f'{self.identifier}: Long signal generated at {datetime.now(tz=TZ)}, price: {self.ltp}')
            self.bought = True
            self.instruction = 'BUY'
            return True
        elif self.side == 'SHORT':
            logger.info(f'{self.identifier}: Short signal generated at {datetime.now(tz=TZ)}, price: {self.ltp}')
            self.sold = True
            self.instruction = 'SELL'
            return True

    def make_entry(self):
        # Calculation quantity according to trade_size
        self.qty = int(self.trade_size / (self.ltp * 100))

        logger.debug(f'{self.identifier}: Quantity set to {self.qty}')
        if self.qty < 1:
            logger.debug(f'{self.identifier}: Quantity less than 0, please increase trade size,  '
                         f'lot size: {self.qty},')
            self.trade_ended = True
            return

        self.client.nextorderId += 1
        self.entry_order_id = self.client.nextorderId
        self.client.placeOrder(self.entry_order_id, self.contract,
                               self.client.make_order(self.instruction, self.qty,
                                                      order_type='MKT'))
        self.entry_order_time = datetime.now(tz=TZ)
        self.entered = True
        self.entry_order_filled = False
        self.entry_order_status = 'OPEN'

        # Update account balance after taking position
        self.client.reqAccountSummary(9002, "All", "$LEDGER")

        logger.debug(f"""{self.identifier}: Entry order Placed to {self.instruction} qty: {self.qty}, 
                         price: {self.entry_order_price}, ltp: {self.ltp}, time:{self.entry_order_time}, 
                         order id: {self.entry_order_id}""")
        self.trade_id = str(uuid.uuid4())
        logger.debug(f'{self.identifier} Instance, new trade_id: {self.trade_id}')
        entry_data = self.save_trade(action='make_entry')
        self.messages.append(entry_data)

    def confirm_entry(self):
        for exec_order in self.client.exec_orders:
            if str(exec_order['exec_order_id']) == str(self.entry_order_id) and exec_order['symbol'] == self.symbol and \
                    exec_order['exec_qty'] == self.qty:
                self.entry_price = self.ref_price = exec_order['exec_avg_price']
                self.entry_time = exec_order['exec_time']
                self.entry_order_filled = True
                self.entry_order_status = 'FILLED'
                self.position_status = 'OPEN'
                self.sl = self.final_sl = self.entry_price * (1 - (self.stop_loss / 100))
                logger.debug(
                    f"{self.identifier}: Entry order Filled to {self.instruction}, price: {self.entry_price},"
                    f" qty:{self.qty}, time:{self.entry_time}, sl: {self.sl}")
                entry_data = self.save_trade(action='confirm_entry')
                self.position_check = False
                self.messages.append(entry_data)
                return

        for order in self.client.orders:
            if str(order['order_id']) == str(self.entry_order_id) and order['status'] in ['Cancelled', 'Inactive']:
                logger.debug(f'{self.identifier} Entry order to {self.instruction} {order["status"]}')
                self.entered = False
                self.bought, self.sold = False, False
                self.entry_time = None
                self.entry_price = None
                self.sl = None
                self.entry_order_status = order['status']
                self.position_status = None

                entry_data = self.save_trade(action='confirm_entry')
                self.messages.append(entry_data)
                self.trade_ended = True
                logger.info(f'{self.identifier}: Entry order cancelled, Closing instance')
                if order['status'] == 'Inactive':
                    self.time_based_exit = True
                return

    def is_valid_exit(self):
        if not self.entered or not self.entry_order_filled or self.exit_pending:
            return False

        close_entry_in_db = False
        pos_qty = None
        self.position_check = False
        if self.bought:
            if self.position_check:
                for pos in self.client.positions:
                    pos_qty = pos['position']
                    if pos['symbol'] == self.symbol and pos['position'] >= self.qty:
                        self.instruction = 'SELL'
                        return True
                else:
                    logger.debug(f'{self.identifier}: No long position exist for qty: {self.qty}, pos_qty: {pos_qty}')
                    close_entry_in_db = True
            else:
                self.instruction = 'SELL'
                self.position_check = True
                return True

        elif self.sold:
            if self.position_check:
                for pos in self.client.positions:
                    pos_qty = pos['position']
                    if pos['symbol'] == self.symbol and abs(pos['position']) >= self.qty:
                        self.instruction = 'BUY'
                        return True
                else:
                    logger.debug(f'{self.identifier}: No short position exist for qty: {self.qty}, pos qty: {pos_qty}')
                    close_entry_in_db = True
            else:
                self.instruction = 'BUY'
                self.position_check = True
                return True

        if close_entry_in_db:
            self.exit_type, self.exit_time, self.exit_price = None, None, None
            self.exit_order_status, self.position_status = None, None
            self.entered, self.bought, self.sold, self.exit_pending = False, False, False, False
            confirm_exit_data = self.save_trade(action='confirm_exit')
            self.messages.append(confirm_exit_data)
            self.trade_ended = True
            logger.debug(f'{self.identifier}: Trade completed, closing instance')

    def make_exit(self):
        self.client.nextorderId += 1
        self.exit_order_id = self.client.nextorderId
        self.client.nextorderId += 1

        self.exit_order_price = float("{:0.2f}".format(self.final_sl))
        if self.time_based_exit:
            price = 'MKT'
            order = self.client.make_order(action=self.instruction, quantity=self.qty, order_type='MKT')
        else:
            price = self.exit_order_price
            order = self.client.make_order(action=self.instruction, quantity=self.qty, order_type='STP',
                                           stop_price=self.exit_order_price)

        self.exit_order_time = datetime.now(tz=TZ)
        self.client.placeOrder(self.exit_order_id, self.contract, order)

        self.exit_order_status = 'OPEN'
        self.exit_order_filled = False
        self.exit_pending = True
        logger.debug(f"""{self.identifier}: Exit SL order Placed to {self.instruction} qty: {self.qty}, 
                         SL order price: {price}, SL order time time:{self.exit_order_time}, 
                         SL order id: {self.exit_order_id}""")
        exit_data = self.save_trade(action='make_exit')
        self.messages.append(exit_data)

    def confirm_exit(self):
        for exec_order in self.client.exec_orders:
            if exec_order['symbol'] != self.symbol:
                continue
            exec_order_id = str(exec_order['exec_order_id'])
            if exec_order_id == str(self.exit_order_id):
                if exec_order['exec_qty'] != self.qty:
                    continue
                self.exit_price = exec_order['exec_avg_price']
                self.exit_time = exec_order['exec_time']
                self.exit_type = 'SL'
                self.exit_order_status = 'FILLED'
                self.position_status = 'CLOSED'
                self.bought, self.sold = False, False
                self.exit_order_filled = True
                self.entered = False
                self.exit_pending = False
                logger.debug(f"""{self.identifier}: Exit {self.exit_type} order Filled to {self.instruction} {self.qty}, 
                                 price: {self.exit_price}, time:{self.exit_time}, order id: {self.exit_order_id}, 
                                 exit type: {self.exit_type}""")
                exit_data = self.save_trade(action='confirm_exit')
                self.messages.append(exit_data)
                self.trade_ended = True
                logger.debug(f'{self.identifier}: Trade completed, closing instance')
                return

        for order in self.client.orders:
            order_id = str(order['order_id'])
            if order_id == str(self.exit_order_id) and order['status'] in ['Cancelled', 'Inactive', 'ApiCancelled']:
                order_status = order['status']
                logger.debug(f'{self.identifier} Exit order to {self.instruction}, status: {order_status}')
                self.exit_pending = False
                return

    def save_trade(self, action):
        message = dict()
        if action == 'make_entry':
            message[action] = {'symbol': self.symbol, 'symbol_type': self.symbol_type,
                               'side': self.side, 'entry_order_time': self.entry_order_time,
                               'entry_order_price': self.entry_order_price, 'instruction': self.instruction,
                               'entry_order_id': self.entry_order_id, 'entry_order_status': self.entry_order_status,
                               'quantity': self.qty, 'trade_id': self.trade_id, 'trading_mode': self.trading_mode,
                               'opt_type': self.opt_type, 'expiry_date': self.expiry_date,
                               'strike': self.strike, 'exchange': self.exchange}
            return message

        elif action == 'confirm_entry':
            message[action] = {'symbol': self.symbol, 'trade_id': self.trade_id, 'entry_time': self.entry_time,
                               'entry_price': self.entry_price, 'reference_price': self.ref_price,
                               'final_stop_loss': self.final_sl, 'entry_order_status': self.entry_order_status,
                               'position_status': self.position_status}
            return message

        elif action == 'make_exit':
            message[action] = {'symbol': self.symbol, 'trade_id': self.trade_id, 'instruction': self.instruction,
                               'exit_order_id': self.exit_order_id, 'exit_order_time': self.exit_order_time,
                               'exit_order_price': self.exit_order_price, 'exit_order_status': self.exit_order_status,
                               'reference_price': self.ref_price, 'final_stop_loss': self.final_sl}
            return message

        elif action == 'confirm_exit':
            message[action] = {'symbol': self.symbol, 'trade_id': self.trade_id, 'exit_time': self.exit_time,
                               'exit_price': self.exit_price, 'exit_type': self.exit_type,
                               'exit_order_status': self.exit_order_status, 'position_status': self.position_status}
            return message
