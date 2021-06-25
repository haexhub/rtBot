from binance import AsyncClient, DepthCacheManager, BinanceSocketManager
from dotenv import dotenv_values
from enum import Enum
from random import randint
import asyncio
import json
import re
import time

config = dotenv_values(".env")


class rtSide(Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


class orderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class orderStatus(Enum):
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    FILLED = "FILLED"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    REJECTED = "REJECTED"


class orderType(Enum):
    LIMIT = "LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"


class timeInForce(Enum):
    FOK = "FOK"
    GTC = "GTC"
    IOC = "IOC"


class rtBot:
    """Range Trading Bot"""

    def __init__(self, symbol="BUSDUSDT"):
        self.binance = None
        self.accountInfo = None
        self.orderIdPrefix = "RT1"
        self.orders = {
            "all": [],
            "filled": [],
            "new": [],
            "rt": []
        }
        self.symbol = symbol
        self.takeProfitAmount = 0.0001

    def createOrderId(self, side=False, id=False):
        if (not side):
            return False

        if (id):
            return f'{self.orderIdPrefix}_{side}_{id}'
        else:
            return f'{self.orderIdPrefix}_{side}_{int(time.time())}_{randint(1000, 9999999)}'

    def createTakeProfitOrder(self, order={}):
        rtOrder = self.isRtOrder(order)
        if (not rtOrder or
                not float(order.get("price")) or
                rtOrder.groups()[0] != rtSide.OPEN.name
            ):
            return False

        newClientOrderId = self.createOrderId(
            rtSide.CLOSE.name, rtOrder.groups()[1])

        if (order.get("side") == orderSide.BUY.name):
            targetSide = orderSide.SELL.name
            targetPrice = float(order.get("price")) + self.takeProfitAmount
        else:
            targetSide = orderSide.BUY.name
            targetPrice = float(order.get("price")) - self.takeProfitAmount

        return {
            "newClientOrderId": newClientOrderId,
            "quantity": order.get("executedQty") if order.get("executedQty") else order.get("quantity"),
            "price": targetPrice,
            "side": targetSide,
            "symbol": order.get("symbol"),
            "timeInForce": timeInForce.GTC.name,
            "type": orderType.LIMIT.name
        }

    def determinNewRtOrders(self, price=0, maxOrders=2):
        iteration = 1
        nextOrders = []

        if (price < 1):
            while iteration <= maxOrders:
                nextOrders.append({
                    "newClientOrderId": self.createOrderId(rtSide.OPEN.name),
                    "quantity": 20,
                    "price": round(round(price, 4) - self.takeProfitAmount * iteration, 4),
                    "side": orderSide.BUY.name,
                    "symbol": self.symbol,
                    "timeInForce": timeInForce.GTC.name,
                    "type": orderType.LIMIT.name
                })
                iteration += 1
        elif(price > 1):
            while iteration <= maxOrders:
                nextOrders.append({
                    "newClientOrderId": self.createOrderId(rtSide.OPEN.name),
                    "quantity": 20,
                    "price": round(price + self.takeProfitAmount * iteration, 4),
                    "side": orderSide.SELL.name,
                    "symbol": self.symbol,
                    "timeInForce": timeInForce.GTC.name,
                    "type": orderType.LIMIT.name
                })
                iteration += 1
        return nextOrders

    def existsTakeProfitOrder(self, checkOrder={}):
        for order in self.orders.get("rt"):
            rtOrder = self.isRtOrder(order)
            rtCheckOrder = self.isRtOrder(checkOrder)

            if (rtCheckOrder and
                    rtOrder.groups()[0] == rtSide.CLOSE.name and
                    rtOrder.groups()[1] == rtCheckOrder.groups()[1]
                ):
                return True

        return False

    async def initBinance(self, api_key, api_secret):
        self.binance = await AsyncClient.create(api_key, api_secret)

    def isRtOrder(self, order={}):
        # print("search 4", order)
        regExp = f'^{self.orderIdPrefix}_({rtSide.CLOSE.name}|{rtSide.OPEN.name})_(.*)'
        # print("regexp", regExp)

        if (order.get("clientOrderId")):
            return re.search(regExp, order.get("clientOrderId"))

        if (order.get("newClientOrderId")):
            return re.search(regExp, order.get("newClientOrderId"))

        return False

    def isRtOrderAlreadyOpen(self, checkOrder={}):

        for rtOrder in self.orders.get("rt"):
            matchRtOrder = self.isRtOrder(rtOrder)
            matchCheckOrder = self.isRtOrder(checkOrder)

            if (
                matchRtOrder and
                matchCheckOrder and
                matchRtOrder.groups()[0] == matchCheckOrder.groups()[0] and
                matchRtOrder.groups()[1] == matchCheckOrder.groups()[1]
            ):
                return True

            # print("compare", rtOrder, checkOrder)
            if (rtOrder.get("status") == "NEW" and
                float(rtOrder.get("origQty")) == float(checkOrder.get("quantity")) and
                float(rtOrder.get("price")) == float(checkOrder.get("price")) and
                rtOrder.get("symbol") == checkOrder.get("symbol") and
                    rtOrder.get("side") == checkOrder.get("side")):
                return True

        return False

    def setOrders(self, orders=[]):
        self.orders.update(all=orders)
        self.orders.update(filled=[])
        self.orders.update(new=[])
        self.orders.update(rt=[])

        for order in self.orders.get("all"):
            isRtOrder = self.isRtOrder(order)
            if (order.get("status") == orderStatus.FILLED.name):
                self.orders.get("filled").append(order)

            if (order.get("status") == "NEW"):
                self.orders.get("new").append(order)

            if (isRtOrder and
                        (order.get("status") == orderStatus.FILLED.name or
                         order.get("status") == "NEW"
                         )
                    ):
                self.orders.get("rt").append(order)

    async def setTakeProfitOrders(self):
        for order in self.orders.get("rt"):
            if (order.get("status") == orderStatus.FILLED.name and
                    not self.existsTakeProfitOrder(order)):
                takeProfitOrder = self.createTakeProfitOrder(order)
                print("open tp order", takeProfitOrder)
                await self.binance.create_order(
                    newClientOrderId=takeProfitOrder.get("newClientOrderId"),
                    price=takeProfitOrder.get("price"),
                    quantity=takeProfitOrder.get(
                        "quantity"),
                    side=takeProfitOrder.get("side"),
                    symbol=takeProfitOrder.get("symbol"),
                    timeInForce=takeProfitOrder.get(
                        "timeInForce"),
                    type=takeProfitOrder.get("type"))

    async def startTrading(self):
        avgPrice = await self.binance.get_avg_price(symbol=self.symbol)
        syncedOrders = await self.syncOrders()
        price = float(avgPrice.get("price"))

        if (syncedOrders):
            print("price", price)
            await self.setTakeProfitOrders()
            nextOrders = self.determinNewRtOrders(price)
            # print("next orders", nextOrders)

            for newOrder in nextOrders:
                takeProfitOrder = self.createTakeProfitOrder(newOrder)

                """ print("order", newOrder)
                print("takeProfit", takeProfitOrder) """
                if (not self.isRtOrderAlreadyOpen(newOrder) and
                        not self.isRtOrderAlreadyOpen(takeProfitOrder)):
                    print("open new order", newOrder)
                    """ await self.binance.create_order(
                        newClientOrderId=newOrder.get("newClientOrderId"),
                        price=newOrder.get("price"),
                        quantity=newOrder.get("quantity"),
                        side=newOrder.get("side"),
                        symbol=newOrder.get("symbol"),
                        timeInForce=newOrder.get("timeInForce"),
                        type=newOrder.get("type")
                    )"""
        time.sleep(10)
        await self.startTrading()

    async def syncOrders(self, symbol="BUSDUSDT"):
        try:
            allOrders = await self.binance.get_all_orders(symbol=symbol)
            self.setOrders(allOrders)
            return True
        except:
            print("Error syncOrders")
            return False


async def main():
    # initialise the client
    bot = rtBot("BUSDUSDT")
    await bot.initBinance(config.get("api_key"), config.get("api_secret"))
    print(dir(bot))
    await bot.startTrading()
    await bot.binance.close_connection()

    # run some simple requests
    # print(json.dumps(res, indent=2))

    # initialise websocket factory manager
    # bsm = BinanceSocketManager(client)

    # create listener using async with
    # this will exit and close the connection after 5 messages
    # async with bsm.trade_socket('ETHBTC') as ts:
    #     for _ in range(5):
    #         res = await ts.recv()
    #         print(f'recv {res}')

    # get historical kline data from any date range

    """     # fetch 1 minute klines for the last day up until now
    klines = client.get_historical_klines(
        "BNBBTC", AsyncClient.KLINE_INTERVAL_1MINUTE, "1 day ago UTC")

    # use generator to fetch 1 minute klines for the last day up until now
    async for kline in await client.get_historical_klines_generator("BNBBTC", AsyncClient.KLINE_INTERVAL_1MINUTE, "1 day ago UTC"):
        print(kline)

    # fetch 30 minute klines for the last month of 2017
    klines = client.get_historical_klines(
        "ETHBTC", Client.KLINE_INTERVAL_30MINUTE, "1 Dec, 2017", "1 Jan, 2018")

    # fetch weekly klines since it listed
    klines = client.get_historical_klines(
      "NEOBTC", Client.KLINE_INTERVAL_1WEEK, "1 Jan, 2017") """

    # setup an async context the Depth Cache and exit after 5 messages
    # async with DepthCacheManager(client, symbol='ETHBTC') as dcm_socket:
    #     for _ in range(5):
    #         depth_cache = await dcm_socket.recv()
    #         print(
    #             f"symbol {depth_cache.symbol} updated:{depth_cache.update_time}")
    #         print("Top 5 asks:")
    #         print(depth_cache.get_asks()[:5])
    #         print("Top 5 bids:")
    #         print(depth_cache.get_bids()[:5])
    #


if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
