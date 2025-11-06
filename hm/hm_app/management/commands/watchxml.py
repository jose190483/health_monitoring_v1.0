from django.core.management.base import BaseCommand
from watchdog.observers import Observer
from ...xml_watcher import XMLHandler, WATCH_DIRS
import time, os, logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Watch all business unit folders and automatically store new XML files into the database."

    def handle(self, *args, **options):
        observer = Observer()

        # Create and watch all BU folders
        for bu, path in WATCH_DIRS.items():
            os.makedirs(path, exist_ok=True)
            event_handler = XMLHandler()
            observer.schedule(event_handler, path, recursive=False)
            self.stdout.write(self.style.SUCCESS(f"📂 Watching folder for {bu}: {path}"))

        observer.start()

        try:
            while True:
                time.sleep(2)
        except KeyboardInterrupt:
            observer.stop()
            self.stdout.write(self.style.WARNING("👋 Watcher stopped manually."))
        observer.join()
