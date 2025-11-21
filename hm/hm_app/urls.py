from django.urls import path
from .views import register_view, login_view, logout_view, download_ticket_email, application_dashboard_view
from .views import portal_home, upload_view, dashboard_view
from django.contrib.auth.decorators import login_required
from .views import server_services_view, service_details_view, application_detail_view, application_dashboard_view, metrics_page_view, metrics_data_api, all_servers_plot, metrics_dashboard, metrics_data, check_threshold_view

urlpatterns = [
    path('', portal_home, name='home'),          # tile entry page
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('app/upload/', login_required(upload_view), name='upload_view'),
    path('app/dashboard/', login_required(dashboard_view), name='dashboard_view'),
    path('app/server/<path:hostname>/<path:service_name>/', service_details_view, name='service_details'),
    path('app/server/<path:hostname>/', server_services_view, name='server_services'),
    path('app/applications/', login_required(application_dashboard_view), name='application_dashboard'),
    path('app/application/<path:app_name>/', login_required(application_detail_view), name='application_detail'),
    path('app/metrics/', login_required(metrics_page_view), name='metrics_page'),
    path('app/api/metrics_data_api/', login_required(metrics_data_api), name='metrics_data_api'),
    path('app/metrics/data/',login_required(metrics_data), name='metrics_data'),
    path('app/metrics_dashboard',login_required(metrics_dashboard), name='metrics_dashboard'),
    path('app/server_visualization/',login_required(all_servers_plot), name='all_servers_plot'),
    path('app/check_threshold/<path:server_name>/',login_required(check_threshold_view), name='check_threshold'),
    path('ticket/email/<str:hostname>/', download_ticket_email, name="download_ticket_email"),
]
