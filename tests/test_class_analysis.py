from textwrap import dedent

from src.call_analyzer import analyze_project
from src.models import ClassBase, ClassInfo, ClassMethod


def test_classes_methods_and_package_inheritance_are_resolved(make_project):
    root = make_project({
        "pkg/__init__.py": "from .models import Child\n",
        "pkg/base.py": dedent('''\
            from typing import Generic, TypeVar
            T = TypeVar("T")

            class Base(Generic[T]):
                def inherited(self):
                    pass
        '''),
        "pkg/models.py": dedent('''\
            from .base import Base as Parent

            class Child(Parent[str]):
                def __init__(self, value: str = "x"):
                    self.value = value

                @classmethod
                def build(cls):
                    return cls()

                @staticmethod
                def label():
                    return "child"

                @property
                def value_text(self):
                    return self.value

                async def refresh(self, *, force=False):
                    pass

            class Leaf(Child, UnknownBase):
                pass
        '''),
        "app.py": "from pkg import Child\n\nclass Application(Child):\n    pass\n",
    })

    classes = analyze_project(str(root)).classes
    assert [(item.file.replace("\\", "/"), item.name) for item in classes] == [
        ("app.py", "Application"),
        ("pkg/base.py", "Base"),
        ("pkg/models.py", "Child"),
        ("pkg/models.py", "Leaf"),
    ]
    child = next(item for item in classes if item.name == "Child")
    assert [(base.expression, base.target_file.replace("\\", "/"), base.target_class)
            for base in child.bases] == [("Parent[str]", "pkg/base.py", "Base")]
    assert [(method.name, method.kind) for method in child.methods] == [
        ("__init__", "method"),
        ("build", "classmethod"),
        ("label", "staticmethod"),
        ("value_text", "property"),
        ("refresh", "async"),
    ]
    assert child.methods[0].signature == "self, value: str='x'"
    assert child.methods[-1].signature == "self, *, force=False"

    leaf = next(item for item in classes if item.name == "Leaf")
    assert leaf.bases[0].expression == "Child"
    assert leaf.bases[0].target_file.replace("\\", "/") == "pkg/models.py"
    assert leaf.bases[0].target_class == "Child"
    assert leaf.bases[1] == ClassBase("UnknownBase")
    application = classes[0]
    assert application.bases[0].expression == "Child"
    assert application.bases[0].target_file.replace("\\", "/") == "pkg/models.py"
    assert application.bases[0].target_class == "Child"


def test_nested_classes_and_selection_filters(make_project):
    root = make_project({
        "app.py": dedent('''\
            class Visible:
                class Nested:
                    def method(self, value):
                        pass
        '''),
        "pkg/hidden.py": "class Hidden:\n    pass\n",
    })

    analysis = analyze_project(str(root), max_depth=0)
    assert analysis.classes == [
        ClassInfo("app.py", "Visible", 1),
        ClassInfo("app.py", "Visible.Nested", 2, methods=(ClassMethod("method", "self, value", 3),)),
    ]
    assert analyze_project(str(root), ignore=["pkg"]).classes == analysis.classes


def test_class_usages_are_recorded_only_from_methods(make_project):
    root = make_project({
            "pkg/__init__.py": "from .models import Tool\n",
            "pkg/models.py": dedent('''\
                class Tool:
                    @classmethod
                    def build(cls):
                        return cls()
            '''),
            "services.py": dedent('''\
                import pkg
                from pkg import Tool as ImportedTool

                class Service:
                    def create(self):
                        return ImportedTool()

                    @staticmethod
                    def prepare():
                        return ImportedTool.build()

                class Controller:
                    def create(self):
                        return pkg.Tool()

                ImportedTool()
            '''),
            "local.py": dedent('''\
                class Local:
                    def clone(self):
                        return Local()
            '''),
    })

    usages = analyze_project(str(root)).class_usages
    assert [
        (usage.source_file.replace("\\", "/"), usage.source_class, usage.source_method,
         usage.expression, usage.lineno, usage.target_file.replace("\\", "/"), usage.target_class)
        for usage in usages
    ] == [
        ("services.py", "Service", "create", "ImportedTool", 6, "pkg/models.py", "Tool"),
        ("services.py", "Service", "prepare", "ImportedTool.build", 10, "pkg/models.py", "Tool"),
        ("services.py", "Controller", "create", "pkg.Tool", 14, "pkg/models.py", "Tool"),
    ]
