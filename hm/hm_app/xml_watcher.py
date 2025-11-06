import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from django.utils import timezone
from django.contrib.auth import get_user_model

from .utils import parse_xml_dynamic
from .models import XMLData, ServiceComponentData, ApplicationData

logger = logging.getLogger(__name__)

User = get_user_model()

# 🧭 All business unit watch folders
WATCH_DIRS = {
    "TPS": r"C:\Users\waltjos01\PycharmProjects\health_monitoring_v1.0\hm\hm_app\xml_files\incoming\TPS",
    "OFS": r"C:\Users\waltjos01\PycharmProjects\health_monitoring_v1.0\hm\hm_app\xml_files\incoming\OFS",
    "OFE": r"C:\Users\waltjos01\PycharmProjects\health_monitoring_v1.0\hm\hm_app\xml_files\incoming\OFE",
    "Admin": r"C:\Users\waltjos01\PycharmProjects\health_monitoring_v1.0\hm\hm_app\xml_files\incoming\Admin",
}


class XMLHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".xml"):
            return

        time.sleep(1)  # wait for the file to finish writing

        file_path = event.src_path
        try:
            logger.info(f"[Watcher] Detected file: {file_path}")

            # Determine Business Unit from parent folder
            parent_dir = os.path.basename(os.path.dirname(file_path))
            bu = parent_dir if parent_dir in WATCH_DIRS else "Admin"

            parsed = parse_xml_dynamic(file_path)
            fname = os.path.basename(file_path)

            # Identify XML type by top tag
            top_keys = list(parsed.keys()) if isinstance(parsed, dict) else []
            top_tag = top_keys[0] if top_keys else fname

            if (
                "ServiceMetrics" in top_tag
                or "ServiceComponent" in top_tag
                or "service" in top_tag.lower()
            ):
                ServiceComponentData.objects.create(
                    file_name=fname,
                    data=parsed,
                    business_unit=bu,
                    created_at=timezone.now(),
                )
                logger.info(f"[Watcher] ✅ Stored Service Data: {fname} (BU={bu})")

            elif "Application" in top_tag or "application" in fname.lower():
                ApplicationData.objects.create(
                    file_name=fname,
                    data=parsed,
                    business_unit=bu,
                    created_at=timezone.now(),
                )
                logger.info(f"[Watcher] ✅ Stored Application Data: {fname} (BU={bu})")

            else:
                XMLData.objects.create(
                    file_name=fname,
                    data=parsed,
                    business_unit=bu,
                    created_at=timezone.now(),
                )
                logger.info(f"[Watcher] ✅ Stored Server Metrics: {fname} (BU={bu})")

        except Exception:
            logger.exception(f"[Watcher] ❌ Failed to process {file_path}")


def start_watcher():
    observer = Observer()
    for bu, path in WATCH_DIRS.items():
        os.makedirs(path, exist_ok=True)
        event_handler = XMLHandler()
        observer.schedule(event_handler, path, recursive=False)
        logger.info(f"[Watcher] 🔍 Watching folder for {bu}: {path}")

    observer.start()
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()



