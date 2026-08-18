from django.db.models import Q
from apps.tenants.models import School
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile
from apps.teachers.models import TeacherProfile, StaffProfile
from apps.finance.models import StudentInvoice, Payment


class CentralizedSearchEngine:
    """
    Centralized School Search Engine (Point 28).
    Queries Students, Parents, Teachers, Staff, Invoices, and Payments with tenant-scoped isolation.
    Searches across student_id, admission_number, national_id, staff employee_id, position, and names.
    """
    @staticmethod
    def search(school: School, query: str):
        if not query or len(query.strip()) < 2:
            return {'students': [], 'parents': [], 'teachers': [], 'staff': [], 'invoices': [], 'payments': []}

        q = query.strip()

        students = StudentProfile.objects.filter(
            Q(school=school) & (
                Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                Q(student_id__icontains=q) | Q(admission_number__icontains=q) |
                Q(national_id__icontains=q) | Q(roll_number__icontains=q) |
                Q(amharic_name__icontains=q) | Q(phone__icontains=q)
            )
        )[:10]

        parents = ParentProfile.objects.filter(
            Q(school=school) & (
                Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) |
                Q(phone__icontains=q)
            )
        )[:10]

        teachers = TeacherProfile.objects.filter(
            Q(school=school) & (
                Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) |
                Q(employee_id__icontains=q)
            )
        )[:10]

        staff = StaffProfile.objects.filter(
            Q(school=school) & (
                Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) |
                Q(employee_id__icontains=q) | Q(position__icontains=q) | Q(department__icontains=q)
            )
        )[:10]

        invoices = StudentInvoice.objects.filter(
            Q(school=school) & (
                Q(invoice_number__icontains=q) | Q(student__first_name__icontains=q)
            )
        )[:10]

        payments = Payment.objects.filter(
            Q(school=school) & (
                Q(tx_ref__icontains=q) | Q(receipt_no__icontains=q)
            )
        )[:10]

        return {
            'students': [
                {
                    'id': s.id,
                    'title': s.full_name,
                    'subtitle': f"ID: {s.student_id} | Adm: {s.admission_number or 'N/A'}",
                    'url': f"/settings/users/?search={s.student_id}",
                    'icon': 'fa-user-graduate',
                    'badge': 'Student'
                } for s in students
            ],
            'parents': [
                {
                    'id': p.id,
                    'title': p.user.get_full_name() or p.user.username,
                    'subtitle': f"Phone: {p.phone or 'N/A'} ({p.relationship or 'Parent'})",
                    'url': f"/settings/users/?search={p.phone or p.user.username}",
                    'icon': 'fa-user-group',
                    'badge': 'Parent'
                } for p in parents
            ],
            'teachers': [
                {
                    'id': t.id,
                    'title': t.user.get_full_name() or t.user.username,
                    'subtitle': f"Emp ID: {t.employee_id or 'N/A'} | {t.specialization or 'Teacher'}",
                    'url': f"/teachers/assignments/",
                    'icon': 'fa-chalkboard-user',
                    'badge': 'Teacher'
                } for t in teachers
            ],
            'staff': [
                {
                    'id': st.id,
                    'title': st.user.get_full_name() or st.user.username,
                    'subtitle': f"Emp ID: {st.employee_id or 'N/A'} | {st.position or 'Staff'}",
                    'url': f"/teachers/management/",
                    'icon': 'fa-id-badge',
                    'badge': 'Staff'
                } for st in staff
            ],
            'invoices': [
                {
                    'id': inv.id,
                    'title': f"Invoice #{inv.invoice_number}",
                    'subtitle': f"Student: {inv.student.full_name} | Status: {inv.status}",
                    'url': f"/finance/invoices/",
                    'icon': 'fa-file-invoice-dollar',
                    'badge': 'Invoice'
                } for inv in invoices
            ],
            'payments': [
                {
                    'id': pay.id,
                    'title': f"Payment #{pay.receipt_no or pay.tx_ref[:12]}",
                    'subtitle': f"Ref: {pay.tx_ref} | Status: {pay.status}",
                    'url': f"/finance/dashboard/",
                    'icon': 'fa-receipt',
                    'badge': 'Payment'
                } for pay in payments
            ]
        }
