from .helpers.numbers import add
from .operations import Calculation


def display(value):
    print(add(value, 0))


class Formatter:
    def format(self, value):
        return str(value)

    def calculation(self):
        return Calculation()


class ConsoleFormatter(Formatter):
    @staticmethod
    def label():
        return "console"

    async def format_async(self, value):
        return self.format(value)
