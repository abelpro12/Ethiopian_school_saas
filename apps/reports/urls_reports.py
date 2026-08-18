from django.urls import path
from .views import (
    download_report_card_pdf_view, download_receipt_pdf_view, download_transcript_pdf_view,
    download_transfer_certificate_pdf_view, download_enrollment_certificate_pdf_view,
    alumni_reports_view, export_alumni_list_csv, bulk_transcripts_pdf_view,
    bulk_historical_import_view
)
from .views_moe import moe_report_view, moe_export_excel_view

urlpatterns = [
    path('report-card/<uuid:student_id>/<str:period_id>/', download_report_card_pdf_view, name='download_report_card_pdf'),
    path('receipt/<uuid:payment_id>/', download_receipt_pdf_view, name='download_receipt_pdf'),
    path('transcript/<uuid:student_id>/', download_transcript_pdf_view, name='download_transcript_pdf'),
    path('transfer-certificate/<uuid:student_id>/', download_transfer_certificate_pdf_view, name='download_transfer_certificate_pdf'),
    path('enrollment-certificate/<uuid:student_id>/', download_enrollment_certificate_pdf_view, name='download_enrollment_certificate_pdf'),
    path('moe/', moe_report_view, name='moe_report'),
    path('moe/export/excel/', moe_export_excel_view, name='moe_export_excel'),
    path('alumni/', alumni_reports_view, name='alumni_reports'),
    path('alumni/export-list/', export_alumni_list_csv, name='export_alumni_list'),
    path('alumni/bulk-transcripts/', bulk_transcripts_pdf_view, name='bulk_transcripts_pdf'),
    path('historical-import/', bulk_historical_import_view, name='bulk_historical_import'),
]


