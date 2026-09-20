from django.urls import path

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.overview, name='overview'),
    path('graphs/', views.graphs, name='graphs'),
    path('incidents/', views.incidents_list, name='incidents_list'),
    path('incidents/<int:incident_id>/', views.incident_detail, name='incident_detail'),
    path('sla-comparison/', views.sla_comparison, name='sla_comparison'),
    path('baseline-comparison/', views.baseline_comparison, name='baseline_comparison'),
    path('historical-comparison/', views.historical_comparison, name='historical_comparison'),
    path('api/overview/', views.api_overview, name='api_overview'),
    path('api/timeseries/', views.api_timeseries, name='api_timeseries'),
]
