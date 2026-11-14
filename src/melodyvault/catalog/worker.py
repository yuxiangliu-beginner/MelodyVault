"""One QThread per user search; connections stay inside their thread."""
import logging
from pathlib import Path
import threading
import time
from PySide6.QtCore import QThread, Signal
from melodyvault.catalog.models import ArtistChoiceRequired, CatalogCancelled
from melodyvault.catalog.musicbrainz import MusicBrainzClient
from melodyvault.catalog.service import CatalogService
from melodyvault.database.catalog import CatalogRepository


class CatalogWorker(QThread):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)
    choices_required = Signal(object)
    partial = Signal(object)

    def __init__(self, database_path: Path, query: str, force_refresh: bool = False,
                 selected_mbid: str | None = None, parent=None):
        super().__init__(parent)
        self.database_path = database_path
        self.query = query
        self.force_refresh = force_refresh
        self.selected_mbid = selected_mbid
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        started=time.perf_counter()
        try:
            repository = CatalogRepository(self.database_path)
            with MusicBrainzClient(repository, self.cancel_event, self.force_refresh) as client:
                result = CatalogService(repository, client, self.progress.emit, self.partial.emit).search_catalog(self.query, self.selected_mbid)
            result.summary['catalog_seconds']=time.perf_counter()-started
            self.completed.emit(result)
        except ArtistChoiceRequired as error:
            self.choices_required.emit(error.candidates)
        except CatalogCancelled as error:
            self.cancelled.emit(str(error))
        except Exception as error:
            logging.getLogger("melodyvault.catalog").exception("Catalog search failed")
            self.failed.emit(f"{type(error).__name__}: {error}")
