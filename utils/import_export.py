import csv
import io
from apps.tenants.models import School
from apps.students.models import StudentProfile


class TenantImportExportService:
    """
    Tenant-Scoped Data Import and Export Service (Points 25, 26 & 62).
    Provides CSV export and atomic bulk import with validation preview.
    Includes separate identifiers: Student ID, Admission No, Roll No, National ID.
    """
    @staticmethod
    def export_students_csv(school: School) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Student ID', 'Admission No', 'Roll No', 'National ID', 'First Name', 'Middle Name', 'Last Name', 'Gender', 'Phone', 'Status'])

        students = StudentProfile.objects.filter(school=school)
        for s in students:
            writer.writerow([
                s.student_id, s.admission_number or '', s.roll_number or '', s.national_id or '',
                s.first_name, s.middle_name, s.last_name, s.gender, s.phone or '', s.status
            ])

        return output.getvalue()

    @staticmethod
    def preview_student_import_csv(csv_content: str):
        reader = csv.DictReader(io.StringIO(csv_content))
        valid_rows = []
        errors = []

        for idx, row in enumerate(reader, start=1):
            if not row.get('Student ID') or not row.get('First Name') or not row.get('Last Name'):
                errors.append(f"Row {idx}: Missing required fields (Student ID, First Name, Last Name)")
            else:
                valid_rows.append(row)

        return {
            'total_rows': len(valid_rows) + len(errors),
            'valid_count': len(valid_rows),
            'error_count': len(errors),
            'errors': errors
        }
