import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.test import Client

def test_login_redirects():
    roles = [
        ('superadmin', 'AdminPass123!', '/super-admin/'),
        ('schooladmin', 'SchoolPass123!', '/dashboard/'),
        ('teacher', 'TeacherPass123!', '/teacher/'),
        ('parent', 'ParentPass123!', '/parent/'),
        ('student', 'StudentPass123!', '/student/'),
    ]

    for username, password, expected_url in roles:
        c = Client()
        res = c.post('/login/', {'username': username, 'password': password}, follow=False)
        print(f"User: {username:15} | Status: {res.status_code} | Target URL: {res.url} | Expected: {expected_url}")
        assert res.url == expected_url, f"Expected {expected_url} for {username}, got {res.url}"

    print("\nALL 5 ROLES REDIRECT TO THEIR DISTINCT DEDICATED PORTALS 100% PERFECTLY!")

if __name__ == '__main__':
    test_login_redirects()
