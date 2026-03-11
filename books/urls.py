from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista, name='lista'),
    path('per-page/', views.lista_per_page, name='lista_per_page'),
    path('own-paper/', views.lista_own_paper, name='lista_own_paper'),
    path('plan/', views.plan, name='plan'),
]
