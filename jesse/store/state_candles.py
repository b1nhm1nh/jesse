import numpy as np

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.config import config
from jesse.enums import timeframes
from jesse.exceptions import RouteNotFound
from jesse.libs import DynamicNumpyArray
from jesse.models import store_candle_into_db
from jesse.services.candle import generate_candle_from_one_minutes
from timeloop import Timeloop
from datetime import timedelta

from jesse.ctf import on_init_storage, on_live_generate_warmup_candles_for_bigger_timeframe
from jesse.services import logger
from jesse.services.candle import generate_candle_from_one_minutes, print_candle
class CandlesState:
    def __init__(self) -> None:
        self.storage = {}
        self.are_all_initiated = False
        self.initiated_pairs = {}
        # CTF: Ignore CTF candles generated from Jesse Live module
        self.ctf_ignore = False
        self.is_live = jh.is_live()

    def generate_new_candles_loop(self) -> None:
        """
        to prevent the issue of missing candles when no volume is traded on the live exchange
        """
        t = Timeloop()

        @t.job(interval=timedelta(seconds=1))
        def time_loop_per_second():
            # make sure all candles are already initiated
            if not self.are_all_initiated:
                return

            # only at first second on each minute
            if jh.now(True) % 60_000 != 1000:
                return

            for c in config['app']['considering_candles']:
                exchange, symbol = c[0], c[1]
                current_candle = self.get_current_candle(exchange, symbol, '1m')

                # fix for a bug
                if current_candle[0] <= 60_000:
                    continue

                if jh.now() >= current_candle[0] + 60_000:
                    new_candle = self._generate_empty_candle_from_previous_candle(current_candle)
                    self.add_candle(new_candle, exchange, symbol, '1m')

        t.start()

    @staticmethod
    def _generate_empty_candle_from_previous_candle(previous_candle: np.ndarray) -> np.ndarray:
        new_candle = previous_candle.copy()
        new_candle[0] = previous_candle[0] + 60_000

        # new candle's open, close, high, and low all equal to previous candle's close
        new_candle[1] = previous_candle[2]
        new_candle[2] = previous_candle[2]
        new_candle[3] = previous_candle[2]
        new_candle[4] = previous_candle[2]
        # set volume to 0
        new_candle[5] = 0
        return new_candle

    def mark_all_as_initiated(self) -> None:
        
        if self.is_live:
            # CTF Hack
            self.are_all_initiated = False
            # Debug:
            # logger.info("mark_all_as_initiated: Re-Generate candles")
            for c in config['app']['considering_candles']:        
                exchange, symbol = c[0], c[1]
                for timeframe in config['app']['all_timeframes']:
                    # if timeframe != '1m':
                    key = jh.key(exchange, symbol, timeframe)
                    # logger.info(f"Info: {timeframe} candle length {len(self.storage[key])}")

            # Debug: print all candles
            # for c in config['app']['considering_candles']:        
            #     exchange, symbol = c[0], c[1]
            #     self.initiated_pairs[f'{exchange}-{symbol}'] = True

            #     for timeframe in config['app']['all_timeframes']:
            #         if timeframe != '1m':
            #             key = jh.key(exchange, symbol, timeframe)
            #             logger.info(f"candle length: {timeframe} length {len(self.storage[key])}")
            #             candles = self.get_storage(exchange, symbol, timeframe)
            #             logger.info(f"candle {symbol} after re-generated length: {timeframe} length {len(candles)}")

            # Ignoring stage Done:  candles generate from Jesse Live module. Now we back to accept CTF candles
            self.ctf_ignore = False

        for k in self.initiated_pairs:
            self.initiated_pairs[k] = True
        self.are_all_initiated = True

    def get_storage(self, exchange: str, symbol: str, timeframe: str) -> DynamicNumpyArray:
        key = jh.key(exchange, symbol, timeframe)

        try:
            return self.storage[key]
        except KeyError:
            raise RouteNotFound(
                f"Bellow route is required but missing in your routes:\n('{exchange}', '{symbol}', '{timeframe}')"
            )

    def init_storage(self, bucket_size: int = 1000) -> None:
        for c in config['app']['considering_candles']:
            exchange, symbol = c[0], c[1]

            # initiate the '1m' timeframes
            key = jh.key(exchange, symbol, timeframes.MINUTE_1)
            self.storage[key] = DynamicNumpyArray((bucket_size, 6))

            for timeframe in config['app']['considering_timeframes']:
                key = jh.key(exchange, symbol, timeframe)
                # ex: 1440 / 60 + 1 (reserve one for forming candle)
                total_bigger_timeframe = int((bucket_size / jh.timeframe_to_one_minutes(timeframe)) + 1)
                self.storage[key] = DynamicNumpyArray((total_bigger_timeframe, 6))
        # CTF Hook
        # Initialized all 
        on_init_storage()
        # End CTF Hook

    def add_candle(
            self,
            candle: np.ndarray,
            exchange: str,
            symbol: str,
            timeframe: str,
            with_execution: bool = True,
            with_generation: bool = True,
            with_skip: bool = True
    ) -> None:

        # add only 1 candle
        if len(candle.shape) == 1:
            self._add_one_candle(
                candle,
                exchange,
                symbol,
                timeframe,
                with_execution,
                with_generation,
                with_skip)

        # add only multiple candles
        elif len(candle.shape) == 2:

            self._add_multiple_candles(
                candle,
                exchange,
                symbol,
                timeframe,
                with_execution,
                with_generation,
                )

    def _add_one_candle(self,
                        candle: np.ndarray,
                        exchange: str,
                        symbol: str,
                        timeframe: str,
                        with_execution: bool = True,
                        with_generation: bool = True,
                        with_skip: bool = True):
        # CTF Hook, ignore orignal CTF candle insertion
        if self.ctf_ignore and timeframe != '1m':
            return
        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, timeframe)
        if jh.is_collecting_data():
            raise NotImplemented("Collecting data is deactivated at the moment")
            # make sure it's a complete (and not a forming) candle
            if jh.now_to_timestamp() >= (candle[0] + 60000):
                store_candle_into_db(exchange, symbol, candle)
            return

        if candle[0] == 0:
            if jh.is_debugging():
                logger.error("DEBUGGING-VALUE: please report to Saleh: candle[0] is zero")
            return

        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, timeframe)

        if jh.is_live():
            # ignore if candle is still being initially imported
            if with_skip and f'{exchange}-{symbol}' not in self.initiated_pairs:
                return

            self.update_position(exchange, symbol, candle[2])

            # ignore new candle at the time of execution because it messes
            # the count of candles without actually having an impact
            if candle[0] >= jh.now():
                return

        # if it's not an initial candle, add it to the storage, if already exists, update it
        if f'{exchange}-{symbol}' in self.initiated_pairs:
            store_candle_into_db(exchange, symbol, candle, on_conflict='replace')

        # initial
        if len(arr) == 0:
            arr.append(candle)

        # if it's new, add
        elif candle[0] > arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to be executed
            if with_execution and jh.is_paper_trading():
                # logger.info(f"******* on new candles")
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr.append(candle)

            # generate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution)

        # if it's the last candle again, update
        elif candle[0] == arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to get executed
            if with_execution and jh.is_paper_trading():
                # logger.info(f"******* on last candles")
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr[-1] = candle

            # regenerate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution)

        # past candles will be ignored (dropped)
        elif candle[0] < arr[-1][0]:
            return

    def _add_multiple_candles(self,
                              candle: np.ndarray,
                              exchange: str,
                              symbol: str,
                              timeframe: str,
                              with_execution: bool = True,
                              with_generation: bool = True):

        arr: DynamicNumpyArray = self.get_storage(exchange, symbol, timeframe)
        # this is an array of candles
        if len(arr) == 0:
            arr.append_multiple(candle)

        # if it's new, add
        elif candle[-1][0] > arr[-1][0]:
            # in paper mode, check to see if the new candle causes any active orders to be executed
            if with_execution and jh.is_paper_trading():
                self.simulate_order_execution(exchange, symbol, timeframe, candle)

            arr.append_multiple(candle)

            # generate other timeframes
            if with_generation and timeframe == '1m':
                self.generate_bigger_timeframes(candle, exchange, symbol, with_execution)
        else:
            raise ValueError('Try to insert list of candles into memory, but some already exist..')

    def add_candle_from_trade(self, trade, exchange: str, symbol: str) -> None:
        """
        In few exchanges, there's no candle stream over the WS, for
        those we have to use cases the trades stream
        """
        if not jh.is_live():
            raise Exception('add_candle_from_trade() is for live modes only')

        # ignore if candle is still being initially imported
        if f'{exchange}-{symbol}' not in self.initiated_pairs:
            return

        # in some cases we might be missing the current forming candle like it is on FTX, hence
        # if that is the case, generate the current forming candle (it won't be super accurate)
        current_candle = self.get_current_candle(exchange, symbol, '1m')
        if jh.now() > current_candle[0] + 60_000:
            new_candle = self._generate_empty_candle_from_previous_candle(current_candle)
            self.add_candle(new_candle, exchange, symbol, '1m')

        # update position's current price
        self.update_position(exchange, symbol, trade['price'])

        current_candle = self.get_current_candle(exchange, symbol, '1m')
        new_candle = current_candle.copy()
        # close
        new_candle[2] = trade['price']
        # high
        new_candle[3] = max(new_candle[3], trade['price'])
        # low
        new_candle[4] = min(new_candle[4], trade['price'])
        # volume
        new_candle[5] += trade['volume']

        self.add_candle(new_candle, exchange, symbol, '1m')

    @staticmethod
    def update_position(exchange: str, symbol: str, price: float) -> None:
        # get position object
        p = selectors.get_position(exchange, symbol)

        # for extra_route candles, p == None, hence no further action is required
        if p is None:
            return

        if jh.is_live():
            price_precision = selectors.get_exchange(exchange).vars['precisions'][symbol]['price_precision']

            # update position.current_price
            p.current_price = jh.round_price_for_live_mode(price, price_precision)
        else:
            p.current_price = price

    def generate_bigger_timeframes(self, candle: np.ndarray, exchange: str, symbol: str, with_execution: bool) -> None:
        if not jh.is_live():
            return
        
        # all_timeframes = list(config['app']['considering_timeframes']) + config['app']['ctf_timeframes']
        for timeframe in config['app']['all_timeframes']:
            # skip '1m'
            if timeframe == '1m':
                continue

            # last_candle = self.get_current_candle(exchange, symbol, timeframe)
            current_1m_candle = self.get_storage(exchange, symbol, '1m')[-1]
            required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
            min_from_open_time = int(current_1m_candle[0]//60000 + 1) % 1440
            # generate_from_count = int((candle[0] - last_candle[0]) / 60_000)

            real_generate_from_count = min_from_open_time % required_1m_to_complete_count

            
            generate_from_count = real_generate_from_count

            print(f"generate_bigger_timeframes: min_from_open_time {min_from_open_time} Real candle: {real_generate_from_count}")

            short_candles = self.get_candles(exchange, symbol, '1m')[-1 - generate_from_count:]

            if generate_from_count < 0:
                current_1m = self.get_current_candle(exchange, symbol, '1m')
                last_candle = self.get_current_candle(exchange, symbol, timeframe)
                number_of_candles = len(self.get_candles(exchange, symbol, '1m'))
                raise ValueError(
                    f'generate_from_count cannot be negative! '
                    f'generate_from_count:{generate_from_count}, candle[0]:{candle[0]}, '
                    f'last_candle[0]:{last_candle[0]}, current_1m:{current_1m[0]}, number_of_candles:{number_of_candles}')

            if len(short_candles) == 0:
                last_candle = self.get_current_candle(exchange, symbol, timeframe)
                raise ValueError(
                    f'No candles were passed. More info:'
                    f'\nexchange:{exchange}, symbol:{symbol}, timeframe:{timeframe}, generate_from_count:{generate_from_count}'
                    f'\nlast_candle\'s timestamp: {last_candle[0]}'
                    f'\ncurrent timestamp: {jh.now()}'
                )
            # logger.info(f'Generating Bigger TF: timestamp: {last_candle[0]} current timestamp: {jh.now()} generate from count {generate_from_count} candles for {exchange}-{symbol}-{timeframe}')
            # update latest candle
            generated_candle = generate_candle_from_one_minutes(
                timeframe,
                short_candles,
                accept_forming_candles=True
            )

            self.add_candle(generated_candle, exchange, symbol, timeframe, with_execution, with_generation=False)

    def simulate_order_execution(self, exchange: str, symbol: str, timeframe: str, new_candle: np.ndarray) -> None:
        previous_candle = self.get_current_candle(exchange, symbol, timeframe)
        orders = selectors.get_orders(exchange, symbol)

        if previous_candle[2] == new_candle[2]:
            return

        for o in orders:
            # skip inactive orders
            if not o.is_active:
                continue

            if ((o.price >= previous_candle[2]) and (o.price <= new_candle[2])) or (
                    (o.price <= previous_candle[2]) and (o.price >= new_candle[2])):
                o.execute()

    def batch_add_candle(self, candles: np.ndarray, exchange: str, symbol: str, timeframe: str,
                         with_generation: bool = True) -> None:
        for c in candles:
            self.add_candle(c, exchange, symbol, timeframe, with_execution=False, with_generation=with_generation, with_skip=False)
        # for timeframe in config['app']['ctf_timeframes']:
        if jh.is_live() and timeframe == '1m':
            # logger.info("Generating CTF candles")
            self.generate_warmup_ctf_candle(exchange, symbol)
        # logger.info(f"on batch_add_candle. Ignore ctf candles.")

        # Ignore Warmup candles generate from Jesse Live module
        if jh.is_live():
            self.ctf_ignore = True

    def forming_estimation(self, exchange: str, symbol: str, timeframe: str) -> tuple:
        long_key = jh.key(exchange, symbol, timeframe)
        short_key = jh.key(exchange, symbol, '1m')
        required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
        current_1m_count = len(self.get_storage(exchange, symbol, '1m'))

        # CTF, dif reset at 00:00 for CTF
        if self.is_live:
            # in live mode, candle not away start at 00:00, so we have to calculate midnight diff
            if required_1m_to_complete_count < 1440:
                # get current 1m candle
                current_1m_candle = self.get_storage(exchange, symbol, '1m')[-1]
                min_from_open_time = int (current_1m_candle[0]//60000 + 1) % 1440
            else:
                min_from_open_time = current_1m_count
   
            real_generate_from_count = min_from_open_time % required_1m_to_complete_count
            dif = current_1m_count % required_1m_to_complete_count
            # 
            # if dif != real_generate_from_count:
            #     self.storage[short_key] = self.storage[short_key][(real_generate_from_count - dif + required_1m_to_complete_count) % required_1m_to_complete_count:]
            
            print(f"forming_estimation: min_from_open_time {min_from_open_time} Jesse dif {dif} Real dif: {real_generate_from_count}")
            dif = real_generate_from_count
        else:
            # in backtest mode, candle away start at 00:00, so we dont have to calculate midnight diff
            if required_1m_to_complete_count < 1440:
               current_1m_count = current_1m_count % 1440
            dif = current_1m_count % required_1m_to_complete_count

        return dif, long_key, short_key

    # # # # # # # # #
    # # # # # getters
    # # # # # # # # #
    def get_candles(self, exchange: str, symbol: str, timeframe: str, fullonly = False) -> np.ndarray:
        # no need to worry for forming candles when timeframe == 1m
        if timeframe == '1m':
            arr: DynamicNumpyArray = self.get_storage(exchange, symbol, '1m')
            if len(arr) == 0:
                return np.zeros((0, 6))
            else:
                return arr[:]

        # other timeframes
        dif, long_key, short_key = self.forming_estimation(exchange, symbol, timeframe)
        long_count = len(self.get_storage(exchange, symbol, timeframe))
        short_count = len(self.get_storage(exchange, symbol, '1m'))

        if dif == 0 and long_count == 0:
            return np.zeros((0, 6))

        # complete candle
        if dif == 0 or (self.storage[long_key][:long_count][-1][0] == self.storage[short_key][short_count - dif][0]):
            if fullonly and dif != 0:
                # return full candles only, ignore last incomplete candle
                return self.storage[long_key][:long_count-1]
            else:
                return self.storage[long_key][:long_count]
        # generate forming
        else:
            # CTF Get only full candle
            # logger.info(f"Get Candles: CTF Long {long_key} Short {short_key} Diff {dif} Long count {long_count} Short count {short_count}")
            if fullonly:
                # logger.info(f"Get Candles full: CTF Long {long_key} Short {short_key} Diff {dif} Long count {long_count} Short count {short_count}")
                return self.storage[long_key][:long_count]
            else:
                # logger.info(f"Get Candles with forming: CTF Long {long_key} Short {short_key} Diff {dif} Long count {long_count} Short count {short_count}")
                # logger.info(f"********* dif {dif} - {short_count - dif}-{short_count}")
                return np.concatenate(
                    (
                        self.storage[long_key][:long_count],
                        np.array(
                            (
                                generate_candle_from_one_minutes(
                                    timeframe,
                                    self.storage[short_key][short_count - dif:short_count],
                                    True
                                ),
                            )
                        )
                    ), axis=0
                )

    def get_current_candle(self, exchange: str, symbol: str, timeframe: str, fullonly = False) -> np.ndarray:
        # no need to worry for forming candles when timeframe == 1m
        if timeframe == '1m':
            arr: DynamicNumpyArray = self.get_storage(exchange, symbol, '1m')
            if len(arr) == 0:
                return np.zeros((0, 6))
            else:
                return arr[-1]

        # other timeframes
        dif, long_key, short_key = self.forming_estimation(exchange, symbol, timeframe)
        long_count = len(self.get_storage(exchange, symbol, timeframe))
        short_count = len(self.get_storage(exchange, symbol, '1m'))

        # complete candle
        if dif != 0:
            if fullonly:
                # remove last forming candle
                if long_count <= 1:
                    return np.zeros((0, 6))
                else:
                    return self.storage[long_key][-2]
            else:
                return generate_candle_from_one_minutes(
                    timeframe, self.storage[short_key][short_count - dif:short_count],
                    True
                )
        if long_count == 0:
            return np.zeros((0, 6))
        else:
            return self.storage[long_key][-1]

    # CTF Hack
    def generate_warmup_ctf_candle(self, exchange: str, symbol: str):
        logger.info(f"generate_warmup_ctf_candle")
        for c in config['app']['considering_candles']:        
            exchange, symbol = c[0], c[1]
            candles = self.get_storage(exchange, symbol, '1m')
            # print(f"generate_warmup_ctf_candle Generating CTF candles for {exchange} {symbol} len {len(candles)}")
            on_live_generate_warmup_candles_for_bigger_timeframe(candles, exchange, symbol)


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

