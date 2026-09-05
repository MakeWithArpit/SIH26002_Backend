from django.contrib import admin
from .models import IncidentReport


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'officer', 'incident_type', 'severity',
        'analysis_status', 'status', 'server_timestamp',
    ]
    list_filter = ['incident_type', 'severity', 'analysis_status', 'status']
    search_fields = ['officer__username', 'description']
    readonly_fields = [
        'server_timestamp', 'updated_at',
        'ai_issue_type', 'ai_severity', 'ai_confidence', 'analysis_status',
    ]
    raw_id_fields = ['officer']
