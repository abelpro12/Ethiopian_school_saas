import uuid
import random
from django.shortcuts import render, redirect
from django.contrib import messages


def public_admission_form_view(request):
    """
    Public-facing online admission form — no login required.
    Parents/guardians fill this form to apply for their child's admission.
    """
    if request.method == 'POST':
        from apps.students.models import StudentApplication, ApplicationStatus
        from apps.tenants.models import School

        # We need to know which school this is. Use a slug or domain.
        school_code = request.POST.get('school_code', '').strip().upper()
        first_name = request.POST.get('first_name', '').strip()
        middle_name = request.POST.get('middle_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        gender = request.POST.get('gender', 'M')
        grade_level = request.POST.get('grade_level', '9')
        previous_school = request.POST.get('previous_school', '').strip()
        parent_name = request.POST.get('parent_name', '').strip()
        parent_phone = request.POST.get('parent_phone', '').strip()

        try:
            school = School.objects.get(code=school_code)
        except School.DoesNotExist:
            messages.error(request, f"No school found with code '{school_code}'. Please check the school code and try again.")
            return render(request, 'students/public_admission.html', {'form_data': request.POST})

        # Generate unique application number
        app_number = f"APP-{school_code}-{random.randint(10000, 99999)}"
        while StudentApplication.objects.filter(application_number=app_number).exists():
            app_number = f"APP-{school_code}-{random.randint(10000, 99999)}"

        StudentApplication.objects.create(
            school=school,
            application_number=app_number,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            gender=gender,
            grade_level=int(grade_level),
            previous_school=previous_school or None,
            status=ApplicationStatus.PENDING,
        )
        messages.success(request, f"Application submitted! Your application number is: {app_number}")
        return redirect(f'/admission/apply/status/?app_number={app_number}')

    return render(request, 'students/public_admission.html')


def public_admission_form_redirect(request):
    """Redirect after successful submission to avoid re-POST on refresh."""
    return render(request, 'students/public_admission.html')


def application_status_view(request):
    """
    Public application status check — no login required.
    Applicant enters their application number to see status.
    """
    app_number = request.GET.get('app_number', '').strip()
    application = None

    if app_number:
        from apps.students.models import StudentApplication
        try:
            application = StudentApplication.objects.get(application_number=app_number)
        except StudentApplication.DoesNotExist:
            messages.error(request, f"No application found with number '{app_number}'.")

    return render(request, 'students/application_status.html', {
        'application': application,
        'app_number': app_number,
    })
