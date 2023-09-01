import warnings

from trading_bot.database.db import session
from trading_bot.settings import logger

warnings.filterwarnings('ignore')


def save_trade(model_class, action, params):
    if action == 'make_entry':
        obj = model_class(**params)
        obj.save_to_db()
        logger.debug(f'Trade Saved for {params["symbol"]} for action: {action}')
    elif action == 'confirm_entry':
        obj = session.query(model_class).filter(model_class.trade_id == params['trade_id'],
                                                model_class.symbol == params['symbol'],
                                                model_class.entry_order_status == 'OPEN').first()
        if not obj:
            logger.debug(f'Trade not found for {params["symbol"]}, trade_id: {params["trade_id"]}')
            return
        symbol = params.pop('symbol')
        del params['trade_id']
        for k, v in params.items():
            setattr(obj, k, v)
        obj.commit_changes()
        logger.debug(f'Trade modified for {symbol} for action: {action}')
    elif action == 'make_exit':
        obj = session.query(model_class).filter(model_class.trade_id == params['trade_id'],
                                                model_class.symbol == params['symbol'],
                                                model_class.position_status == 'OPEN').first()
        if not obj:
            logger.debug(f'Position not found for {params["symbol"]}, trade_id: {params["trade_id"]}')
            return
        symbol = params.pop('symbol')
        del params['trade_id']
        for k, v in params.items():
            setattr(obj, k, v)
        obj.commit_changes()
        logger.debug(f'Trade modified for {symbol} for action: {action}')
    elif action == 'confirm_exit':
        obj = session.query(model_class).filter(model_class.trade_id == params['trade_id'],
                                                model_class.symbol == params['symbol'],
                                                model_class.position_status == 'OPEN').first()
        if not obj:
            logger.debug(f'Open Position not found for {params["symbol"]}, trade_id: {params["trade_id"]}')
            return
        symbol = params.pop('symbol')
        del params['trade_id']
        for k, v in params.items():
            setattr(obj, k, v)
        obj.commit_changes()
        logger.debug(f'Trade modified for {symbol} for action: {action}')

    elif action == 'status_closed':
        obj = session.query(model_class).filter(model_class.trade_id == params['trade_id'],
                                                model_class.symbol == params['symbol'],
                                                model_class.position_status == 'OPEN').first()
        if not obj:
            logger.debug(f'Open Position not found for {params["symbol"]}, trade_id: {params["trade_id"]}')
            return
        symbol = params.pop('symbol')
        params['position_status'] = 'CLOSED'
        # del params['trade_id']

        for k, v in params.items():
            setattr(obj, k, v)

        obj.commit_changes()
        logger.debug(f'Previous position modified to CLOSED for {symbol} for action: {action}')
