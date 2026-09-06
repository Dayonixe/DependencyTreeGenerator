from dataclasses import dataclass


ModuleMap = dict[str, list[str]]


@dataclass(frozen=True)
class ImportReference:
    """An import statement, retaining the distinction between modules and names."""

    module: str
    name: str | None = None
    level: int = 0

    @property
    def base(self) -> str:
        return "." * self.level + self.module

    @property
    def target(self) -> str:
        if self.name is None or self.name == "*":
            return self.base
        separator = "." if self.module else ""
        return f"{self.base}{separator}{self.name}"

    def __str__(self) -> str:
        if self.name is None:
            return f"import {self.module}"
        return f"from {self.base} import {self.name}"
