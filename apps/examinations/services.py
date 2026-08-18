from apps.examinations.models import ExamSchedule
from apps.enrollment.models import StudentEnrollment


class ExamSeatingGeneratorService:
    """
    Automated Exam Seating Generator (Point 21).
    Assigns students to Hall, Row, Seat, and generates printable seating plans.
    """
    @staticmethod
    def generate_seating_plan(exam_schedule: ExamSchedule, rows_per_hall: int = 5, seats_per_row: int = 8):
        school = exam_schedule.school
        section = exam_schedule.section

        enrollments = StudentEnrollment.objects.filter(school=school, section=section, status='ACTIVE').order_by('student__last_name', 'student__first_name')
        
        seating_plan = []
        seat_num = 1

        for idx, enrollment in enumerate(enrollments):
            row_num = (idx // seats_per_row) + 1
            seat_in_row = (idx % seats_per_row) + 1
            
            seating_plan.append({
                'student_id': enrollment.student.student_id,
                'student_name': enrollment.student.full_name,
                'hall': exam_schedule.room or 'Main Hall',
                'row': f"Row {row_num}",
                'seat': f"Seat {seat_in_row}",
                'seating_number': f"SEAT-{seat_num:03d}"
            })
            seat_num += 1

        return seating_plan
