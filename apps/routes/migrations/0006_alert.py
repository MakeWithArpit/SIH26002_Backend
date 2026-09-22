from django.contrib.gis.db import models
from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('routes', '0005_infrastructure_risk_updated_at'),
        ('vehicles', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Alert',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('alert_id', models.CharField(db_index=True, help_text='Unique alert identifier (e.g., infra-5-high)', max_length=100, unique=True)),
                ('alert_type', models.CharField(choices=[('infrastructure_risk', 'Infrastructure Risk'), ('extreme_weather', 'Extreme Weather'), ('heavy_rainfall', 'Heavy Rainfall'), ('weather_warning', 'Weather Warning'), ('flood_detection', 'Flood Detection'), ('landslide_warning', 'Landslide Warning'), ('road_blockage', 'Road Blockage'), ('delivery_delay', 'Delivery Delay')], db_index=True, max_length=30)),
                ('severity', models.CharField(choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], db_index=True, max_length=10)),
                ('status', models.CharField(choices=[('active', 'Active'), ('acknowledged', 'Acknowledged'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], db_index=True, default='active', max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField()),
                ('recommended_action', models.TextField(blank=True, default='')),
                ('location', models.PointField(geography=True, null=True, srid=4326, blank=True)),
                ('risk_score', models.FloatField(blank=True, null=True)),
                ('risk_level', models.CharField(blank=True, default='', max_length=10)),
                ('disruption_probability', models.FloatField(blank=True, null=True)),
                ('rainfall_mm', models.FloatField(blank=True, null=True)),
                ('weather_condition', models.CharField(blank=True, default='', max_length=20)),
                ('generated_by', models.CharField(default='system', help_text='Source of alert generation', max_length=50)),
                ('generated_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='assigned_alerts', to=settings.AUTH_USER_MODEL)),
                ('district', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='alerts', to='routes.district')),
                ('infrastructure', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='alerts', to='routes.infrastructure')),
                ('trip', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='alerts', to='vehicles.trip')),
            ],
            options={
                'ordering': ['-generated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['status', '-generated_at'], name='routes_alert_status_d8e8c4_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['severity', 'status'], name='routes_alert_severity_52f2b5_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['alert_type', 'status'], name='routes_alert_alert_ty_1a0c5f_idx'),
        ),
        migrations.AddIndex(
            model_name='alert',
            index=models.Index(fields=['district', 'status'], name='routes_alert_district_7a8c3e_idx'),
        ),
    ]