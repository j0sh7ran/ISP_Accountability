"""Generic CSV import/export for "configurable" ModelAdmins (Target, ScheduleConfig,
RetentionPolicy, StateMachineConfig, SLARule, Baseline) — lets a whole network's configuration be
exported from one machine and imported on another (or just bulk-edited) instead of one row at a
time through the normal admin forms.

Deliberately hand-rolled with the stdlib `csv` module rather than a new dependency
(e.g. django-import-export) — matches this project's "minimal dependencies" pattern.
"""
import csv
import io

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='CSV file',
        help_text='First row must be a header with column names matching the exported format. '
                   'Unrecognized columns are ignored.',
    )


class CSVImportExportMixin:
    """Mix into a ModelAdmin alongside:

    - `csv_fields`: tuple of field names, in column order (also used for export).
    - `csv_key_fields`: tuple of field names that uniquely identify a row for update-vs-create
      (ignored if `csv_singleton = True`, which always updates the one `pk=1` row instead).
    """

    csv_fields = ()
    csv_key_fields = ()
    csv_singleton = False
    change_list_template = 'admin/csv_changelist.html'
    actions = ['export_as_csv']

    @admin.action(description='Export selected as CSV')
    def export_as_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{self.model._meta.model_name}_export.csv"'
        writer = csv.writer(response)
        writer.writerow(self.csv_fields)
        for obj in queryset:
            writer.writerow([self._export_value(getattr(obj, field)) for field in self.csv_fields])
        return response

    def _export_value(self, value):
        if value is None:
            return ''
        if hasattr(value, 'isoformat'):
            return value.isoformat()
        return value

    def get_urls(self):
        # Must come before super()'s urls, otherwise the `<path:object_id>/` change-view pattern
        # swallows this literal path first.
        custom_urls = [
            path('import-csv/', self.admin_site.admin_view(self.import_csv_view), name=self._import_csv_url_name()),
        ]
        return custom_urls + super().get_urls()

    def _import_csv_url_name(self):
        return f'{self.model._meta.app_label}_{self.model._meta.model_name}_import_csv'

    def import_csv_view(self, request):
        # A singleton config row always exists already, so importing it is really an update, not
        # an add — check the permission that actually applies instead of always requiring "add".
        allowed = self.has_change_permission(request) if self.csv_singleton else self.has_add_permission(request)
        if not allowed:
            raise PermissionDenied

        if request.method == 'POST':
            form = CSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                created, updated, errors = self._import_csv(request.FILES['csv_file'])
                if created or updated:
                    self.message_user(request, f'Imported {created} new and updated {updated} existing row(s).')
                for error in errors:
                    self.message_user(request, error, level=messages.ERROR)
                return redirect('..')
        else:
            form = CSVImportForm()

        context = {
            **self.admin_site.each_context(request),
            'form': form,
            'title': f'Import {self.model._meta.verbose_name_plural} from CSV',
            'opts': self.model._meta,
        }
        return render(request, 'admin/csv_import_form.html', context)

    def _import_csv(self, file_obj):
        decoded = file_obj.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(decoded))
        created = updated = 0
        errors = []
        for line_number, row in enumerate(reader, start=2):  # header is line 1
            try:
                values = {field: self._parse_value(field, row.get(field, '')) for field in self.csv_fields}
                if self.csv_singleton:
                    lookup = {'pk': 1}
                else:
                    lookup = {field: values.pop(field) for field in self.csv_key_fields}
                _, was_created = self.model.objects.update_or_create(defaults=values, **lookup)
                created += was_created
                updated += not was_created
            except Exception as exc:
                errors.append(f'Row {line_number}: {exc}')
        return created, updated, errors

    def _parse_value(self, field_name, raw_value):
        field = self.model._meta.get_field(field_name)
        raw_value = raw_value.strip() if isinstance(raw_value, str) else raw_value

        if raw_value == '':
            return None if field.null else ('' if isinstance(field, (models.CharField, models.TextField)) else None)
        if isinstance(field, models.BooleanField):
            return raw_value.lower() in ('1', 'true', 'yes', 'y', 'on')
        if isinstance(field, models.DateField):
            from django.utils.dateparse import parse_date
            return parse_date(raw_value)
        if isinstance(field, models.FloatField):
            return float(raw_value)
        if isinstance(field, models.IntegerField):
            return int(raw_value)
        return raw_value
