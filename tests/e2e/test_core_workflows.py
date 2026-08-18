import pytest
from django.urls import reverse

try:
    from playwright.sync_api import expect
except ImportError:
    expect = None
    pytestmark = pytest.mark.skip(reason="Playwright is not installed in the current environment")

@pytest.mark.django_db
def test_user_login(page, live_server, client):
    """
    Test the basic login workflow using Playwright.
    """
    from apps.tenants.models import School
    from apps.accounts.models import User, UserRole

    # Setup demo user
    school = School.objects.create(name="QA Academy", code="QA-001", subdomain="qa")
    user = User.objects.create_user(username="qa_admin", password="password123", school=school, role=UserRole.SCHOOL_ADMIN)

    # Navigate to login
    page.goto(f"{live_server.url}/accounts/login/")
    
    # Fill login form
    page.fill("input[name='username']", "qa_admin")
    page.fill("input[name='password']", "password123")
    page.click("button[type='submit']")

    # Wait for dashboard redirect and verify
    page.wait_for_url("**/dashboard/")
    expect(page.locator("body")).to_contain_text("Dashboard")
