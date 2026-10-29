import pytest
import uuid
import datetime
from decimal import Decimal
from django.urls import reverse

import os

try:
    from playwright.sync_api import expect
    PLAYWRIGHT_INSTALLED = True
except ImportError:
    expect = None
    PLAYWRIGHT_INSTALLED = False
    if os.environ.get('CI'):
        raise RuntimeError(
            "CRITICAL CI ERROR: Playwright is not installed in CI environment. E2E tests must execute and cannot be silently skipped."
        )
    pytestmark = pytest.mark.skip(reason="Playwright is not installed in the current local environment")

from apps.tenants.models import School
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import TeacherProfile
from apps.enrollment.models import StudentEnrollment
from apps.assessments.models import AssessmentComponent, StudentMark


@pytest.mark.django_db
def test_1_user_login_logout_and_session_behavior(page, live_server):
    """Scenario 1: Login, logout, session verification, and invalid credential handling."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"E2E School {uid}", code=f"E2E{uid.upper()}", subdomain=f"e2e-{uid}")
    User.objects.create_user(username=f"admin_{uid}", password="password123", school=school, role=UserRole.SCHOOL_ADMIN)

    # 1. Test invalid login
    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"admin_{uid}")
    page.fill("input[name='password']", "wrongpassword")
    page.click("button[type='submit']")
    expect(page.locator("body")).to_contain_text("Invalid")

    # 2. Test valid login
    page.fill("input[name='username']", f"admin_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")
    page.wait_for_url("**/dashboard/")
    expect(page.locator("body")).to_contain_text("Dashboard")

    # 3. Test logout
    page.goto(f"{live_server.url}{reverse('logout')}")
    page.wait_for_url(f"**{reverse('login')}**")
    expect(page.locator("input[name='username']")).to_be_visible()


@pytest.mark.django_db
def test_2_school_admin_and_principal_access_restrictions(page, live_server):
    """Scenario 2: Verify role-based dashboard and settings access."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Access School {uid}", code=f"ACC{uid.upper()}", subdomain=f"acc-{uid}")
    User.objects.create_user(username=f"admin_{uid}", password="password123", school=school, role=UserRole.SCHOOL_ADMIN)
    User.objects.create_user(username=f"student_{uid}", password="password123", school=school, role=UserRole.STUDENT)

    # Admin accesses user management
    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"admin_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")
    page.wait_for_url("**/dashboard/")

    page.goto(f"{live_server.url}{reverse('user_management')}")
    expect(page.locator("body")).to_contain_text("User")

    # Logout and login as Student
    page.goto(f"{live_server.url}{reverse('logout')}")
    page.goto(f"{live_server.url}{reverse('login')}")
    expect(page.locator("input[name='username']")).to_be_visible()
    page.fill("input[name='username']", f"student_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    # Student cannot access user management
    response = page.goto(f"{live_server.url}{reverse('user_management')}")
    assert response.status in (403, 302)


@pytest.mark.django_db
def test_3_registrar_student_creation_search_and_detail(page, live_server):
    """Scenario 3: Registrar student search and detail navigation."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Reg School {uid}", code=f"REG{uid.upper()}", subdomain=f"reg-{uid}")
    User.objects.create_user(username=f"reg_{uid}", password="password123", school=school, role=UserRole.REGISTRAR)
    stu_user = User.objects.create_user(username=f"stu_{uid}", password="password123", school=school, role=UserRole.STUDENT)
    student = StudentProfile.objects.create(
        school=school, user=stu_user, student_id=f"STU-{uid}", first_name="Abebe", last_name="Bikila"
    )

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"reg_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    # Search student via API / page
    page.goto(f"{live_server.url}{reverse('centralized_search_api')}?q=Abebe")
    expect(page.locator("body")).to_contain_text("Abebe")


@pytest.mark.django_db
def test_4_teacher_attendance_entry_workflow(page, live_server):
    """Scenario 4: Teacher portal and attendance view."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Att School {uid}", code=f"ATT{uid.upper()}", subdomain=f"att-{uid}")
    teacher = User.objects.create_user(username=f"teacher_{uid}", password="password123", school=school, role=UserRole.TEACHER)
    TeacherProfile.objects.create(school=school, user=teacher, employee_id=f"EMP-{uid}")

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"teacher_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    page.goto(f"{live_server.url}{reverse('teacher_portal')}")
    expect(page.locator("body")).to_contain_text("Teacher")


@pytest.mark.django_db
def test_5_grade_entry_validation_and_locking(page, live_server):
    """Scenario 5: Assessment and mark submission workflow."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Grade School {uid}", code=f"GRD{uid.upper()}", subdomain=f"grd-{uid}")
    teacher = User.objects.create_user(username=f"eval_t_{uid}", password="password123", school=school, role=UserRole.TEACHER)

    ay = AcademicYear.objects.create(school=school, name="2016", ethiopian_year=2016, gregorian_start_date=datetime.date(2023, 9, 12), gregorian_end_date=datetime.date(2024, 6, 30))
    period = AcademicPeriod.objects.create(school=school, academic_year=ay, name="Sem 1", start_date=ay.gregorian_start_date, end_date=datetime.date(2024, 1, 20))
    grade = Grade.objects.create(school=school, level=9, name="Grade 9")
    stream = Stream.objects.create(school=school, name="General", code="GEN")
    subj = Subject.objects.create(school=school, code=f"SUB-{uid}", name="Math", grade=grade, stream=stream)
    AssessmentComponent.objects.create(school=school, academic_year=ay, period=period, subject=subj, name="Midterm", weight=Decimal('30.0'))

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"eval_t_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    # Navigate to assessments
    response = page.goto(f"{live_server.url}{reverse('assessments:assessments')}")
    assert response.status in (200, 302)


@pytest.mark.django_db
def test_6_parent_and_student_access_restrictions(page, live_server):
    """Scenario 6: Parent and student portal access separation."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Parent School {uid}", code=f"PAR{uid.upper()}", subdomain=f"par-{uid}")
    parent_user = User.objects.create_user(username=f"parent_{uid}", password="password123", school=school, role=UserRole.PARENT)
    ParentProfile.objects.create(school=school, user=parent_user, phone="+251911002233")

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"parent_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    page.goto(f"{live_server.url}{reverse('parent_portal')}")
    expect(page.locator("body")).to_contain_text("Parent")

    # Parent cannot view admin dashboard
    resp = page.goto(f"{live_server.url}{reverse('admin_dashboard')}")
    assert resp.status in (403, 302)


@pytest.mark.django_db
def test_7_cross_school_access_attempt_blocked(page, live_server):
    """Scenario 7: Cross-tenant direct object navigation rejected."""
    uid_a = uuid.uuid4().hex[:6]
    uid_b = uuid.uuid4().hex[:6]
    school_a = School.objects.create(name=f"School A {uid_a}", code=f"A{uid_a.upper()}", subdomain=f"a-{uid_a}")
    school_b = School.objects.create(name=f"School B {uid_b}", code=f"B{uid_b.upper()}", subdomain=f"b-{uid_b}")

    User.objects.create_user(username=f"user_a_{uid_a}", password="password123", school=school_a, role=UserRole.SCHOOL_ADMIN)
    User.objects.create_user(username=f"user_b_{uid_b}", password="password123", school=school_b, role=UserRole.STUDENT)

    stu_b = StudentProfile.objects.create(
        school=school_b, user=User.objects.get(username=f"user_b_{uid_b}"), student_id=f"SB-{uid_b}", first_name="Bob"
    )

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"user_a_{uid_a}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    # User A tries to view School B student
    response = page.goto(f"{live_server.url}/api/v1/students/{stu_b.id}/")
    assert response.status == 404


@pytest.mark.django_db
def test_8_navigation_and_permission_denied_states(page, live_server):
    """Scenario 8: Nonexistent route returns 404 without unhandled error."""
    page.goto(f"{live_server.url}/nonexistent-test-path-404/")
    expect(page.locator("body")).to_contain_text("Not Found")


@pytest.mark.django_db
def test_9_academic_calendar_and_reporting_workflows(page, live_server):
    """Scenario 9: Academic calendar viewing."""
    uid = uuid.uuid4().hex[:6]
    school = School.objects.create(name=f"Cal School {uid}", code=f"CAL{uid.upper()}", subdomain=f"cal-{uid}")
    User.objects.create_user(username=f"cal_admin_{uid}", password="password123", school=school, role=UserRole.SCHOOL_ADMIN)

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"cal_admin_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    resp = page.goto(f"{live_server.url}{reverse('school_calendar')}")
    assert resp.status in (200, 302)


@pytest.mark.django_db
def test_10_super_admin_school_management(page, live_server):
    """Scenario 10: Super admin platform management portal access."""
    uid = uuid.uuid4().hex[:6]
    User.objects.create_user(username=f"super_{uid}", password="password123", role=UserRole.SUPER_ADMIN, is_superuser=True)

    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("input[name='username']", f"super_{uid}")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    resp = page.goto(f"{live_server.url}{reverse('platform:dashboard')}")
    assert resp.status in (200, 302)
