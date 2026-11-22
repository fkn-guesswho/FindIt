from django.urls import path
from . import views

urlpatterns = [
    path('report/', views.create_item_report, name='create_item_report'),
    path('my-reports/', views.my_item_reports, name='my_item_reports'),
    path('', views.browse_items, name='browse_items'),
    path('<int:item_id>/', views.item_detail, name='item_detail'),
]
