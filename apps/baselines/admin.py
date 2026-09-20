from django.contrib import admin

from .models import Baseline


@admin.register(Baseline)
class BaselineAdmin(admin.ModelAdmin):
    list_display = ('metric', 'value', 'unit', 'version', 'technology_type', 'geographic_scope', 'source')
    list_filter = ('metric', 'technology_type', 'geographic_scope')
    search_fields = ('metric', 'source')
