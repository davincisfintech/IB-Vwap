#  Parameters start  #

account_mode = 'Paper'  # Choices Live, Paper. Live if Live account is open and Paper if paper account is open in IB TWS

symbols = ['SPY']

# Choices: pta, custom.
# pta for calculating std using pandas-ta function and
# custom to calculate std using custom function as mentioned in that reddit post
# (https://www.reddit.com/r/algotrading/comments/gman9v/calculating_vwap_bands/?rdt=52675)
calc_method = 'custom'

# Timeframe for candles, choices: 1 min, 2 mins, 3 mins, 5 mins, 10 mins, 15 mins, 20 mins, 30 mins, 1 hour
time_frame = '15 mins'  # Only applies in case of calc_method pta else it'll be set to 1 min as default

standard_deviation = 2  # Standard deviation multiplier. 1 for 1 std, 2 for 2 std etc
below_vwap_per = 0.18  # Percentage below vwap. like vwap * (1 - below_vwap_per/100)

# Percentage above (vwap - std * standard_deviation(multiplier parameter)). like (vwap - std) * (1 + below_vwap_std/100)
above_vwap_std_per = 0.02

# Percentage below (vwap - std * standard_deviation(multiplier parameter)). like (vwap - std) * (1 + below_vwap_std/100)
below_vwap_std_per = 2  # if underlying price is below vwap_std by this much percent then do not take trade

trade_size = 1000  # $ size to buy contracts, like $1000 means buy contracts worth $1000

start_time = '10:00'  # Format HH:MM EST
end_time = '15:00'  # Format HH:MM EST
trade_end_time = '15:50'  # Format HH:MM EST
total_loss_amount = 600   # If this much amount lost then stop trading for the day
day_down_percent = 1  # If underlying is down from day's open by more than this much percent then ignore trade
stop_loss = 20   # Stop loss percent to set stop loss at the start
tighter_stop_loss = 7  # Stop loss percent to set stop loss after price moves up more than 20 percent

if __name__ == '__main__':
    kwargs = {i: j for i, j in locals().items() if not i.startswith('__')}
    from trading_bot.controller import run

    run(**kwargs)
