
import numpy as np
import jesse.helpers as jh

from jesse.services import logger
from jesse.config import config
from jesse.enums import timeframes
from jesse.services.candle import generate_candle_from_one_minutes, print_candle, candle_includes_price, split_candle

"""
Hook on init storage in states_candles.py
Add ctf timeframes
"""
def on_init_storage():
    logger.info("BM: Initializing storage..")
    logger.info("---considering_candles:" + str(config['app']['considering_candles']))
    logger.info("---considering_timeframes:" + str(config['app']['considering_timeframes']))
    enable_ctf = True
    config['app']['ctf_timeframes'] = []
    if enable_ctf:
        for c in config['app']['considering_candles']:
            exchange, symbol = c[0], c[1]
            config['app']['all_timeframes'] = config['app']['considering_timeframes']
            config['app']['considering_timeframes'] = list(config['app']['considering_timeframes'])
            for timeframe in config['app']['considering_timeframes']:
                if timeframe != timeframes.MINUTE_1:
                    # config['app']['ctf_timeframes'].append(timeframe)
                    # config['app']['considering_timeframes'].remove(timeframe)
                    pass
                    
            # config['app']['considering_timeframes'] = tuple(['1m'])

    logger.info("---considering_timeframes:" + str(config['app']['considering_timeframes']))
    logger.info("---ctf_timeframes:" + str(config['app']['ctf_timeframes']))

"""
Hook on require_candles.py 
"""
def on_inject_required_candles_to_store(candles: np.ndarray, exchange: str, symbol: str) -> None:
    pass

"""
Hook backtest_modes.py 
on generate ctf candles
"""
def on_generate_candles_for_bigger_timeframe(candles: np.ndarray, exchange: str, symbol: str, i, j) -> None:
    from jesse.store import store

    # generate and add candles for bigger timeframes
    for timeframe in config['app']['all_timeframes']:
        # for 1m, no work is needed
        if timeframe == '1m':
            continue

        count = jh.timeframe_to_one_minutes(timeframe)

        is_ctf_candle = False
        if (count < 1440) and (1440 % count != 0):
            is_ctf_candle = True

        # only works with TF < 1440
        if is_ctf_candle:                                  
            k = (i + 1) % 1440 
            if ((k == 0) and (i > 1)):                      
                count = round(1440 - (1440 // count) * count)
                # logger.info(f"K {k} count {count} i={i}")
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]['candles'][(i - (count - 1)):(i + 1)],
                    True)
                # _get_fixed_jumped_candle(candles[j]['candles'][i - count], candles[j]['candles'][i - (count - 1)])  

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                        with_generation=False)
                print_candle(generated_candle, False, symbol)
            elif (k % count == 0):
                # logger.info(f"K {k} count {count} i={i}")
                # _get_fixed_jumped_candle(candles[j]['candles'][i - count], candles[j]['candles'][i - (count - 1)])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]['candles'][(i - (count - 1)):(i + 1)],
                    False)
                store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                        with_generation=False)
                print_candle(generated_candle, False, symbol)                        
        elif (i + 1) % count == 0:
            # _get_fixed_jumped_candle(candles[j]['candles'][i - count], candles[j]['candles'][i - (count - 1)])
            generated_candle = generate_candle_from_one_minutes(
                timeframe,
                candles[j]['candles'][(i - (count - 1)):(i + 1)])
            store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                    with_generation=False)
        
        # End CTF Hack
"""
Hook backtest_modes.py 
on generate ctf candles
"""
def on_generate_candles_for_bigger_timeframe_with_skip(candles: np.ndarray, exchange: str, symbol: str, i, j) -> None:
    from jesse.store import store
    for timeframe in config['app']['considering_timeframes']:
        # for 1m, no work is needed
        if timeframe == '1m':
            continue

        count = jh.timeframe_to_one_minutes(timeframe)

        is_ctf_candle = False
        if (count < 1440) and (1440 % count != 0):
            is_ctf_candle = True
        # only works with TF < 1440
        if is_ctf_candle:                                  
            k = (i) % 1440 
            if ((k == 0) and (i > 1)):                      
                count = round(1440 - (1440 // count) * count)
                # logger.info(f"K {k} count {count} i={i}")
                _get_fixed_jumped_candle(candles[j]['candles'][i - count - 1], candles[j]['candles'][i - count])  
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]['candles'][(i - (count)):(i)],
                    True)
                store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                        with_generation=False)
                # print_candle(generated_candle, False, r.symbol)
            elif (k % count == 0):
                # logger.info(f"K {k} count {count} i={i}")
                _get_fixed_jumped_candle(candles[j]['candles'][i - count - 1], candles[j]['candles'][i - count])  
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[j]['candles'][(i - (count)):(i)],
                    False)
                store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                        with_generation=False)
                # print_candle(generated_candle, False, r.symbol)                        
        elif (i) % count == 0:
            _get_fixed_jumped_candle(candles[j]['candles'][i - count - 1], candles[j]['candles'][i - count])  
            generated_candle = generate_candle_from_one_minutes(
                timeframe,
                candles[j]['candles'][(i - (count)):(i)])
            store.candles.add_candle(generated_candle, exchange, symbol, timeframe, with_execution=False,
                                    with_generation=False)   

"""
Hook required_candles.py 
on generate ctf candles
"""
def on_generate_warmup_candles_for_bigger_timeframe_backtest(candles: np.ndarray, exchange: str, symbol: str, i) -> None:
    from jesse.store import store
    # logger.info(f"BM: Generating warmup candles for bigger timeframes: {config['app']['all_timeframes']}..")

    for timeframe in config['app']['all_timeframes']:
        # skip 1m. already added
        if timeframe == '1m':
            continue
        # print(f"BM: Generating warmup candles for bigger timeframes:{i}-{timeframe}..")
        num = jh.timeframe_to_one_minutes(timeframe)

        is_ctf_candle = False
        if (num < 1440) and (1440 % num != 0):
            is_ctf_candle = True

        # only works with TF < 1440
        if is_ctf_candle:                                  
            k = (i + 1) % 1440              
            if ((k == 0) and (i > 1)):   
                # reset the counter, last candle of day
                num = round(1440 - (1440 // num) * num)
                # print(f"Case 1: {i} k = {k}")
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                # print_candle(generated_candle, False, symbol) 
            elif k % num == 0:
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                # print_candle(generated_candle, False, symbol) 
                # print(f"{i} k = {k}")
        else:
            # generate as normal
            if (i + 1) % num == 0:
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                # print_candle(generated_candle, False, symbol) 
"""
Hook required_candles.py 
on generate ctf candles
"""
def on_generate_warmup_candles_for_bigger_timeframe(candles: np.ndarray, exchange: str, symbol: str, i) -> None:
    from jesse.store import store
    # logger.info(f"BM: Generating warmup candles for bigger timeframes: {config['app']['all_timeframes']}..")

    for timeframe in config['app']['all_timeframes']:
        # skip 1m. already added
        if timeframe == '1m':
            continue

        num = jh.timeframe_to_one_minutes(timeframe)

        is_ctf_candle = False
        if (num < 1440) and (1440 % num != 0):
            is_ctf_candle = True

        # only works with TF < 1440
        if is_ctf_candle:                                  
            k = (i + 1) % 1440              
            if ((k == 0) and (i > 1)):   
                # reset the counter, last candle of day
                num = round(1440 - (1440 // num) * num)
                # print(f"Case 1: {i} k = {k}")
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                # print_candle(generated_candle, False, symbol) 
            elif k % num == 0:
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                # print_candle(generated_candle, False, symbol) 
                # print(f"{i} k = {k}")
        else:
            # generate as normal
            if (i + 1) % num == 0:
                _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                store.candles.add_candle(generated_candle, exchange, symbol, timeframe,
                    with_execution=False, with_generation=False
                )
                print_candle(generated_candle, False, symbol) 


"""
Hook state_candles.py 
on generate ctf candles
"""
def on_live_generate_warmup_candles_for_bigger_timeframe(candles: np.ndarray, exchange: str, symbol: str) -> None:
    from jesse.store import store

    # logger.info("BM: Generating warmup candles for bigger timeframes..")
    # logger.info(f"BM: Generating warmup candles for bigger timeframes..{config['app']['all_timeframes']}")

    length = len(candles)
    for i in range(length):
        for timeframe in config['app']['all_timeframes']:
            # skip 1m. already added
            if timeframe == '1m':
                continue

            num = jh.timeframe_to_one_minutes(timeframe)

            is_ctf_candle = False
            if (num < 1440) and (1440 % num != 0):
                is_ctf_candle = True

            # only works with TF < 1440
            if is_ctf_candle:                                  
                k = (i + 1) % 1440              
                if ((k == 0) and (i > 1)):   
                    # reset the counter, last candle of day
                    num = round(1440 - (1440 // num) * num)
                    # print(f"Case 1: {i} k = {k}")
                    _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (num - 1)):(i + 1)],
                        True
                    )

                    store.candles.add_candle(generated_candle,exchange,symbol,timeframe,
                        with_execution=False,
                        with_generation=False,
                        with_skip = False
                    )
                    # if length - i < 20:
                    # print_candle(generated_candle, False, symbol) 
                elif k % num == 0:
                    _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (num - 1)):(i + 1)],
                        True
                    )

                    store.candles.add_candle(generated_candle,exchange,symbol,timeframe,
                        with_execution=False,
                        with_generation=False,
                        with_skip = False
                    )
                    # if length - i < 20:
                    # print_candle(generated_candle, False, symbol) 
                    # print_candle(generated_candle, False, symbol) 
                    # print(f"{i} k = {k}")
            else:
                # generate as normal
                if (i + 1) % num == 0:
                    _get_fixed_jumped_candle(candles[i - num], candles[i - num + 1])
                    generated_candle = generate_candle_from_one_minutes(
                        timeframe,
                        candles[(i - (num - 1)):(i + 1)],
                        True
                    )

                    store.candles.add_candle(generated_candle,exchange,symbol,timeframe,
                        with_execution=False,
                        with_generation=False,
                        with_skip = False
                    )
                    # print_candle(generated_candle, False, symbol) 
"""
Hook state_candles.py 
on_new_candle
"""

def _on_new_candle() -> None:

    # Save
    return



def _get_fixed_jumped_candle(previous_candle: np.ndarray, candle: np.ndarray) -> np.ndarray:
    """
    A little workaround for the times that the price has jumped and the opening
    price of the current candle is not equal to the previous candle's close!

    :param previous_candle: np.ndarray
    :param candle: np.ndarray
    """
    if candle[1] != previous_candle[2]:
        candle[1] = previous_candle[2]
        candle[4] = min(previous_candle[2], candle[4])
        candle[3] = max(previous_candle[2], candle[3])

    return candle