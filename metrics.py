import pandas as pd

from trading_bot.database.db import engine
from trading_bot.settings import logger, BASE_DIR


def generate_metrics(table):
    df = pd.read_sql(table, engine)
    if not len(df):
        logger.debug('No options positions yet')
        return
    del df['instruction']

    df = df.round(2)
    df = df.sort_values(by='entry_time', ascending=True)
    df.index = df['entry_time']
    df.index.names = ['index']
    df['entry_time'] = df['entry_time'].astype(str)
    file_name = 'opt_trade_results.xlsx'
    df.to_excel(BASE_DIR / file_name, index=False)
    logger.info(f'results generated, check {file_name} file for it')


if __name__ == '__main__':
    generate_metrics(table='opt_trades_data')


