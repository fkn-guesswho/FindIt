
from django.contrib.postgres.search import TrigramSimilarity

from .models import Item, ItemMatch, MatchingConfiguration


DEFAULT_MATCH_THRESHOLD = 0.50
MAX_MATCH_SUGGESTIONS = 3


def normalise(value):
    """Normalise text for case-insensitive comparisons."""
    return (value or '').strip().casefold()


def compare_location(item_a, item_b):
    """
    Return 1 when campus, building and specific location
    all match; otherwise return 0.
    """
    fields = (
        'campus',
        'building',
        'specific_location',
    )

    return int(
        all(
            normalise(getattr(item_a, field))
            and normalise(getattr(item_a, field))
            == normalise(getattr(item_b, field))
            for field in fields
        )
    )


def calculate_date_similarity(lost_item, found_item):
    """
    Date similarity decreases over a 14-day period.

    If the item was found before it was lost, return 0.
    """
    days_between = (
        found_item.date_occurred - lost_item.date_occurred
    ).days

    if days_between < 0:
        return 0.0

    return max(0.0, 1 - (days_between / 14))


def calculate_similarity(item_a, item_b, text_score):
    """
    Calculate the weighted similarity score for
    a LOST and FOUND report pair.
    """
    if item_a.category != item_b.category:
        return None

    if item_a.report_type == Item.ReportType.LOST:
        lost_item = item_a
        found_item = item_b
    else:
        lost_item = item_b
        found_item = item_a

    colour_score = int(
        bool(normalise(item_a.colour))
        and normalise(item_a.colour) == normalise(item_b.colour)
    )

    brand_score = int(
        bool(normalise(item_a.brand))
        and normalise(item_a.brand) == normalise(item_b.brand)
    )

    location_score = compare_location(item_a, item_b)

    date_score = calculate_date_similarity(
        lost_item,
        found_item
    )

    total_score = (
        0.40 * text_score
        + 0.15 * colour_score
        + 0.15 * brand_score
        + 0.15 * location_score
        + 0.15 * date_score
    )

    return {
        'score': total_score,
        'text': text_score,
        'colour': colour_score,
        'brand': brand_score,
        'location': location_score,
        'date': date_score,
    }



def find_matching_items(
    item,
    threshold=None,
    candidate_queryset=None
):

    """
    Find and persist qualifying opposite-type report pairs.

    All qualifying pairs are stored. Only the top three
    are returned for display.

    This does not confirm ownership, approve claims
    or modify report status.

    Access permissions and visibility must be enforced
    by the views that display these suggestions.
    """

    if threshold is None:
        configuration = MatchingConfiguration.objects.filter(
            pk=1
        ).first()

        threshold = (
            configuration.threshold
            if configuration
            else DEFAULT_MATCH_THRESHOLD
        )

    if not item.pk or item.status != Item.Status.OPEN:
        return []

    if item.report_type not in Item.ReportType.values:
        return []

    opposite_type = (
        Item.ReportType.FOUND
        if item.report_type == Item.ReportType.LOST
        else Item.ReportType.LOST
    )

    candidates = (
        candidate_queryset
        if candidate_queryset is not None
        else Item.objects.all()
    )

    candidates = (
        candidates
        .filter(
            report_type=opposite_type,
            category=item.category,
            status=Item.Status.OPEN,
        )
        .exclude(pk=item.pk)
        .annotate(
            text_similarity=TrigramSimilarity(
                'description',
                item.description,
            )
        )
    )

    matches = []

    for candidate in candidates:
        components = calculate_similarity(
            item,
            candidate,
            candidate.text_similarity,
        )

        if components is None:
            continue

        if components['score'] > threshold:

            if item.report_type == Item.ReportType.LOST:
                lost_item = item
                found_item = candidate
            else:
                lost_item = candidate
                found_item = item

            ItemMatch.objects.update_or_create(
                lost_item=lost_item,
                found_item=found_item,
                defaults={
                    'similarity_score': components['score'],
                }
            )

            candidate.similarity_score = components['score']
            candidate.match_components = components
            matches.append(candidate)

    matches.sort(
        key=lambda candidate: candidate.similarity_score,
        reverse=True,
    )

    return matches[:MAX_MATCH_SUGGESTIONS]
