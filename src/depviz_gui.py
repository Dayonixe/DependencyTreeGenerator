"""Desktop entry point: python -m src.depviz_gui or python src/depviz_gui.py."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    __package__ = "src"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Depviz — explorateur graphique de dépendances Python.")
    parser.add_argument("--path", help="Projet à ouvrir au démarrage.")
    parser.add_argument("--smoke-test", metavar="DIRECTORY", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication
        from .desktop.window import MainWindow, example_path
        from .desktop.theme import configure_application
    except ImportError as error:
        message = ("L’interface graphique nécessite les dépendances Qt.\n"
                   "Exécutez : python -m pip install -r config/requirements-gui.txt\n\n" + str(error))
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Depviz", 0x10)
        return 1
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("Depviz")
    configure_application(app)
    if args.smoke_test and sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        # The Windows offscreen plugin has no system font database. Test with
        # installed fonts without bundling or redistributing those font files.
        for name in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
    window = MainWindow()
    window.show()
    if args.smoke_test:
        # Exercises the same worker, widgets and exporters in the frozen build.
        # No project code is executed. Used by the build workflow and GUI tests.
        output = Path(args.smoke_test).resolve()
        output.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 60
        timer = QTimer(window)

        def smoke():
            if window.job:
                if time.monotonic() < deadline:
                    return
                (output / "smoke.json").write_text(json.dumps({"error": "analysis timeout"}), encoding="utf-8")
                window.cancel_analysis()
                app.exit(1)
                return
            timer.stop()
            try:
                if window.result is None:
                    raise RuntimeError("No analysis result")
                key = next(iter(window.graph.nodes), "")
                window.select_node(key)
                window.graph.fit_graph()
                for kind in ("png", "svg", "dot", "txt", "ascii"):
                    window.export_to(str(output / ("graph." + kind if kind != "ascii" else "tree.txt")), kind)
                window.grab().save(str(output / "window.png"))
                analysis = window.result.analysis
                report = {"files": len(analysis.dependencies), "calls": len(analysis.calls),
                          "nodes": len(window.graph.nodes), "diagnostics": window.result.diagnostics}
                (output / "smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                app.exit(0)
            except Exception as error:
                (output / "smoke.json").write_text(json.dumps({"error": str(error)}), encoding="utf-8")
                app.exit(1)

        timer.timeout.connect(smoke)
        timer.start(250)
        QTimer.singleShot(0, lambda: window.open_project(args.path or str(example_path())))
    elif args.path:
        QTimer.singleShot(0, lambda: window.open_project(args.path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
