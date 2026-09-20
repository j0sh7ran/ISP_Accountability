from django.urls import path

from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.reports_list, name='list'),
    path('<int:report_id>/download/', views.download_report, name='download'),
    path('export/measurements/<str:data_type>/', views.export_measurements_view, name='export_measurements'),
    path('export/incidents/', views.export_incidents_view, name='export_incidents'),
]
