import pytest


@pytest.fixture
def make_project(tmp_path):
    """Create a small source tree without importing any of its modules."""
    def create(files):
        for relative, content in files.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content, encoding="utf-8")
        return tmp_path
    return create
