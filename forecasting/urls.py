# forecasting/urls.py
from django.urls import path
from .views import ForecastView # Импортируем наше классовое представление
from . import views
app_name = 'forecasting' # Пространство имен для URL-ов этого приложения

urlpatterns = [
    path('run-forecast/', ForecastView.as_view(), name='run_forecast'),
    # - API для скачивания результатов в CSV/JSON
    path('history/', views.forecast_history_view, name='forecast_history'),
    # path('download-forecast/<int:forecast_id>/csv/', DownloadCsvView.as_view(), name='download_csv'),
  path('progress/', views.ForecastProgressView.as_view(), name='forecast_progress_api'),

    path('history/<uuid:forecast_run_id>/view/', views.view_historical_forecast, name='view_historical_forecast'),

    path('export/<uuid:forecast_run_id>/<str:export_format>/',
         views.export_forecast_data_view,
         name='export_forecast_data'),


]
