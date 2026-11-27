
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
        'custodian-queue/',
        views.custodian_queue,
        name='custodian_queue'
    ),

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

    path(
        '<int:item_id>/confirm-custody/',
        views.confirm_item_custody,
        name='confirm_item_custody'
    ),

    path(
        'admin/',
        views.admin_dashboard,
        name='admin_dashboard'
    ),

    path(
        '<int:item_id>/matches/<int:match_id>/dismiss/',
        views.dismiss_match,
        name='dismiss_match'
    ),

    path(
        'claims/<int:claim_id>/handover/',
        views.record_handover,
        name='record_handover'
    ),

    path(
        'claims/<int:claim_id>/regenerate-code/',
        views.regenerate_claim_pickup_code,
        name='regenerate_claim_pickup_code'
    ),

    path(
        'claims/',
        views.claims,
        name='claims'
    ),

    path(
        'handovers/<int:handover_id>/receipt/',
        views.handover_receipt,
        name='handover_receipt'
    ),

    path('<int:item_id>/', views.item_detail, name='item_detail'),

]
