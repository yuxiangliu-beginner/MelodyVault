"""Desktop composition root; no network work during startup."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from melodyvault import __version__
from melodyvault.config import load_settings
from melodyvault.database import initialize_database
from melodyvault.logging_setup import close_logging, configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MelodyVault Windows desktop")
    parser.add_argument("--version", action="version", version=f"MelodyVault {__version__}")
    parser.add_argument("--config", type=Path, help="Explicit TOML configuration")
    parser.add_argument("--data-dir", type=Path, help="Override private runtime directory")
    parser.add_argument("--init-db", action="store_true", help="Initialize database without Qt, then exit")
    parser.add_argument("--smoke", action="store_true", help="Show window, run event loop, then exit")
    args = parser.parse_args(argv)
    logger = None
    try:
        settings = load_settings(args.config, args.data_dir)
        settings.prepare()
        logger = configure_logging(settings.log_dir, settings.log_level)
        version = initialize_database(settings.database_path)
        logger.info("Application initialized; schema version=%s", version)
        if args.init_db:
            print(json.dumps({"application": "MelodyVault", "schema_version": version,
                              "database": str(settings.database_path)}, ensure_ascii=False))
            return 0
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from melodyvault.ui.music_window import MusicWindow as MainWindow
        application = QApplication([sys.argv[0]])
        application.setApplicationName("MelodyVault")
        application.setApplicationVersion(__version__)
        window = MainWindow(settings.database_path)
        window.show()
        if args.smoke:
            def finish_smoke() -> None:
                print("GUI_SMOKE_OK: MelodyVault window visible; event loop running", flush=True)
                window.close()
                application.quit()
            QTimer.singleShot(300, finish_smoke)
        return application.exec()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        # Exception text can include malformed config secrets; report only its type.
        if logger is not None:
            logger.error("Startup failed (%s)", type(error).__name__)
        print(f"MelodyVault startup failed ({type(error).__name__}); check config and data directory.",
              file=sys.stderr)
        return 1
    finally:
        close_logging()
