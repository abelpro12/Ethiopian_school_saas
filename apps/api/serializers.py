from rest_framework import serializers
from apps.tenants.models import School
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark
from apps.finance.models import StudentInvoice, Payment


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ['id', 'name', 'subdomain', 'code', 'motto', 'calendar_preference', 'phone', 'email']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone']


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'


class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'


class SectionSerializer(serializers.ModelSerializer):
    grade_name = serializers.ReadOnlyField(source='grade.name')
    stream_name = serializers.ReadOnlyField(source='stream.name')

    class Meta:
        model = Section
        fields = ['id', 'name', 'grade', 'grade_name', 'stream', 'stream_name', 'capacity', 'shift']


class StudentProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = StudentProfile
        fields = ['id', 'student_id', 'first_name', 'middle_name', 'last_name', 'full_name', 'gender', 'status']


class AttendanceRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.ReadOnlyField(source='student.full_name')

    class Meta:
        model = AttendanceRecord
        fields = ['id', 'section', 'student', 'student_name', 'date', 'status']


class StudentMarkSerializer(serializers.ModelSerializer):
    component_name = serializers.ReadOnlyField(source='assessment_component.name')

    class Meta:
        model = StudentMark
        fields = ['id', 'enrollment', 'assessment_component', 'component_name', 'mark_value', 'status']


class StudentInvoiceSerializer(serializers.ModelSerializer):
    remaining_balance = serializers.ReadOnlyField()

    class Meta:
        model = StudentInvoice
        fields = ['id', 'invoice_number', 'total_amount', 'paid_amount', 'remaining_balance', 'due_date', 'status']
