from binance.client import AsyncClient
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

    def __init__(self, symbol="BUSDUSDT", baseAsset="BUSD", quoteAsset="USDT", lowerBound=0.9990, upperBound=1.0010):
        self.accountInfo = None
        self.baseAsset = baseAsset
        self.binance = None
        self.lowerBound = lowerBound
        self.orderIdPrefix = "RT1"
        self.orders = {
            "all": [],
            "filled": [],
            "new": [],
            "rt": []
        }
        self.quoteAsset = quoteAsset
        self.symbol = symbol
        self.takeProfitAmount = 0.0001
        self.upperBound = upperBound

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
        iteration = 0
        nextOrders = []

        if price < 1 and price > self.lowerBound:
            while iteration < maxOrders:
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

        elif price > 1 and price < self.upperBound:

            while iteration < maxOrders:
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

            if (rtOrder.get("status") == "NEW" and
                float(rtOrder.get("origQty")) == float(checkOrder.get("quantity")) and
                float(rtOrder.get("price")) == float(checkOrder.get("price")) and
                rtOrder.get("symbol") == checkOrder.get("symbol") and
                    rtOrder.get("side") == checkOrder.get("side")):
                return True

        return False

    async def placeOrder(self, order={}):
        try:
            await self.binance.create_order(
                newClientOrderId=order.get("newClientOrderId"),
                price=order.get("price"),
                quantity=order.get("quantity"),
                side=order.get("side"),
                symbol=order.get("symbol"),
                timeInForce=order.get("timeInForce"),
                type=order.get("type"))
            await self.syncOrders()
            return True
        except:
            print("Error placeOrder")
            return False

    def printOrders(self, orders=[{}]):
        for order in orders:
            print(order.get("clientOrderId"), order.get("price"),
                  order.get("side"), order.get("status"))

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
                await self.placeOrder(order=takeProfitOrder)
                self.printOrders(orders=self.orders.get("new"))

    async def startTrading(self):
        try:
            if not await self.syncOrders():
                return False

            avgPrice = await self.binance.get_avg_price(symbol=self.symbol)
            price = round(float(avgPrice.get("price")), 4)
            print("price", price)
            await self.setTakeProfitOrders()

            nextOrders = self.determinNewRtOrders(price)
            # print("next orders", nextOrders)
            balanceBaseAsset = await self.binance.get_asset_balance(asset=self.baseAsset)
            balanceQuoteAsset = await self.binance.get_asset_balance(asset=self.quoteAsset)

            for newOrder in nextOrders:
                takeProfitOrder = self.createTakeProfitOrder(newOrder)

                if (not self.isRtOrderAlreadyOpen(newOrder) and
                        not self.isRtOrderAlreadyOpen(takeProfitOrder)):

                    balance = balanceQuoteAsset if newOrder.get(
                        "side") == orderSide.BUY.name else balanceBaseAsset

                    if (float(balance.get("free")) > float(newOrder.get("quantity"))):

                        print("open new order", newOrder,  balance.get(
                            "free"), newOrder.get("quantity"), balance.get("asset"))
                        await self.placeOrder(order=newOrder)

                    else:
                        print("NICHT GENUG GELD!!!")

                    self.printOrders(orders=self.orders.get("new"))
                    return True
        except:
            print("Fehler beim Trading")
            return False

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

    await bot.syncOrders(symbol=bot.symbol)
    bot.printOrders(orders=bot.orders.get("new"))
    run = True

    while run:
        await bot.startTrading()
        time.sleep(10)

    await bot.binance.close_connection()


if __name__ == "__main__":

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
