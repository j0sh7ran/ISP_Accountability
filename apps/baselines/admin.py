from django.contrib import admin

from apps.core.admin_csv import CSVImportExportMixin

from .models import Baseline


@admin.register(Baseline)
class BaselineAdmin(CSVImportExportMixin, admin.ModelAdmin):
    list_display = ('metric', 'value', 'unit', 'version', 'technology_type', 'geographic_scope', 'source')
    list_filter = ('metric', 'technology_type', 'geographic_scope')
    search_fields = ('metric', 'source')
    csv_fields = (
        'metric', 'value', 'unit', 'population_context', 'technology_type', 'geographic_scope',
        'source', 'source_url', 'publication_date', 'methodology', 'notes', 'version',
    )
    csv_key_fields = ('metric', 'version', 'technology_type', 'geographic_scope')
