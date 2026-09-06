# Third-party components in Depviz Desktop

The portable application bundles the CPython interpreter, Qt for Python
(PySide6-Essentials and Shiboken 6.10.2), and the Python `graphviz` 0.21 wrapper.
Its bootloader is built by PyInstaller 6.20.0. Native Graphviz is not bundled.

Third-party notices shipped by the installed distributions are copied to
`THIRD_PARTY_LICENSES/`. The Qt libraries remain separate shared libraries in the
portable directory. Depviz's Python source is included under `source/`.

Upstream source and license references:

- [CPython source and license](https://github.com/python/cpython).
- [Qt for Python 6.10.2 source](https://github.com/pyside/pyside-setup/tree/v6.10.2).
- [Qt 6.10.2 source archives](https://download.qt.io/archive/qt/6.10/6.10.2/submodules/).
- [Qt license texts](https://doc.qt.io/qt-6.10/licenses.html).
- [Third-party components used in Qt](https://doc.qt.io/qt-6.10/licenses-used-in-qt.html).
- [Python graphviz 0.21 source and license](https://github.com/xflr6/graphviz/tree/0.21).
- [PyInstaller 6.20.0 source and license](https://github.com/pyinstaller/pyinstaller/tree/v6.20.0).

Qt and its bindings are distributed with their upstream license choices. See the
bundled texts and upstream attribution pages for the individual components.
