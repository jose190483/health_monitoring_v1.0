import os, tempfile, logging, re
from datetime import timedelta, datetime
import io
import base64
import matplotlib
from django.conf import settings

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.utils.dateformat import format as df_format
from .models import CustomUser
from .forms import XMLUploadForm
from .utils import parse_xml_dynamic
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import UserRegistrationForm, CustomLoginForm
from django.shortcuts import render, get_object_or_404
from .utils import parse_xml_dynamic  # if needed
from urllib.parse import unquote_plus
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import ApplicationData, ServiceComponentData, XMLData
from .utils import normalize_key

 # reuse your helper or copy it here


logger = logging.getLogger(__name__)


def get_color(value):
    if not value:
        return 'green'
    try:
        v = float(str(value).replace('%', '').strip())
    except Exception:
        return 'green'
    if v <= 50:
        return 'green'
    elif v <= 75:
        return 'yellow'
    else:
        return 'red'


def portal_home(request):
    return render(request, 'home.html')


def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            raw_password = form.cleaned_data['password']
            user.set_password(raw_password)
            user.save()
            messages.success(request, 'Registration successful. Please log in.')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data['username']
            password = form.cleaned_data['password']
            # business_unit = form.cleaned_data['business_unit']
            user = authenticate(request, username=email, password=password)

            if user is not None:
                    # and user.business_unit == business_unit):
                login(request, user)
                messages.success(request, f"Welcome {user.email}! BU: {user.business_unit}")
                return redirect('dashboard_view')
            else:
                messages.error(request, 'Invalid business unit or credentials.')
    else:
        form = CustomLoginForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')


def upload_view(request):
    form = XMLUploadForm(request.POST or None, request.FILES or None)
    user_unit = request.user.business_unit
    if request.method == 'POST' and form.is_valid():
        xml_file = form.cleaned_data['xml_file']
        filename = os.path.basename(xml_file.name)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xml') as tmp:
                for chunk in xml_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name
            data = parse_xml_dynamic(tmp_path)

            XMLData.objects.create(
                file_name=filename,
                data=data,
                user=request.user,  # who uploaded it
                business_unit=request.user.business_unit,  # their unit
            )

            messages.success(request, f"{filename} uploaded successfully.")
            return redirect('dashboard_view')
        except Exception as e:
            logger.exception("Upload error")
            messages.error(request, f"Error parsing XML: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)

    return render(request, 'portal_upload.html', {'form': form, 'name': name.upper(), 'business_unit': user_unit,})


def dashboard_view(request):
    user_unit = request.user.business_unit
    selected_unit = request.GET.get('unit')  # from dropdown filter

    # Admin can filter by any unit or see all
    if user_unit == 'Admin':
        if selected_unit and selected_unit != 'All':
            xml_entries = XMLData.objects.filter(business_unit=selected_unit).order_by('-created_at')
        else:
            xml_entries = XMLData.objects.all().order_by('-created_at')
    else:
        # Regular users can only see their own unit’s data
        xml_entries = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at')

    # build servers data for template
    servers = []
    for entry in xml_entries:
        data = entry.data.get('ServerMetrics', {})
        servers_data = data.get('Server', [])
        if isinstance(servers_data, dict):
            servers_data = [servers_data]

        for server in servers_data:
            disks = server.get('Disks', {}).get('Disk', [])
            if isinstance(disks, dict):
                disks = [disks]
            disk_list = []
            for d in disks:
                drive = d.get('@Drive', '')
                usage = d.get('#text', '')
                disk_list.append({
                    'drive': drive,
                    'usage': usage,
                    'color': get_color(usage)
                })

            servers.append({
                # 'source_file': entry.file_name,
                # 'uploaded_at': entry.created_at,
                'hostname': server.get('@Hostname'),
                'ip': server.get('@IP'),
                'status': server.get('@Status'),
                'cpu': server.get('CPU'),
                'ram': server.get('RAM'),
                'cpu_color': get_color(server.get('CPU')),
                'ram_color': get_color(server.get('RAM')),
                'network_latency': server.get('Network_Latency'),
                'last_boot': server.get('Last_Boot_Time'),
                'disks': disk_list,
            })
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ' ,email)

    return render(request, 'portal_dashboard.html', {
        'servers': servers,
        'business_unit': user_unit,
        'selected_unit': selected_unit or 'All',
        'name': name.upper()
    })

@login_required
def server_services_view(request, hostname):
    hostname = unquote_plus(hostname).strip()
    user_unit = request.user.business_unit

    # choose entries visible to user
    if user_unit == 'Admin':
        entries = ServiceComponentData.objects.all().order_by('-created_at')
    else:
        entries = ServiceComponentData.objects.filter(business_unit=user_unit).order_by('-created_at')

    svc_map = {}  # normalized_service_name -> {service_name, status, source_file, uploaded_at}

    for entry in entries:
        # prefer files that are service metrics (top tag contains "ServiceMetrics" or filename hints)
        top = None
        if isinstance(entry.data, dict):
            top = list(entry.data.keys())[0] if entry.data else None

        is_metrics = False
        if top and 'ServiceMetrics' in top:
            is_metrics = True
        elif isinstance(entry.file_name, str) and 'servicemetrics' in entry.file_name.lower():
            is_metrics = True
        # skip non-metrics: they don't carry the simple service->status mapping
        if not is_metrics:
            continue

        # locate Server nodes
        data_root = entry.data.get(top) if top and top in entry.data else entry.data
        servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
        if isinstance(servers, dict):
            servers = [servers]

        for s in servers:
            host_val = (s.get('@Hostname') or s.get('Hostname') or '').strip()
            if normalize_key(host_val) != normalize_key(hostname):
                continue

            # services may be 'service1','service2' ... or 'service' list/dict
            for key, value in s.items():
                if not key.lower().startswith('service'):
                    continue
                # value might be dict with '@name' and '#text' or plain text
                if isinstance(value, dict):
                    svc_name = value.get('@name') or value.get('name') or key
                    # if status appears as text (child text) or attribute
                    svc_status = value.get('#text') or value.get('@status') or value.get('status') or ''
                else:
                    # plain text or string
                    svc_name = value if isinstance(value, str) else key
                    svc_status = ''  # no explicit status inside this type
                if not svc_name:
                    svc_name = key

                n = normalize_key(svc_name)
                # store latest (entries ordered by -created_at)
                if n not in svc_map:
                    svc_map[n] = {
                        'service_name': svc_name,
                        'status': svc_status,
                        # 'source_file': entry.file_name,
                        # 'uploaded_at': entry.created_at
                    }
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)
    # Also handle cases where ServiceMetrics used 'service' key with list/dict of @name and inner text as status:
    # (example earlier had <service1 name="...">Running</service1> which we covered above)
    services = sorted(svc_map.values(), key=lambda x: (x['service_name'] or '').lower())

    return render(request, 'server_services.html', {
        'hostname': hostname,
        'services': services,
        'name': name.upper(),
        'business_unit': user_unit,
    })



# @login_required
# def service_details_view(request, hostname, service_name):
#     hostname = unquote_plus(hostname).strip()
#     service_name = unquote_plus(service_name).strip()
#     user_unit = request.user.business_unit
#     # print("Debug >> hostname: ",hostname)
#     # print("Debug >> service name: ",service_name)
#     if user_unit == 'Admin':
#         entries = ServiceComponentData.objects.all().order_by('-created_at')
#     else:
#         entries = ServiceComponentData.objects.filter(business_unit=user_unit).order_by('-created_at')
#
#     components = []
#
#     for entry in entries:
#         data_root = entry.data.get('ServiceComponent') or entry.data.get('ServiceMetrics') or entry.data
#         servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
#         if isinstance(servers, dict):
#             servers = [servers]
#
#         for s in servers:
#             host = (s.get('@Hostname') or s.get('Hostname') or '').strip()
#             if not host or host.lower() != hostname.lower():
#                 continue
#
#             svc_entries = s.get('service')
#             if not svc_entries:
#                 continue
#             if isinstance(svc_entries, dict):
#                 svc_entries = [svc_entries]
#
#             # find service by @name (case-insensitive)
#             matched = None
#             for sv in svc_entries:
#                 sv_name = (sv.get('@name') or sv.get('name') or '').strip()
#                 if sv_name and sv_name.lower() == service_name.lower():
#                     matched = sv
#                     break
#             if not matched:
#                 continue
#
#             assoc = matched.get('associated_component') or matched.get('associated') or matched.get('associated_component_list')
#             if not assoc:
#                 continue
#             assoc_list = assoc if isinstance(assoc, list) else [assoc]
#
#             for comp in assoc_list:
#                 comp_name = comp.get('@name') or comp.get('name') or ''
#                 comp_status = comp.get('@status') or comp.get('status') or ''
#                 comp_url = comp.get('@url') or comp.get('url') or ''
#                 comp_log = (comp.get('@logFile') or comp.get('logfile') or comp.get('logFile') or '')
#                 actual_service = comp.get('@actual_service_name') or comp.get('actual_service_name') or ''
#                 components.append({
#                     'component_name': comp_name,
#                     'status': comp_status,
#                     'url': comp_url,
#                     'logfile': comp_log,
#                     'actual_service': actual_service,
#                     # 'source_file': entry.file_name,
#                     # 'uploaded_at': entry.created_at
#                 })
#
#     return render(request, 'service_details.html', {
#         'hostname': hostname,
#         'service_name': service_name,
#         'components': components
#     })
#

@login_required
def service_details_view(request, hostname, service_name):
    hostname = unquote_plus(hostname).strip()
    service_name = unquote_plus(service_name).strip()
    user_unit = request.user.business_unit

    if user_unit == 'Admin':
        entries = ServiceComponentData.objects.all().order_by('-created_at')
    else:
        entries = ServiceComponentData.objects.filter(business_unit=user_unit).order_by('-created_at')

    components = []

    for entry in entries:
        # Only look at ServiceComponent files (top tag or filename)
        top = None
        if isinstance(entry.data, dict):
            top = list(entry.data.keys())[0] if entry.data else None

        is_component_file = False
        if top and 'ServiceComponent' in top:
            is_component_file = True
        elif isinstance(entry.file_name, str) and 'servicecomponent' in entry.file_name.lower():
            is_component_file = True
        # also accept generic 'service' or files where associated_component exists
        if not is_component_file:
            # But still inspect if the parsed JSON seems to contain associated_component
            # (some producers may not set root tag exactly)
            pass

        # data root and Servers list
        data_root = entry.data.get(top) if (top and top in entry.data) else entry.data
        servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
        if isinstance(servers, dict):
            servers = [servers]

        for s in servers:
            host_val = (s.get('@Hostname') or s.get('Hostname') or '').strip()
            if normalize_key(host_val) != normalize_key(hostname):
                continue

            # services may be under 'service' key as list/dict
            svc_entries = s.get('service') or s.get('Service') or {}
            if isinstance(svc_entries, dict):
                svc_entries = [svc_entries]
            if not svc_entries:
                # maybe services are directly children 'service1'...'serviceN' that contain associated_component
                # iterate through s's keys and find those starting with 'service' and containing associated_component
                for k, v in s.items():
                    if not k.lower().startswith('service'):
                        continue
                    sv = v
                    if isinstance(sv, dict):
                        sv_name = sv.get('@name') or sv.get('name') or ''
                        if normalize_key(sv_name) == normalize_key(service_name):
                            assoc = sv.get('associated_component') or sv.get('associated') or sv.get('associated_component_list')
                            if assoc:
                                assoc_list = assoc if isinstance(assoc, list) else [assoc]
                                for comp in assoc_list:
                                    comp_name = comp.get('@name') or comp.get('name') or ''
                                    comp_status = comp.get('@status') or comp.get('status') or ''
                                    comp_url = comp.get('@url') or comp.get('url') or ''
                                    comp_log = (comp.get('@logFile') or comp.get('logfile') or '')
                                    components.append({
                                        'component_name': comp_name,
                                        'status': comp_status,
                                        'url': comp_url,
                                        'logfile': comp_log,
                                        'source_file': entry.file_name
                                    })
                continue

            # Now svc_entries is a list of service dicts — find the matching one by @name
            for sv in svc_entries:
                if not isinstance(sv, dict):
                    continue
                sv_name = (sv.get('@name') or sv.get('name') or '').strip()
                if normalize_key(sv_name) != normalize_key(service_name):
                    continue
                assoc = sv.get('associated_component') or sv.get('associated') or sv.get('associated_component_list')
                if not assoc:
                    continue
                assoc_list = assoc if isinstance(assoc, list) else [assoc]
                for comp in assoc_list:
                    comp_name = comp.get('@name') or comp.get('name') or ''
                    comp_status = comp.get('@status') or comp.get('status') or ''
                    comp_url = comp.get('@url') or comp.get('url') or ''
                    comp_log = comp.get('@logFile') or comp.get('@logfile') or comp.get('logFile') or comp.get('logfile') or ''
                    actual_service = comp.get('@actual_service_name') or comp.get('actual_service_name') or ''
                    components.append({
                        'component_name': comp_name,
                        'status': comp_status,
                        'url': comp_url,
                        'logfile': comp_log,
                        'actual_service': actual_service,
                    })
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)
    # sort components by name
    # components = sorted(components, key=lambda x: (x.get('component_name') or '').lower())
    return render(request, 'service_details.html', {
        'hostname': hostname,
        'service_name': service_name,
        'components': components,
        'name': name.upper(),
        'business_unit': user_unit,
    })


@login_required
def application_list_view(request):
    user_unit = request.user.business_unit
    if user_unit == 'Admin':
        entries = ApplicationData.objects.all().order_by('-created_at')
    else:
        entries = ApplicationData.objects.filter(business_unit=user_unit).order_by('-created_at')

    applications = []
    for entry in entries:
        data_root = entry.data.get('ApplicationList') or entry.data.get('Application') or entry.data
        apps = data_root.get('Application', []) if isinstance(data_root, dict) else []
        if isinstance(apps, dict):
            apps = [apps]

        for app in apps:
            name = app.get('Name') or app.get('@name') or ''
            accessible = str(app.get('Accessible') or '')
            response = app.get('ResponseTime') or ''
            service_status = app.get('ServiceStatus') or ''
            if name and service_status != "":
                applications.append({
                    'name': name.strip(),
                    'accessible': accessible,
                    'response_time': response,
                    'service_status': service_status,
                    'file': entry.file_name,
                })
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)

    return render(request, 'application_list.html', {'applications': applications, 'name': name.upper(), 'business_unit': user_unit,})


@login_required
def application_detail_view(request, app_name):
    app_name = unquote_plus(app_name).strip()
    user_unit = request.user.business_unit

    if user_unit == 'Admin':
        entries = ApplicationData.objects.all().order_by('-created_at')
    else:
        entries = ApplicationData.objects.filter(business_unit=user_unit).order_by('-created_at')

    servers = []
    for entry in entries:
        data_root = entry.data.get('ApplicationList') or entry.data.get('Application') or entry.data
        apps = data_root.get('Application', []) if isinstance(data_root, dict) else []
        if isinstance(apps, dict):
            apps = [apps]

        for app in apps:
            name = app.get('@name') or app.get('Name')
            if not name or name.strip().lower() != app_name.lower():
                continue

            srv_list = app.get('Server', [])
            if isinstance(srv_list, dict):
                srv_list = [srv_list]

            for s in srv_list:
                servers.append({
                    'type': s.get('@type') or '',
                    'name': s.get('@name') or '',
                    'status': s.get('@status') or '',
                })
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)

    return render(request, 'application_detail.html', {
        'app_name': app_name,
        'servers': servers,
        'name': name.upper(),
        'business_unit': user_unit,
    })



def _to_float(s):
    """Safe convert: '15' or '15%' -> 15.0; returns None on failure."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    # remove percent sign and non-numeric trailing text
    s = re.sub(r'[^0-9.\-]', '', s)
    try:
        return float(s)
    except Exception:
        return None

def _normalize_hostname(s):
    return (s or '').strip()

@login_required
def metrics_page_view(request):
    # page with three charts: CPU line, RAM line, Disk donut
    return render(request, 'metrics_page.html', {})


@login_required
def metrics_data_api(request):
    """
    Returns JSON with time-series CPU and RAM for a host, plus latest disk usage.
    Query params:
      - hostname (optional) : if provided, return metrics for that host only
      - limit (optional) : number of historical points to return, default 20
    """
    user_unit = request.user.business_unit
    hostname = request.GET.get('hostname')  # may be None -> aggregate
    try:
        limit = int(request.GET.get('limit', 20))
    except ValueError:
        limit = 20

    # Filter by BU
    # choose the model where ServiceMetrics are stored; modify if you used ServiceComponentData
    qs = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at') if user_unit != 'Admin' else XMLData.objects.all().order_by('-created_at')

    # We'll collect up to `limit` samples (most recent first)
    labels = []     # timestamps string
    cpu_points = [] # floats
    ram_points = [] # floats

    # latest disks dict: drive -> value
    latest_disk = {}

    seen = 0
    # iterate rows newest->oldest until we collect `limit` points for the hostname (or collect aggregated)
    for entry in qs:
        if seen >= limit:
            break
        parsed = entry.data or {}
        # pick top tag (ServiceMetrics or similar)
        top = None
        if isinstance(parsed, dict):
            top = list(parsed.keys())[0] if parsed else None
        data_root = parsed.get(top) if (top and top in parsed) else parsed

        # servers may be list or dict
        servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
        if isinstance(servers, dict):
            servers = [servers]

        for s in servers:
            host = (s.get('@Hostname') or s.get('Hostname') or '').strip()
            if hostname:
                hostname = hostname.replace(' ','')
                if host.lower() != hostname.lower():
                    continue

            # extract cpu, ram
            cpu_raw = s.get('CPU') or s.get('cpu') or s.get('@CPU') or s.get('#CPU')
            ram_raw = s.get('RAM') or s.get('ram') or s.get('@RAM') or s.get('#RAM')
            cpu = _to_float(cpu_raw)
            ram = _to_float(ram_raw)
            # skip if both None
            if cpu is None and ram is None:
                continue



            # record timestamp
            ts = entry.created_at + timedelta(hours=5, minutes=30)
            labels.append(ts.strftime("%Y-%m-%d %H:%M:%S"))
            cpu_points.append(cpu if cpu is not None else None)
            ram_points.append(ram if ram is not None else None)

            # disk usage: get disks if available (take latest non-empty)
            disks = s.get('Disks') or s.get('disks') or {}
            # Disks may have 'Disk' key
            disk_nodes = []
            if isinstance(disks, dict):
                # try various shapes
                if 'Disk' in disks:
                    disk_nodes = disks.get('Disk') or []
                else:
                    # maybe directly dict of drives
                    disk_nodes = []
            if isinstance(disk_nodes, dict):
                disk_nodes = [disk_nodes]
            for d in disk_nodes:
                drive = d.get('@Drive') or d.get('Drive') or d.get('name') or ''
                used = d.get('#text') or d.get('@used') or d.get('used') or d.get('value')
                val = _to_float(used)
                if drive and val is not None:
                    # keep most recent (first encountered is latest)
                    if drive not in latest_disk:
                        latest_disk[drive] = val

            seen += 1
            if seen >= limit:
                break

    # reverse arrays so oldest -> newest for chart
    labels = labels[::-1]
    cpu_points = cpu_points[::-1]
    ram_points = ram_points[::-1]


    return JsonResponse({
        'labels': labels,
        'cpu': cpu_points,
        'ram': ram_points,
        'disks': latest_disk,
    })


@login_required
def metrics_dashboard(request):
    user_unit = request.user.business_unit
    if user_unit == 'Admin':
        entries = XMLData.objects.all().order_by('-created_at')
    else:
        entries = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at')

    # get unique hostnames for dropdown
    hostnames = []
    for entry in entries:
        data_root = entry.data.get('ServiceMetrics') or entry.data.get('ServerMetrics') or entry.data
        servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
        if isinstance(servers, dict):
            servers = [servers]
        for s in servers:
            hn = s.get('@Hostname') or s.get('Hostname')
            if hn and hn not in hostnames:
                hostnames.append(hn)
    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)
    return render(request, 'metrics_dashboard.html', {
        'hostnames': hostnames,
        'name': name.upper(),
        'business_unit': user_unit,
    })

@login_required
def metrics_data(request):
    server = request.GET.get('server')
    if not server:
        return JsonResponse({'error': 'No server provided'}, status=400)

    user_unit = request.user.business_unit

    # Filter only relevant XMLData entries
    if user_unit == 'Admin':
        entries = XMLData.objects.all().order_by('-created_at')
    else:
        entries = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at')

    labels, cpu, ram = [], [], []
    disk_labels, disk_values = [], []
    server_info = {'hostname': server, 'ip': None, 'business_unit':user_unit}

    for entry in entries:
        data_root = entry.data.get('ServiceMetrics') or entry.data.get('ServerMetrics') or entry.data
        servers = data_root.get('Server', []) if isinstance(data_root, dict) else []
        if isinstance(servers, dict):
            servers = [servers]

        for s in servers:
            hn = (s.get('@Hostname') or s.get('Hostname') or '').strip()
            if hn.lower() != server.lower():
                continue

            ip_val = s.get('@IP') or s.get('IP') or None
            if ip_val:
                server_info['ip'] = ip_val

            # Get CPU and RAM
            cpu_val = None
            ram_val = None
            for key, value in s.items():
                if 'cpu' in key.lower():
                    cpu_val = float(str(value).replace('%', '').strip() or 0)
                if 'ram' in key.lower():
                    ram_val = float(str(value).replace('%', '').strip() or 0)

            ts = entry.created_at.astimezone(timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M:%S')
            labels.append(ts)
            cpu.append(cpu_val or 0)
            ram.append(ram_val or 0)

            # Disk values
            disks = s.get('Disk', []) if isinstance(s.get('Disk', []), list) else [s.get('Disk', [])]
            for d in disks:
                if not isinstance(d, dict):
                    continue
                d_name = d.get('@Drive') or d.get('Drive')
                d_val = d.get('#text') or d.get('value') or ''
                if d_name and d_val:
                    disk_labels.append(d_name)
                    # Extract numeric value if like '50GB' or '60%'
                    num = ''.join(ch for ch in d_val if (ch.isdigit() or ch == '.'))
                    disk_values.append(float(num or 0))


    return JsonResponse({
        'labels': labels[::-1],  # reverse chronological order
        'cpu': cpu[::-1],
        'ram': ram[::-1],
        'disk_labels': disk_labels,
        'disk_values': disk_values,
        'server_info': server_info,
    })


@login_required
def all_servers_plot(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    selected_metric = request.GET.get('metric', 'ALL')
    user_unit = request.user.business_unit
    selected_bu = request.GET.get('bu')

    if start_date and end_date:
        date_obj1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        date_obj2 = datetime.strptime(end_date, "%Y-%m-%d").date()
        start_datetime = timezone.make_aware(datetime.combine(date_obj1, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(date_obj2, datetime.max.time()))
    else:
        start_datetime = end_datetime = None

    if user_unit == 'Admin' and selected_bu and selected_bu == 'ALL':
        entries = XMLData.objects.all().order_by('-created_at')
    elif user_unit == 'Admin' and selected_bu and selected_bu != 'ALL':
        entries = XMLData.objects.filter(business_unit=selected_bu).order_by('-created_at')
    else:
        entries = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at')
    if start_datetime and end_datetime:
        entries = entries.filter(created_at__range=[start_datetime, end_datetime])


    # Collect metrics
    server_names = []
    cpu_vals = []
    ram_vals = []
    disk_data = {}  # e.g. {'C': [50, 70, 60], 'D': [100, 80, 120]}

    for entry in entries:
        data_root = entry.data.get('ServiceMetrics') or entry.data.get('ServerMetrics') or entry.data
        servers = data_root.get('Server', [])
        if isinstance(servers, dict):
            servers = [servers]

        for s in servers:
            name = s.get('@Hostname') or s.get('Hostname')
            if not name:
                continue

            cpu = None
            ram = None

            for k, v in s.items():
                if 'cpu' in k.lower():
                    cpu = float(str(v).replace('%', '').strip() or 0)
                if 'ram' in k.lower():
                    ram = float(str(v).replace('%', '').strip() or 0)

            # Disk handling
            disks = s.get('Disks', {}).get('Disk', [])
            if isinstance(disks, dict):
                disks = [disks]

            for d in disks:
                if not isinstance(d, dict):
                    continue
                drive = d.get('@Drive') or d.get('Drive') or 'Unknown'
                val = d.get('#text') or d.get('value') or ''
                num = ''.join(ch for ch in str(val) if ch.isdigit() or ch == '.')
                num = float(num or 0)
                if drive not in disk_data:
                    disk_data[drive] = []
                disk_data[drive].append(num)

            if cpu is not None and ram is not None:
                server_names.append(name)
                cpu_vals.append(cpu)
                ram_vals.append(ram)

    # --- Plotting ---
    fig, ax = plt.subplots(figsize=(10, 6))
    width = 0.15
    x = range(len(server_names))

    def autolabel(rects):
        """Attach a text label above each bar in *rects*, displaying its height."""
        for rect in rects:
            height = rect.get_height()
            ax.annotate('{}'.format(height),
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, -2),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom')

    if selected_metric == 'ALL' or selected_metric == '':
        rects1 = ax.bar([i - width for i in x], cpu_vals, width, label='CPU (%)', color='skyblue')
        rects2 = ax.bar(x, ram_vals, width, label='RAM (%)', color='salmon')

        # plot each drive dynamically
        color_cycle = ['mediumseagreen', 'orange', 'mediumpurple', 'gold', 'lightcoral']
        for idx, (drive, values) in enumerate(disk_data.items()):
            offset = width * (idx + 1)
            color = color_cycle[idx % len(color_cycle)]
            rects3 = ax.bar([i + offset for i in x], values, width, label=f'Disk {drive} (GB)', color=color)
            autolabel(rects3)

        autolabel(rects1)
        autolabel(rects2)

    elif selected_metric == 'CPU':
        cpu_rects = ax.bar(x, cpu_vals, width, label='CPU (%)', color='skyblue')
        autolabel(cpu_rects)

    elif selected_metric == 'RAM':
        ram_rects = ax.bar(x, ram_vals, width, label='RAM (%)', color='salmon')
        autolabel(ram_rects)

    else:
        color_cycle = ['mediumseagreen', 'orange', 'mediumpurple', 'gold', 'lightcoral']
        for idx, (drive, values) in enumerate(disk_data.items()):
            offset = width * (idx + 1)
            color = color_cycle[idx % len(color_cycle)]
            disk_rects = ax.bar([i + offset for i in x], values, width, label=f'Disk {drive} (GB)', color=color)
            autolabel(disk_rects)

    ax.set_xticks(list(x))
    ax.set_xticklabels(server_names, rotation=45, ha='center')
    ax.set_ylabel('Usage')

    bar_print_label = ''
    if selected_metric == 'ALL' or selected_metric == '':
        bar_print_label = 'CPU, RAM, and Disk Usage (C, D, etc.)'
    else:
        bar_print_label = selected_metric

    ax.set_title(f'{bar_print_label} Usage Across Servers ({start_date} to {end_date})')
    ax.legend(
        loc = 'upper center',
        bbox_to_anchor = (0.5,1.2),
        ncol = 4,
        fontsize = 10,
        frameon = False,
        handlelength = 2.5,
        handletextpad = 0.8
    )

    ax.set_ylim(0,100)
    ax.set_yticks([0,20,40,60,80,100])

    plt.tight_layout()

    # Convert to base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)

    last_updated = timezone.now().astimezone(timezone.get_current_timezone()) + timedelta(hours=5, minutes=30)

    email = request.user.email
    pattern = "@[\w\.-]*"
    name = re.sub(pattern, ' ', email)

    selectionTab = ['ALL','CPU', 'RAM', 'Disks']
    # for disk in disk_data.keys():
    #     selectionTab.append(disk.replace(' ',''))
    if start_date and end_date and start_date > end_date:
        return render(request, 'all_servers_plot.html', {
            'message': 'End Date must be after Start Date !!',
            'start_date': start_date,
            'end_date': end_date,
            'name': name.upper(),
            'business_unit': user_unit,
            'selectionTab': selectionTab,
        })

    elif start_date == '':
        return render(request, 'all_servers_plot.html', {
            'message': 'Please Select a Start Date !!',
            'start_date': start_date,
            'end_date': end_date,
            'name': name.upper(),
            'business_unit': user_unit,
            'selectionTab': selectionTab,
        })
    elif len(entries)!=0:
        return render(request, 'all_servers_plot.html', {
            'plot_image': img_b64,
            'last_updated': last_updated,
            'start_date':start_date,
            'end_date':end_date,
            'name': name.upper(),
            'business_unit': user_unit,
            'selectionTab':selectionTab,
            'selectedBU': selected_bu,
        })
    else:
        return render(request, 'all_servers_plot.html', {
            'message': f'No data found between {start_date} and {end_date}',
            'start_date': start_date,
            'end_date': end_date,
            'name': name.upper(),
            'business_unit': user_unit,
            'selectionTab': selectionTab,
        })


CPU_THRESHOLD = 80
RAM_THRESHOLD = 80
DISK_THRESHOLD = 80
Ticket_ID = 1000

@login_required
def check_threshold_view(request, server_name):
    global Ticket_ID
    user_unit = request.user.business_unit
    threshold_exceeded = []

    # Get the latest entry for this BU
    entries = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at')

    if not entries.exists():
        messages.error(request, "No data available for this Business Unit.")
        return redirect('dashboard_view')


    selected_server = None
    for entry in entries:
        data_root = entry.data.get('ServiceMetrics') or entry.data.get('ServerMetrics') or entry.data
        servers = data_root.get('Server', [])
        if isinstance(servers, dict):
            servers = [servers]

        for server in servers:
            name = server.get('@Hostname') or server.get('Hostname')
            if name and name.lower() == server_name.lower():
                selected_server = server
                break

    if not selected_server:
        messages.error(request, f"No data found for {server_name}")
        return redirect('dashboard_view')

    # Extract metrics
    cpu_val = None
    ram_val = None
    disk_vals = []

    for k, v in selected_server.items():
        if 'cpu' in k.lower():
            cpu_val = float(str(v).replace('%', '').strip() or 0)
        elif 'ram' in k.lower():
            ram_val = float(str(v).replace('%', '').strip() or 0)

    disks = selected_server.get('Disks', {}).get('Disk', [])
    if isinstance(disks, dict):
        disks = [disks]

    for d in disks:
        drive = d.get('@Drive') or d.get('Drive') or 'Unknown'
        val = d.get('#text') or d.get('value') or ''
        num = ''.join(ch for ch in str(val) if ch.isdigit() or ch == '.')
        num = float(num or 0)
        disk_vals.append((drive, num))

    # Compare with thresholds
    if cpu_val and cpu_val > CPU_THRESHOLD:
        threshold_exceeded.append(f"CPU usage {cpu_val}% exceeded the threshold of {CPU_THRESHOLD}%")
    if ram_val and ram_val > RAM_THRESHOLD:
        threshold_exceeded.append(f"RAM usage {ram_val}% exceeded the threshold of {RAM_THRESHOLD}%")

    for drive, val in disk_vals:
        if val > DISK_THRESHOLD:
            threshold_exceeded.append(f"Disk {drive} usage {val}% exceeded the threshold of {DISK_THRESHOLD}%")
    print(request.user)
    # Prepare the ticket file content
    ticket_text = []
    if threshold_exceeded:
        ticket_text.append(f"Ticket ID - {Ticket_ID}\n")
        ticket_text.append(f"Affected User - {request.user}\n")
        ticket_text.append(f"Location - India\n")
        ticket_text.append("Category - Hardware\n")
        ticket_text.append(f"Subcategory - Performance\n")
        ticket_text.append(f"Short Description - Threshold Alert for Server: {server_name}\n")
        ticket_text.append("Description - Issues Detected:\n")
        for t in threshold_exceeded:
            ticket_text.append(f"- {t}\n")
        ticket_text.append("Impact - 3 ( Low )\n")
        ticket_text.append("Urgency - 3 ( Low )\n")
        ticket_text.append(f"Assignment Group - L3_{user_unit}TeamcenterPLM_SysAdmin\n")
        ticket_text.append("\nAction: Immediate attention required.\n")
    else:
        ticket_text.append(f"No threshold limit reached for Server: {server_name}\nAll parameters are normal.\n")

    # Save to .txt file
    save_dir = os.path.join(settings.BASE_DIR, 'tickets')
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{Ticket_ID}_{server_name}_ticket.txt")



    if threshold_exceeded:
        messages.warning(request, f"⚠️ Threshold exceeded! Ticket with ID: {Ticket_ID} created successfully at: \n{file_path}")
        Ticket_ID += 1
        with open(file_path, "w") as f:
            f.writelines(ticket_text)

    else:
        messages.success(request, f"✅ No threshold limit reached for {server_name}. Hence no ticket created !!")

    return redirect('dashboard_view')

# @login_required
# def check_threshold_view(request, server_name):
#     user_unit = request.user.business_unit
#     threshold_exceeded = []
#
#     entry = XMLData.objects.filter(business_unit=user_unit).order_by('-created_at').first()
#     if not entry:
#         return JsonResponse({"status": "error", "message": "No data available for this Business Unit."})
#
#     data_root = entry.data.get('ServiceMetrics') or entry.data.get('ServerMetrics') or entry.data
#     servers = data_root.get('Server', [])
#     if isinstance(servers, dict):
#         servers = [servers]
#
#     selected_server = next((s for s in servers if (s.get('@Hostname') or s.get('Hostname')).lower().replace(' ','') == server_name.lower().replace(' ','')), None)
#     print(selected_server)
#     print(server_name)
#     if not selected_server:
#         return JsonResponse({"status": "error", "message": f"No data found for {server_name}"})
#
#     # Extract metrics
#     cpu_val = ram_val = None
#     disk_vals = []
#     for k, v in selected_server.items():
#         if 'cpu' in k.lower():
#             cpu_val = float(str(v).replace('%', '').strip() or 0)
#         elif 'ram' in k.lower():
#             ram_val = float(str(v).replace('%', '').strip() or 0)
#
#     disks = selected_server.get('Disks', {}).get('Disk', [])
#     if isinstance(disks, dict):
#         disks = [disks]
#
#     for d in disks:
#         drive = d.get('@Drive') or d.get('Drive') or 'Unknown'
#         val = d.get('#text') or d.get('value') or ''
#         num = ''.join(ch for ch in str(val) if ch.isdigit() or ch == '.')
#         disk_vals.append((drive, float(num or 0)))
#
#     # Compare
#     CPU_THRESHOLD, RAM_THRESHOLD, DISK_THRESHOLD = 80, 80, 90
#
#     if cpu_val and cpu_val > CPU_THRESHOLD:
#         threshold_exceeded.append(f"CPU usage {cpu_val}% exceeded threshold ({CPU_THRESHOLD}%)")
#     if ram_val and ram_val > RAM_THRESHOLD:
#         threshold_exceeded.append(f"RAM usage {ram_val}% exceeded threshold ({RAM_THRESHOLD}%)")
#     for drive, val in disk_vals:
#         if val > DISK_THRESHOLD:
#             threshold_exceeded.append(f"Disk {drive} usage {val}% exceeded threshold ({DISK_THRESHOLD}%)")
#
#     # Create ticket file
#     save_dir = os.path.join(settings.BASE_DIR, 'tickets')
#     os.makedirs(save_dir, exist_ok=True)
#     file_path = os.path.join(save_dir, f"{server_name}_ticket.txt")
#
#     if threshold_exceeded:
#         with open(file_path, "w") as f:
#             f.write(f"Threshold Alert for {server_name}\n\n")
#             for line in threshold_exceeded:
#                 f.write(f"- {line}\n")
#         return JsonResponse({
#             "status": "exceeded",
#             "message": "\n".join(threshold_exceeded),
#             "file": file_path
#         })
#     else:
#         with open(file_path, "w") as f:
#             f.write(f"All parameters normal for {server_name}.\n")
#         return JsonResponse({
#             "status": "normal",
#             "message": f"No threshold limit reached for {server_name}."
#         })
