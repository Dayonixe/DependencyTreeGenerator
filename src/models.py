from dataclasses import dataclass


ModuleMap = dict[str, list[str]]


@dataclass(frozen=True)
class ImportReference:
    """An import statement, retaining the distinction between modules and names."""

    module: str
    name: str | None = None
    level: int = 0
    alias: str | None = None

    @property
    def binding(self) -> str:
        return self.alias or self.name or self.module.split(".", 1)[0]

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
            statement = f"import {self.module}"
        else:
            statement = f"from {self.base} import {self.name}"
        return statement + (f" as {self.alias}" if self.alias else "")


@dataclass(frozen=True)
class FunctionCall:
    """A statically resolved call to a function defined in another project file."""

    source_file: str
    caller: str
    expression: str
    lineno: int
    target_file: str
    target_function: str
    target_lineno: int
    col_offset: int = 0


@dataclass
class ProjectAnalysis:
    dependencies: dict[str, list[ImportReference]]
    module_map: ModuleMap
    calls: list[FunctionCall]
