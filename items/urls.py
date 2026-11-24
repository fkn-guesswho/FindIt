
from django.urls import path
from . import views

urlpatterns = [

    path(
        'image/<int:item_id>/',
        views.view_item_image,
        name='view_item_image'
    ),

    path(
        'additional-image/<int:image_id>/',
         views.view_additional_item_image,
         name='view_additional_item_image'
    ),
    path('report/', views.create_item_report, name='create_item_report'),
    path('my-reports/', views.my_item_reports, name='my_item_reports'),

    path(
        'claim-evidence/<int:evidence_id>/',
        views.view_claim_evidence,
        name='view_claim_evidence'
    ),

    path('', views.browse_items, name='browse_items'),

    path(
        '<int:item_id>/claim/',
        views.submit_claim,
        name='submit_claim'
    ),

    path(
        '<int:item_id>/request-closure/',
        views.request_item_closure,
        name='request_item_closure'
    ),

    path('<int:item_id>/', views.item_detail, name='item_detail'),

]
