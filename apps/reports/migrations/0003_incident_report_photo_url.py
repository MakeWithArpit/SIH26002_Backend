from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Migrate IncidentReport photo storage from local ImageField to ImageKit.io CDN URLField.

    Before: photo = ImageField(upload_to='reports/photos/%Y/%m/%d/')
            — stores binary file locally, requires media/ volume

    After:  photo_url = URLField(max_length=500)
            — stores ImageKit CDN URL; no local storage required
    """

    dependencies = [
        ('reports', '0002_remove_incidentreport_snapped_road_segment_id_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='incidentreport',
            name='photo',
        ),
        migrations.AddField(
            model_name='incidentreport',
            name='photo_url',
            field=models.URLField(
                max_length=500,
                help_text='ImageKit.io CDN URL of the uploaded photo.',
            ),
        ),
    ]
