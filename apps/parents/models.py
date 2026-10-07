from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.students.models import StudentProfile


class ParentProfile(TenantAwareModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='parent_profile')
    phone = models.CharField(max_length=50)
    relationship = models.CharField(max_length=50, default='Father')  # Father, Mother, Guardian
    preferred_language = models.CharField(max_length=10, choices=[('am', 'Amharic'), ('en', 'English')], default='am')

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.relationship})"

    @property
    def unique_children_info(self):
        """
        Returns a deduplicated list of linked active children with their latest grade & section.
        Used for clean sibling display in admin search dropdowns.
        """
        children_data = []
        seen_student_ids = set()

        for g in self.guardianships.select_related('student').all():
            student = g.student
            if not student or student.id in seen_student_ids:
                continue
            seen_student_ids.add(student.id)

            latest_enrollment = student.enrollments.select_related('grade', 'section').order_by('-academic_year__gregorian_start_date', '-enrollment_date').first()
            
            section_display = f"{latest_enrollment.grade.name} - Section {latest_enrollment.section.name}" if latest_enrollment and latest_enrollment.section and latest_enrollment.grade else "Enrolled"
            section_id = str(latest_enrollment.section_id) if latest_enrollment and latest_enrollment.section_id else ""

            children_data.append({
                'student_id': str(student.id),
                'full_name': student.full_name,
                'code': student.student_id,
                'section_display': section_display,
                'section_id': section_id,
            })

        return children_data

    @classmethod
    def link_student_by_phone(cls, school, student_profile, phone, parent_name=None, relationship="Father"):
        """
        Links a student to a parent by searching for an existing parent profile matching the phone number.
        If found, links student to existing parent (giving single login credentials for multiple children).
        If not found, creates a new parent account and links the student.
        """
        if not phone:
            return None

        phone_clean = str(phone).strip()
        parent_profile = cls.objects.filter(school=school, phone=phone_clean).first()

        if not parent_profile:
            from apps.accounts.models import User, UserRole
            digits = ''.join(filter(str.isdigit, phone_clean))
            username = f"parent_{digits[-6:]}" if len(digits) >= 6 else f"parent_{student_profile.student_id.lower()}"
            
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': parent_name or f"Parent of {student_profile.first_name}",
                    'role': UserRole.PARENT,
                    'school': school,
                }
            )
            if created:
                from apps.accounts.utils import get_default_role_password
                temp_password = get_default_role_password(UserRole.PARENT)
                user.set_password(temp_password)
                user.must_change_password = True
                user.save()


            parent_profile, _ = cls.objects.get_or_create(
                user=user,
                school=school,
                defaults={
                    'phone': phone_clean,
                    'relationship': relationship,
                }
            )

        GuardianRelationship.objects.get_or_create(
            school=school,
            parent=parent_profile,
            student=student_profile,
            defaults={'is_primary': True}
        )
        return parent_profile


class GuardianRelationship(TenantAwareModel):
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name='guardianships')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='guardianships')
    is_primary = models.BooleanField(default=True)

    class Meta:
        unique_together = ('school', 'parent', 'student')

    def __str__(self):
        return f"{self.parent.user.username} -> {self.student.full_name}"
