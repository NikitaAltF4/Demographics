# accounts/urls.py
from django.urls import path
from . import views

app_name = 'accounts'  # Пространство имен для этого приложения

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),

]