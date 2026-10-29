from rest_framework import serializers
from apps.tenants.models import School
from apps.accounts.models import User
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.enrollment.models import StudentEnrollment
from apps.attendance.models import AttendanceRecord
from apps.assessments.models import StudentMark, AssessmentComponent
from apps.finance.models import StudentInvoice, Payment


class TenantScopedModelSerializer(serializers.ModelSerializer):
    """
    Base ModelSerializer that enforces strict multi-tenant boundaries:
    1. Restricts querysets of all related fields referencing TenantAware models
       to the authenticated user's active school context.
    2. Enforces that all referenced objects belong to the active school tenant.
    3. Prevents cross-tenant foreign-key substitution during create, update, and partial update.
    4. Automatically protects 'school' from client-side tampering.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        school = self._resolve_context_school()

        # Scope querysets of all related fields to the active tenant school
        for field_name, field in self.fields.items():
            if isinstance(field, serializers.PrimaryKeyRelatedField) or hasattr(field, 'queryset'):
                queryset = getattr(field, 'queryset', None)
                if queryset is not None and hasattr(queryset.model, 'school'):
                    if school is not None:
                        field.queryset = queryset.filter(school=school)
                    else:
                        # Without an authenticated tenant context, related querysets are empty
                        field.queryset = queryset.none()

    def _resolve_context_school(self):
        request = self.context.get('request')
        if not request:
            if self.instance and hasattr(self.instance, 'school'):
                return self.instance.school
            return None

        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if getattr(user, 'role', None) == 'SUPER_ADMIN' or getattr(user, 'is_superuser', False):
                return getattr(request, 'school', None) or getattr(user, 'school', None)
            return getattr(user, 'school', None)
        return getattr(request, 'school', None)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        school = self._resolve_context_school()

        # When updating, the instance's school is the immutable anchor
        if self.instance and hasattr(self.instance, 'school'):
            anchor_school = self.instance.school
        else:
            anchor_school = school

        referenced_schools = set()

        for field_name, value in attrs.items():
            if value is not None and hasattr(value, 'school_id'):
                referenced_schools.add(value.school_id)
                if anchor_school is not None:
                    if value.school_id != anchor_school.id:
                        raise serializers.ValidationError({
                            field_name: "Referenced object does not belong to the active school tenant."
                        })
                else:
                    raise serializers.ValidationError({
                        field_name: "Cannot associate tenant resource without an active school context."
                    })

        if len(referenced_schools) > 1:
            raise serializers.ValidationError(
                "All referenced related objects must belong to the same school tenant."
            )

        return attrs


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ['id', 'name', 'subdomain', 'code', 'motto', 'calendar_preference', 'phone', 'email']


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone']


class AcademicYearSerializer(TenantScopedModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'
        read_only_fields = ['school']


class GradeSerializer(TenantScopedModelSerializer):
    class Meta:
        model = Grade
        fields = '__all__'
        read_only_fields = ['school']


class SectionSerializer(TenantScopedModelSerializer):
    grade_name = serializers.ReadOnlyField(source='grade.name')
    stream_name = serializers.ReadOnlyField(source='stream.name')

    class Meta:
        model = Section
        fields = ['id', 'name', 'grade', 'grade_name', 'stream', 'stream_name', 'capacity', 'shift']
        read_only_fields = ['school']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        grade = attrs.get('grade') or (self.instance.grade if self.instance else None)
        stream = attrs.get('stream') or (self.instance.stream if self.instance else None)
        if grade and stream and grade.school_id != stream.school_id:
            raise serializers.ValidationError("Grade and Stream must belong to the same school.")
        return attrs


class StudentProfileSerializer(TenantScopedModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = StudentProfile
        fields = ['id', 'student_id', 'first_name', 'middle_name', 'last_name', 'full_name', 'gender', 'status']
        read_only_fields = ['school']


class AttendanceRecordSerializer(TenantScopedModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = ['id', 'section', 'student', 'student_name', 'date', 'status']
        read_only_fields = ['school', 'recorded_by']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        section = attrs.get('section') or (self.instance.section if self.instance else None)
        student = attrs.get('student') or (self.instance.student if self.instance else None)
        if section and student and section.school_id != student.school_id:
            raise serializers.ValidationError("Section and Student must belong to the same school.")
        return attrs


class StudentMarkSerializer(TenantScopedModelSerializer):
    component_name = serializers.CharField(source='assessment_component.name', read_only=True)

    class Meta:
        model = StudentMark
        fields = ['id', 'enrollment', 'assessment_component', 'component_name', 'mark_value', 'status']
        read_only_fields = ['school', 'entered_by', 'letter_grade', 'grade_points']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        enrollment = attrs.get('enrollment') or (self.instance.enrollment if self.instance else None)
        component = attrs.get('assessment_component') or (self.instance.assessment_component if self.instance else None)
        if enrollment and component and enrollment.school_id != component.school_id:
            raise serializers.ValidationError("Enrollment and Assessment Component must belong to the same school.")
        return attrs


class StudentInvoiceSerializer(TenantScopedModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    remaining_balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = StudentInvoice
        fields = ['id', 'student', 'student_name', 'academic_year', 'period', 'invoice_number', 'total_amount', 'discount_amount', 'paid_amount', 'remaining_balance', 'due_date', 'status']
        read_only_fields = ['school']

