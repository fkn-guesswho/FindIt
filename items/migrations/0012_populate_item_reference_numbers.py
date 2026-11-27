import secrets

from django.db import migrations


def populate_reference_numbers(apps, schema_editor):
    Item = apps.get_model('items', 'Item')
    database = schema_editor.connection.alias

    existing_numbers = set(
        Item.objects.using(database)
        .exclude(reference_number__isnull=True)
        .values_list('reference_number', flat=True)
    )

    for item in (
        Item.objects.using(database)
        .filter(reference_number__isnull=True)
        .order_by('pk')
    ):
        prefix = 'LST' if item.report_type == 'LOST' else 'FND'
        year = item.created_at.year

        while True:
            number = f"{prefix}-{year}-{secrets.randbelow(1_000_000):06d}"

            if number not in existing_numbers:
                break

        item.reference_number = number
        item.save(update_fields=['reference_number'])
        existing_numbers.add(number)


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0011_item_brand_item_colour_item_current_holding_location_and_more'),
    ]

    operations = [
        migrations.RunPython(
            populate_reference_numbers,
            migrations.RunPython.noop,
        ),
    ]