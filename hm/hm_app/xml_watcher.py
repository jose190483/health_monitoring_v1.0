import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from django.utils import timezone
from django.contrib.auth import get_user_model

from .utils import parse_xml_dynamic
from .models import (
    ServerMetricsLive,
    ServerMetricsHistory,
    ServiceMetricsLive,
    ServiceMetricsHistory,
    ServiceComponentLive,
    ServiceComponentHistory,
    ApplicationDashboardLive,
    ApplicationDashboardHistory,
    ApplicationListLive,
    ApplicationListHistory,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# 🧭 Watch directories per BU
WATCH_DIRS = {
    "TPS": r"C:\Users\2671706\Python Training\xml_project_11\xml_project_11\xml_app\xml_files\incoming\TPS",
    "OFS": r"C:\Users\2671706\Python Training\xml_project_11\xml_project_11\xml_app\xml_files\incoming\OFS",
    "OFE": r"C:\Users\2671706\Python Training\xml_project_11\xml_project_11\xml_app\xml_files\incoming\OFE",
    "Admin": r"C:\Users\2671706\Python Training\xml_project_11\xml_project_11\xml_app\xml_files\incoming\Admin",
}


# 🧩 Utility functions
def extract_hostname(parsed):
    """Extract hostname or server name from parsed XML."""
    if not parsed or not isinstance(parsed, dict):
        return None

    def deep_search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in ('@hostname', 'hostname', 'host', 'name') and v:
                    return str(v).strip()
                res = deep_search(v)
                if res:
                    return res
        elif isinstance(obj, list):
            for el in obj:
                res = deep_search(el)
                if res:
                    return res
        return None

    return deep_search(parsed)


def extract_application_name(parsed):
    """Extract Application name from parsed XML."""
    if not parsed or not isinstance(parsed, dict):
        return None

    data_root = parsed.get("ApplicationList") or parsed.get("Applications") or parsed.get("ApplicationDashboard") or parsed
    apps = data_root.get("Application") or data_root.get("application") or []
    if isinstance(apps, dict):
        apps = [apps]

    for app in apps:
        name = app.get("Name") or app.get("@name")
        if name:
            return str(name).strip()

    return None


def detect_xml_type(parsed, fname):
    """Identify the XML type by its top-level tag or structure."""
    if not parsed or not isinstance(parsed, dict):
        return "unknown"

    top_keys = list(parsed.keys())
    top_tag = top_keys[0].strip() if top_keys else fname
    top_tag_lower = top_tag.lower()

    # Classification logic
    if "servermetrics" in top_tag_lower:
        return "server"
    elif "servicemetrics" in top_tag_lower:
        return "service_metrics"
    elif "servicecomponent" in top_tag_lower or "component" in top_tag_lower or "componentdetails" in top_tag_lower:
        return "service_component"
    # elif any(x in top_tag_lower for x in ["applicationdashboard","applicationlist", "applicationmetrics", "application_status", "application"]):
    #     return "application"
    elif "applicationdashboard" in top_tag_lower:
        return "app_dashboard"
    elif "applicationlist" in top_tag_lower:
        return "app_list"
    else:
        # fallback detection by internal structure
        text_repr = str(parsed).lower()
        if "cpu" in text_repr and "ram" in text_repr:
            return "server"
        if "associated_component" in text_repr:
            return "service_component"
        if "<service" in text_repr or "servicemetrics" in text_repr:
            return "service_metrics"
        if "responsetimems" in text_repr or "availabilityuptimepercent" in text_repr or "loadbalancerrequestcount" in text_repr:
            return "app_dashboard"
        if "server type=" in text_repr or "@type" in text_repr:
            return "app_list"

        return "unknown"


# 🧠 Main XML event handler
class XMLHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".xml"):
            return

        # wait for file write completion
        time.sleep(1)
        file_path = event.src_path

        try:
            logger.info(f"[Watcher] 📄 Detected file: {file_path}")

            parent_dir = os.path.basename(os.path.dirname(file_path))
            bu = parent_dir if parent_dir in WATCH_DIRS else "Admin"

            parsed = parse_xml_dynamic(file_path)
            fname = os.path.basename(file_path)
            xml_type = detect_xml_type(parsed, fname)
            print(xml_type)
            hostname = extract_hostname(parsed)
            app_name = extract_application_name(parsed)
            now = timezone.now()

            logger.info(f"[Watcher] 🧩 Type={xml_type}, Host={hostname}, App={app_name}, BU={bu}")

            # ✅ Server Metrics Handling
            if xml_type == "server":
                ServerMetricsHistory.objects.create(
                    file_name=fname,
                    hostname=hostname,
                    data=parsed,
                    business_unit=bu,
                    created_at=now
                )
                ServerMetricsLive.objects.update_or_create(
                    hostname=hostname,
                    business_unit=bu,
                    defaults={"data": parsed, "updated_at": now}
                )
                logger.info(f"[Watcher] ✅ Stored SERVER metrics for {hostname} ({bu})")

            # ✅ Service Metrics Handling
            elif xml_type == "service_metrics":
                ServiceMetricsHistory.objects.create(
                    file_name=fname,
                    hostname=hostname,
                    data=parsed,
                    business_unit=bu,
                    created_at=now
                )
                if hostname:
                    ServiceMetricsLive.objects.update_or_create(
                        hostname=hostname,
                        business_unit=bu,
                        defaults={"data": parsed, "updated_at": now}
                    )
                    logger.info(f"[Watcher] ✅ Stored SERVICE METRICS for {hostname} ({bu})")

            # ✅ Service Component (Details)
            elif xml_type == "service_component":
                ServiceComponentHistory.objects.create(
                    file_name=fname,
                    hostname=hostname,
                    data=parsed,
                    business_unit=bu,
                    created_at=now,
                )
                if hostname:
                    ServiceComponentLive.objects.update_or_create(
                        hostname=hostname,
                        business_unit=bu,
                        defaults={"data":parsed, "updated_at":now},
                    )
                    logger.info(f"[Watcher] ✅ Stored SERVICE COMPONENT DETAILS for {hostname} ({bu})")

            # ✅ Application Metrics Handling
            elif xml_type == "app_dashboard":
                ApplicationDashboardHistory.objects.create(
                    file_name=fname,
                    app_name=app_name,
                    data=parsed,
                    business_unit=bu,
                    created_at=now
                )
                ApplicationDashboardLive.objects.update_or_create(
                    app_name=app_name,
                    business_unit=bu,
                    defaults={"data": parsed, "updated_at": now}
                )
                logger.info(f"[Watcher] ✅ Stored APPLICATION data for {app_name} ({bu})")

            elif xml_type == "app_list":
                app_name = extract_application_name(parsed)
                ApplicationListHistory.objects.create(
                    file_name=fname,
                    app_name=app_name,
                    data=parsed,
                    business_unit=bu,
                    created_at=now
                )

                ApplicationListLive.objects.update_or_create(
                    app_name=app_name,
                    business_unit=bu,
                    defaults={"data": parsed, "updated_at": now}
                )

                logger.info(f"[Watcher] ✅ Stored APPLICATION LIST for {app_name} ({bu})")

            else:
                logger.warning(f"[Watcher] ⚠️ Unclassified XML type: {fname}")

        except Exception:
            logger.exception(f"[Watcher] ❌ Failed to process file: {file_path}")


# 🚀 Watcher launcher for all BUs
def start_watcher():
    observer = Observer()
    for bu, path in WATCH_DIRS.items():
        os.makedirs(path, exist_ok=True)
        event_handler = XMLHandler()
        observer.schedule(event_handler, path, recursive=False)
        logger.info(f"[Watcher] 👀 Watching folder for {bu}: {path}")

    observer.start()
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
