from .helpers import numbers


class Calculation:
    def apply(self, left, right):
        return left + right


def calculate(left, right):
    return numbers.add(left, right)
