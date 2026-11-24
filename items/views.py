
import mimetypes

from django.contrib import messages

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import FileResponse, Http404

from .forms import ItemReportForm, ClaimForm, ClosureRequestForm
from .models import Item, Claim, ClaimEvidence, ItemImage, ClosureRequest


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
        {'items': items}
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

def browse_items(request):

    items = Item.objects.filter(
        status=Item.Status.OPEN,
        visibility=Item.Visibility.PUBLIC,
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
        and request.user != item.reported_by
        and existing_claim is None
    )


    return render(request, 'items/item_detail.html', {
        'item': item,
        'can_claim': can_claim,
        'existing_claim': existing_claim,
        'is_owner_or_admin': is_owner_or_admin,
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
