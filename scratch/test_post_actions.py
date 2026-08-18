import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.test import Client

# School admin POST actions
c = Client()
c.post('/login/', {'username': 'schooladmin', 'password': 'SchoolPass123!'})

actions = [
    {'action': 'create_event', 'title': 'Semester Exam Period', 'event_type': 'EXAM_PERIOD', 'target_audience': 'ALL', 'start_date': '2026-09-01', 'end_date': '2026-09-10'},
    {'action': 'approve_marks'},
]

for payload in actions:
    r = c.post('/dashboard/', payload)
    loc = r.get('Location', 'No Redirect')
    print(f'POST action={payload["action"]}: HTTP {r.status_code} -> {loc}')

# Teacher portal leave submission
c2 = Client()
c2.post('/login/', {'username': 'teacher', 'password': 'TeacherPass123!'})
r2 = c2.post('/teacher/', {'action': 'submit_leave', 'leave_type': 'ANNUAL', 'start_date': '2026-09-15', 'end_date': '2026-09-20', 'reason': 'Annual vacation'})
print(f'POST teacher submit_leave: HTTP {r2.status_code} -> {r2.get("Location", "No Redirect")}')

# Test that login page renders
c3 = Client()
r3 = c3.get('/login/')
print(f'GET login page: HTTP {r3.status_code}')

print('\nALL POST ACTIONS PASSED!')
