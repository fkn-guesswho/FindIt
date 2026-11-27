from django.test import TestCase

from accounts.models import User
from items.models import Item, MatchingConfiguration
from items.matching import (
    DEFAULT_MATCH_THRESHOLD,
    find_matching_items,
)

from datetime import date
from items.models import Item, ItemMatch, MatchingConfiguration

class MatchingConfigurationTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='matching_test_user',
            password='test-password-123'
        )

    def test_default_threshold_is_used_without_configuration(self):
        self.assertFalse(
            MatchingConfiguration.objects.filter(pk=1).exists()
        )

        # No configuration exists, so the default should be 0.50.
        self.assertEqual(DEFAULT_MATCH_THRESHOLD, 0.50)

    def test_configured_threshold_is_used(self):
        MatchingConfiguration.objects.create(
            pk=1,
            threshold=0.90
        )

        configuration = MatchingConfiguration.objects.filter(
            pk=1
        ).first()

        threshold = (
            configuration.threshold
            if configuration
            else DEFAULT_MATCH_THRESHOLD
        )

        self.assertEqual(threshold, 0.90)

    def create_test_item(self, report_type):
        return Item.objects.create(
            title='Black Lenovo laptop',
            colour='Black',
            brand='Lenovo',
            description='Black Lenovo laptop with a damaged corner',
            category=Item.Category.ELECTRONICS,
            report_type=report_type,
            campus='Main Campus',
            building='Library',
            specific_location='Second Floor',
            date_occurred=date(2026, 11, 20),
            reported_by=self.user,
        )
    def test_match_below_configured_threshold_is_not_saved(self):
        MatchingConfiguration.objects.create(
            pk=1,
            threshold=0.90
        )

        lost_item = self.create_test_item(
            Item.ReportType.LOST
        )

        found_item = self.create_test_item(
            Item.ReportType.FOUND
        )

        found_item.colour = 'Blue'
        found_item.save(update_fields=['colour'])

        matches = find_matching_items(
            lost_item,
            candidate_queryset=Item.objects.filter(
                pk=found_item.pk
            )
        )

        self.assertEqual(matches, [])
        self.assertFalse(
            ItemMatch.objects.filter(
                lost_item=lost_item,
                found_item=found_item
            ).exists()
        )