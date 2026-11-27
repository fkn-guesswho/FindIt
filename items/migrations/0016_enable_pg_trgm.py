from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0015_matchingconfiguration'),
    ]

    operations = [
        TrigramExtension(),
    ]