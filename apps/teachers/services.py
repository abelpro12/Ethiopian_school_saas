from django.db.models import Avg
from apps.teachers.models import TeacherProfile, TeacherAssignment
from apps.academics.models import Section, Subject
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.assessments.models import StudentConduct, StudentMark
from apps.parents.models import GuardianRelationship


class HomeroomService:
    """
    Explicit Homeroom Management Engine (Requirement 12).
    Provides Homeroom Teachers full visibility into section students, parent contacts,
    attendance records, conduct ratings, announcements, and general performance summaries.
    Enforces strict security checks blocking mark editing/submission for non-assigned subjects.
    """
    @staticmethod
    def get_homeroom_dashboard(teacher_profile: TeacherProfile, current_ay=None) -> dict:
        school = teacher_profile.school
        
        if current_ay:
            section = Section.objects.filter(school=school, class_teacher=teacher_profile.user).first()
            academic_year = current_ay
        else:
            section = Section.objects.filter(school=school, class_teacher=teacher_profile.user).first()
            from apps.academics.models import AcademicYear
            academic_year = AcademicYear.objects.filter(school=school, is_active=True).first()

        if not section:
            return {'has_homeroom': False, 'message': 'Teacher is not currently assigned as a homeroom teacher.'}

        enrollments = StudentEnrollment.objects.filter(
            school=school, academic_year=academic_year, section=section, status=EnrollmentStatus.ACTIVE, student__isnull=False
        ).select_related('student')

        students_data = []
        for enr in enrollments:
            student = getattr(enr, 'student', None)
            if not student:
                continue
            guardians = GuardianRelationship.objects.filter(school=school, student=student)

            parent_contacts = [{'name': g.parent.user.get_full_name(), 'phone': g.parent.phone, 'relationship': g.parent.relationship} for g in guardians]

            # Section Attendance summary for student
            att_records = AttendanceRecord.objects.filter(school=school, section=section, student=student)
            total_days = att_records.count()
            absent_days = att_records.filter(status=AttendanceStatus.ABSENT).count()
            att_rate = 100.0 if total_days == 0 else ((total_days - absent_days) / total_days) * 100.0

            # Latest Conduct from apps.assessments.models
            latest_conduct = StudentConduct.objects.filter(school=school, enrollment=enr).order_by('-created_at').first()

            # Overall Performance Average across assessments
            avg_score = StudentMark.objects.filter(school=school, enrollment=enr).aggregate(avg=Avg('mark_value'))['avg'] or 0.0

            students_data.append({
                'student_id': student.student_id,
                'full_name': student.full_name,
                'parent_contacts': parent_contacts,
                'attendance_rate': round(att_rate, 2),
                'conduct': latest_conduct.get_grade_display() if latest_conduct else 'Not Rated',
                'average_score': round(float(avg_score), 2)
            })

        # 2. Scoped Subjects (Subjects teacher is authorized to edit marks for)
        assigned_subjects = Subject.objects.filter(
            teacher_assignments__school=school,
            teacher_assignments__teacher=teacher_profile,
            teacher_assignments__section=section
        ).distinct()

        return {
            'has_homeroom': True,
            'section_name': f"{section.grade.name}-{section.name}",
            'total_students': len(students_data),
            'students': students_data,
            'authorized_mark_edit_subjects': [s.name for s in assigned_subjects]
        }

    @staticmethod
    def can_teacher_edit_subject_marks(teacher_profile: TeacherProfile, section: Section, subject: Subject) -> bool:
        """
        Constraint Check (Requirement 12):
        Ensures homeroom teachers cannot edit marks for subjects they do not explicitly teach.
        """
        return TeacherAssignment.objects.filter(
            school=teacher_profile.school,
            teacher=teacher_profile,
            section=section,
            subject=subject
        ).exists()
