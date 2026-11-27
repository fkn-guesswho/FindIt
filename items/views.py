
import mimetypes

from django.contrib import messages

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.db import IntegrityError
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_POST

from .forms import (
    ItemReportForm,
    ClaimForm,
    ClosureRequestForm,
    CustodyConfirmationForm,
    HandoverForm,
)

from .models import (
    Item,
    ItemMatch,
    Claim,
    Handover,
    ClaimEvidence,
    ItemImage,
    ClosureRequest,
    CustodyRecord,
    MatchingConfiguration,
)

from .matching import find_matching_items, DEFAULT_MATCH_THRESHOLD
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .services import complete_handover, regenerate_pickup_code

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        raise Http404

    User = get_user_model()

    context = {
        'total_users': User.objects.count(),
        'total_lost_reports': Item.objects.filter(
            report_type=Item.ReportType.LOST
        ).count(),
        'total_found_reports': Item.objects.filter(
            report_type=Item.ReportType.FOUND
        ).count(),
        'pending_claims': Claim.objects.filter(
            status=Claim.Status.PENDING
        ).count(),
    }

    return render(request, 'items/admin_dashboard.html', context)

@login_required
def create_item_report(request):
    if request.method == 'POST':
        form = ItemReportForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_images = form.cleaned_data['images']

            item = form.save(commit=False)
            item.reported_by = request.user

            if uploaded_images:
                item.image = uploaded_images[0]

            item.save()

            if item.report_type == Item.ReportType.LOST:
                eligible_matches = Item.objects.filter(
                    report_type=Item.ReportType.FOUND,
                    status=Item.Status.OPEN,
                    visibility=Item.Visibility.PUBLIC,
                    contains_sensitive_info=False,
                    custody_record__isnull=False,
                )

            else:
                eligible_matches = Item.objects.filter(
                    report_type=Item.ReportType.LOST,
                    status=Item.Status.OPEN,
                    visibility=Item.Visibility.PUBLIC,
                    contains_sensitive_info=False,
                )

            find_matching_items(
                item,
                candidate_queryset=eligible_matches
            )

            for uploaded_image in uploaded_images[1:]:
                ItemImage.objects.create(
                    item=item,
                    image=uploaded_image
                )

            return redirect('my_item_reports')

    else:
        form = ItemReportForm()

    return render(request, 'items/item_form.html', {
        'form': form
    })


@login_required
def my_item_reports(request):
    items = Item.objects.filter(
        reported_by=request.user
    ).prefetch_related('closure_requests')

    for item in items:
        item.has_pending_closure_request = item.closure_requests.filter(
            status=ClosureRequest.Status.PENDING
        ).exists()

    return render(
        request,
        'items/my_reports.html',
        {
            'items': items,
        }
    )


@login_required
def custodian_queue(request):
    if not (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    ):
        raise Http404

    pending_custody_items = Item.objects.filter(
        report_type=Item.ReportType.FOUND,
        status=Item.Status.OPEN,
        custody_record__isnull=True
    ).select_related('reported_by').order_by('-created_at')

    return render(
        request,
        'items/custodian_queue.html',
        {
            'pending_custody_items': pending_custody_items,
        }
    )

@login_required
def request_item_closure(request, item_id):
    item = get_object_or_404(
        Item,
        id=item_id,
        reported_by=request.user
    )

    if item.status != Item.Status.OPEN:
        messages.error(request, 'Only open reports can be submitted for closure.')
        return redirect('my_item_reports')

    pending_request = ClosureRequest.objects.filter(
        item=item,
        status=ClosureRequest.Status.PENDING
    ).exists()

    if pending_request:
        messages.warning(request, 'This report already has a pending closure request.')
        return redirect('my_item_reports')

    if request.method == 'POST':
        form = ClosureRequestForm(request.POST)

        if form.is_valid():
            closure_request = form.save(commit=False)
            closure_request.item = item
            closure_request.requested_by = request.user
            closure_request.save()

            messages.success(request, 'Your closure request has been submitted for review.')
            return redirect('my_item_reports')

    else:
        form = ClosureRequestForm()

    return render(
        request,
        'items/closure_request_form.html',
        {
            'form': form,
            'item': item
        }
    )

@login_required
def claims(request):
    is_custodian = (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    )

    context = {
        'is_custodian': is_custodian,
        'is_superuser': request.user.is_superuser,
    }

    # Regular users see only claims they submitted.
    # Superusers also get this section.
    if not is_custodian or request.user.is_superuser:
        context['user_claims'] = (
            Claim.objects
            .filter(claimant=request.user)
            .select_related('item', 'handover')
        )

    # Custodians and superusers see approved claims
    # that have not yet been handed over.
    if is_custodian:
        context['pending_handovers'] = (
            Claim.objects
            .filter(
                status=Claim.Status.APPROVED,
                handover__isnull=True,
            )
            .select_related('item', 'claimant')
        )

    return render(request, 'items/claims.html', context)

@login_required
def confirm_item_custody(request, item_id):
    if not (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    ):
        raise Http404

    item = get_object_or_404(
        Item,
        id=item_id,
        report_type=Item.ReportType.FOUND,
        status=Item.Status.OPEN,
    )

    if hasattr(item, 'custody_record'):
        messages.info(
            request,
            "Custody has already been confirmed for this item."
        )
        return redirect('item_detail', item_id=item.id)

    if request.method == 'POST':
        form = CustodyConfirmationForm(request.POST)

        if form.is_valid():
            custody_record = form.save(commit=False)
            custody_record.item = item
            custody_record.received_by = request.user

            try:
                custody_record.save()
            except IntegrityError:
                messages.info(
                    request,
                    "Custody has already been confirmed for this item."
                )
            else:
                eligible_matches = Item.objects.filter(
                    report_type=Item.ReportType.LOST,
                    status=Item.Status.OPEN,
                    visibility=Item.Visibility.PUBLIC,
                    contains_sensitive_info=False,
                )

                find_matching_items(
                    item,
                    candidate_queryset=eligible_matches
                )

                messages.success(
                    request,
                    "Item custody has been confirmed successfully."
                )

            return redirect('item_detail', item_id=item.id)

    else:
        form = CustodyConfirmationForm()

    return render(
        request,
        'items/custody_confirmation_form.html',
        {
            'form': form,
            'item': item,
        }
    )


@login_required
def handover_receipt(request, handover_id):
    # Only administrators and designated custodians can access receipts.
    if not (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    ):
        raise Http404

    handover = get_object_or_404(
        Handover.objects.select_related(
            'claim__item',
            'claim__claimant',
            'recorded_by',
        ),
        pk=handover_id,
    )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ReceiptTitle',
        parent=styles['Title'],
        fontSize=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#1f3a5f'),
        spaceAfter=8,
    )

    subtitle_style = ParagraphStyle(
        'ReceiptSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.grey,
        spaceAfter=20,
    )

    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#1f3a5f'),
        spaceBefore=12,
        spaceAfter=8,
    )

    normal_style = styles['BodyText']

    story = []

    # Receipt heading.
    story.append(Paragraph('FINDIT', title_style))
    story.append(
        Paragraph('ITEM HANDOVER RECEIPT', subtitle_style)
    )

    story.append(
        Paragraph(
            'This document confirms that the item described below '
            'was physically handed over to the claimant.',
            normal_style,
        )
    )

    story.append(Spacer(1, 12))

    # Item and claimant information.
    story.append(
        Paragraph('ITEM AND CLAIMANT DETAILS', heading_style)
    )

    item = handover.claim.item
    claimant = handover.claim.claimant

    details = [
        ['Item Reference:', item.reference_number],
        ['Item Description:', item.title],
        ['Claim Number:', str(handover.claim_id)],
        ['Claimant:', claimant.get_full_name() or claimant.username],
        ['Claimant Username:', claimant.username],
        [
            'Handover Date:',
            handover.handed_over_at.strftime('%d %B %Y'),
        ],
        [
            'Handover Time:',
            handover.handed_over_at.strftime('%H:%M'),
        ],
        ['Custodian:', handover.recorded_by.get_full_name()
         or handover.recorded_by.username],
    ]

    details_table = Table(
        details,
        colWidths=[45 * mm, 115 * mm],
    )

    details_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f3f7')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1f3a5f')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    story.append(details_table)

    # Identity verification.
    story.append(
        Paragraph('IDENTITY VERIFICATION', heading_style)
    )

    verification_method = (
        handover.get_verification_method_display()
        if handover.verification_method
        else 'Not specified'
    )

    verification_details = [
        ['Identity Verified:', 'Yes' if handover.identity_verified else 'No'],
        ['Verification Method:', verification_method],
        [
            'Collector Admission/Staff Number:',
            handover.collector_identifier or 'Not provided',
        ],
    ]

    verification_table = Table(
        verification_details,
        colWidths=[60 * mm, 100 * mm],
    )

    verification_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    story.append(verification_table)

    # Additional notes.
    if handover.notes:
        story.append(
            Paragraph('ADDITIONAL NOTES', heading_style)
        )
        story.append(
            Paragraph(handover.notes, normal_style)
        )

    # Physical signatures.
    story.append(
        Paragraph('ACKNOWLEDGEMENT AND SIGNATURES', heading_style)
    )

    story.append(
        Paragraph(
            'By signing below, both parties acknowledge that the item '
            'described in this receipt has been handed over.',
            normal_style,
        )
    )

    story.append(Spacer(1, 30))

    signature_data = [
        ['____________________________', '____________________________'],
        ['Claimant Signature', 'Custodian Signature'],
        ['Name: ______________________', 'Name: ______________________'],
        ['Date: _______________________', 'Date: _______________________'],
    ]

    signature_table = Table(
        signature_data,
        colWidths=[80 * mm, 80 * mm],
    )

    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    story.append(signature_table)

    story.append(Spacer(1, 25))

    story.append(
        Paragraph(
            'This is a system-generated handover record. '
            'Physical signatures should be completed by both parties.',
            styles['Italic'],
        )
    )

    document.build(story)

    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(
        pdf,
        content_type='application/pdf',
    )

    response['Content-Disposition'] = (
        f'inline; filename="handover_receipt_{handover.id}.pdf"'
    )

    return response


@login_required
def record_handover(request, claim_id):
    if not (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    ):
        raise Http404

    claim = get_object_or_404(
        Claim.objects.select_related('item', 'claimant'),
        pk=claim_id,
        status=Claim.Status.APPROVED,
    )

    if request.method == 'POST':
        form = HandoverForm(request.POST)

        if form.is_valid():
            try:
                handover = complete_handover(
                    claim_id=claim.id,
                    submitted_code=form.cleaned_data['submitted_code'],
                    actor=request.user,
                    identity_verified=form.cleaned_data['identity_verified'],
                    verification_method=form.cleaned_data['verification_method'],
                    collector_identifier=form.cleaned_data['collector_identifier'],
                    notes=form.cleaned_data['notes'],
                )

            except ValidationError as error:
                messages.error(request, ' '.join(error.messages))

            else:
                messages.success(
                    request,
                    'Handover completed successfully.'
                )
                return redirect(
                    'handover_receipt',
                    handover_id=handover.id
                )

    else:
        form = HandoverForm()

    return render(
        request,
        'items/handover_form.html',
        {
            'form': form,
            'claim': claim,
            'item': claim.item,
        }
    )


@login_required
@require_POST
def regenerate_claim_pickup_code(request, claim_id):
    if not (
        request.user.is_superuser
        or request.user.has_perm('items.can_confirm_custody')
    ):
        raise Http404

    try:
        regenerate_pickup_code(
            claim_id=claim_id,
            actor=request.user
        )
    except Claim.DoesNotExist:
        raise Http404
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(
            request,
            'A new pickup code has been generated and emailed to the claimant.'
        )

    return redirect('claims')


def browse_items(request):

    items = Item.objects.filter(
        status=Item.Status.OPEN,
        visibility=Item.Visibility.PUBLIC,
    ).filter(
        Q(report_type=Item.ReportType.LOST) |
        Q(
            report_type=Item.ReportType.FOUND,
            custody_record__isnull=False
        )
    )


    search_query = request.GET.get('q', '').strip()
    report_type = request.GET.get('type', '')
    category = request.GET.get('category', '')

    if search_query:
        items = items.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    if report_type in Item.ReportType.values:
        items = items.filter(report_type=report_type)

    if category in Item.Category.values:
        items = items.filter(category=category)

    context = {
        'items': items,
        'search_query': search_query,
        'selected_type': report_type,
        'selected_category': category,
        'categories': Item.Category.choices,
    }

    return render(request, 'items/browse_items.html', context)

@login_required
@require_POST
def dismiss_match(request, item_id, match_id):
    lost_item = get_object_or_404(
        Item,
        id=item_id,
        report_type=Item.ReportType.LOST,
        reported_by=request.user,
    )

    match = get_object_or_404(
        ItemMatch,
        id=match_id,
        lost_item=lost_item,
    )

    match.is_dismissed = True
    match.save(update_fields=['is_dismissed'])

    messages.success(request, 'Match suggestion dismissed.')

    return redirect('item_detail', item_id=lost_item.id)

def item_detail(request, item_id):
    item = get_object_or_404(
        Item,
        id=item_id,
        status=Item.Status.OPEN
    )

    is_owner = (
        request.user.is_authenticated
        and request.user == item.reported_by
    )

    is_admin = (
        request.user.is_authenticated
        and request.user.is_staff
    )


    is_owner_or_admin = is_owner or is_admin

    can_manage_custody = (
        request.user.is_authenticated
        and (
             request.user.is_staff
             or request.user.is_superuser
             or request.user.has_perm('items.can_confirm_custody')
        )
    )

    if (
        item.report_type == Item.ReportType.FOUND
        and not hasattr(item, 'custody_record')
        and not (is_owner or can_manage_custody)
    ):
        raise Http404

    if item.visibility == Item.Visibility.PRIVATE:
        if not is_owner_or_admin:
            raise Http404

    # Check whether the current user already has an active claim.
    existing_claim = None

    if (
        request.user.is_authenticated
        and item.report_type == Item.ReportType.FOUND
    ):
        existing_claim = Claim.objects.filter(
            item=item,
            claimant=request.user,
            status__in=[
                Claim.Status.PENDING,
                Claim.Status.APPROVED
            ]
        ).order_by('-id').first()

    can_claim = (
        request.user.is_authenticated
        and item.report_type == Item.ReportType.FOUND
        and item.visibility == Item.Visibility.PUBLIC
        and hasattr(item, 'custody_record')
        and request.user != item.reported_by
        and existing_claim is None
    )

    matching_items = []

    if request.user.is_authenticated:
        matching_configuration = MatchingConfiguration.objects.filter(
            pk=1
        ).first()

        matching_threshold = (
            matching_configuration.threshold
            if matching_configuration
            else DEFAULT_MATCH_THRESHOLD
        )

        if (
            item.report_type == Item.ReportType.LOST
            and is_owner
        ):
            stored_matches = ItemMatch.objects.filter(
                lost_item=item,
                is_dismissed=False,
                similarity_score__gt=matching_threshold,
                found_item__status=Item.Status.OPEN,
                found_item__visibility=Item.Visibility.PUBLIC,
                found_item__contains_sensitive_info=False,
                found_item__custody_record__isnull=False,
            ).select_related('found_item').order_by('-similarity_score')[:3]

            for match in stored_matches:
                match.suggested_item = match.found_item
                matching_items.append(match)

        elif (
            item.report_type == Item.ReportType.FOUND
            and can_manage_custody
            and hasattr(item, 'custody_record')
        ):
            stored_matches = ItemMatch.objects.filter(
                found_item=item,
                lost_item__status=Item.Status.OPEN,
                similarity_score__gt=matching_threshold,
            ).select_related('lost_item')

            if not request.user.is_staff:
                stored_matches = stored_matches.filter(
                    lost_item__visibility=Item.Visibility.PUBLIC
                )

            for match in stored_matches:
                match.suggested_item = match.lost_item
                matching_items.append(match)

    return render(request, 'items/item_detail.html', {
        'item': item,
        'can_claim': can_claim,
        'existing_claim': existing_claim,
        'is_owner_or_admin': is_owner_or_admin,
        'is_owner': is_owner,
        'matching_items': matching_items,
    })


@login_required
def submit_claim(request, item_id):
    item = get_object_or_404(
        Item,
        id=item_id,
        report_type=Item.ReportType.FOUND,
        status=Item.Status.OPEN,
        visibility=Item.Visibility.PUBLIC
    )

    if not hasattr(item, 'custody_record'):
        messages.error(
            request,
            "This item cannot be claimed until its custody has been confirmed."
        )
        return redirect('browse_items')

    if item.reported_by == request.user:
        messages.error(request, "You cannot claim an item that you reported.")
        return redirect('item_detail', item_id=item.id)

    existing_claim = Claim.objects.filter(
        item=item,
        claimant=request.user,
        status__in=[
            Claim.Status.PENDING,
            Claim.Status.APPROVED
        ]
    ).order_by('-id').first()

    if existing_claim:
        if existing_claim.status == Claim.Status.PENDING:
            messages.warning(
                request,
                "You have already submitted a claim for this item. "
                "It is awaiting admin review."
            )
        else:
            messages.info(
                request,
                "Your claim for this item has already been approved."
            )

        return redirect('item_detail', item_id=item.id)

    if request.method == 'POST':
        form = ClaimForm(request.POST, request.FILES)

        if form.is_valid():
            evidence_images = form.cleaned_data['evidence_images']

            claim = form.save(commit=False)
            claim.item = item
            claim.claimant = request.user
            claim.save()

            for uploaded_image in evidence_images:
                ClaimEvidence.objects.create(
                    claim=claim,
                    image=uploaded_image
                )

            messages.success(
                request,
                "Your claim has been submitted successfully and is awaiting admin review."
            )

            return redirect('item_detail', item_id=item.id)

    else:
        form = ClaimForm()

    return render(request, 'items/claim_form.html', {
        'form': form,
        'item': item,
    })


@staff_member_required
def view_claim_evidence(request, evidence_id):
    evidence = get_object_or_404(
        ClaimEvidence,
        pk=evidence_id
    )

    try:
        image_file = evidence.image.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404("Evidence image not found.")

    content_type, _ = mimetypes.guess_type(evidence.image.name)

    return FileResponse(
        image_file,
        content_type=content_type or 'application/octet-stream'
    )


def can_view_item_images(request, item):
    is_owner = (
        request.user.is_authenticated
        and request.user == item.reported_by
    )

    is_admin = (
        request.user.is_authenticated
        and request.user.is_staff
    )

    if is_owner or is_admin:
        return True

    return (
        item.visibility == Item.Visibility.PUBLIC
        and not item.contains_sensitive_info
        and item.status == Item.Status.OPEN
    )


def view_item_image(request, item_id):
    item = get_object_or_404(Item, pk=item_id)

    if not can_view_item_images(request, item):
        raise Http404

    if not item.image:
        raise Http404("Image not found.")

    try:
        image_file = item.image.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404("Image file not found.")

    content_type, _ = mimetypes.guess_type(item.image.name)

    return FileResponse(
        image_file,
        content_type=content_type or 'application/octet-stream'
    )


def view_additional_item_image(request, image_id):
    extra_image = get_object_or_404(ItemImage, pk=image_id)
    item = extra_image.item

    if not can_view_item_images(request, item):
        raise Http404

    try:
        image_file = extra_image.image.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404("Image file not found.")

    content_type, _ = mimetypes.guess_type(
        extra_image.image.name
    )

    return FileResponse(
        image_file,
        content_type=content_type or 'application/octet-stream'
    )
