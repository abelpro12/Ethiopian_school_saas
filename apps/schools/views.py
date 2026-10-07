import datetime
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Count, Avg, Q, Max
from django.views.decorators.csrf import csrf_exempt

from apps.tenants.models import School, SchoolStatus
from apps.accounts.models import User, UserRole
from apps.academics.models import AcademicYear, AcademicPeriod, Grade, Stream, Section, Subject, TimetableSlot, SchoolEvent, EventType, TargetAudience
from apps.students.models import StudentProfile, StudentStatus, StudentDemographics
from apps.parents.models import ParentProfile, GuardianRelationship
from apps.teachers.models import (
    TeacherProfile, TeacherAssignment, StaffProfile, StaffPosition,
    StaffEmploymentStatus, StaffDocument, StaffDocumentType, StaffLeaveRequest, LeaveType, LeaveRequestStatus
)
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.attendance.models import AttendanceRecord, AttendanceStatus, StaffAttendanceRecord, StaffAttendanceStatus
from apps.attendance.services import StaffLeaveService
from apps.assessments.models import StudentMark, AssessmentComponent, MarkStatus, StudentConduct, ConductGrade
from apps.grading.services import GradeService
from apps.rankings.services import RankingService
from apps.finance.models import FeeCategory, StudentInvoice, InvoiceStatus, Payment, PaymentStatus
from apps.payments.services import ChapaService
from apps.subscriptions.models import SubscriptionPlan, SchoolSubscription, SubscriptionStatus, TenantUsageMeter
from apps.subscriptions.services import SubscriptionService
from apps.communication.models import Announcement
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.teachers.services import HomeroomService
from apps.reports.services import EthiopianEducationReportingService
from utils.photo_processor import PhotoProcessingService
from apps.platform_management.decorators import school_context_required


from apps.schools.models import AdministrativeHierarchy, SchoolSetting, SchoolNews, SchoolGallery, SchoolContactMessage



def get_user_dashboard_redirect(user):
    """Centralized role-based dashboard router for all 10 system user roles."""
    if not user or not user.is_authenticated:
        return redirect('login')

    role = getattr(user, 'role', None)
    if role == UserRole.SUPER_ADMIN or getattr(user, 'is_superuser', False):
        return redirect('platform:dashboard')
    elif role in [UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        return redirect('admin_dashboard')
    elif role == UserRole.ACCOUNTANT:
        return redirect('finance:dashboard')
    elif role == UserRole.HR_MANAGER:
        return redirect('hr:dashboard')
    elif role == UserRole.LIBRARIAN:
        return redirect('library:dashboard')
    elif role == UserRole.TEACHER:
        return redirect('teacher_portal')
    elif role == UserRole.PARENT:
        return redirect('parent_portal')
    elif role == UserRole.STUDENT:
        return redirect('student_portal')
    return redirect('admin_dashboard')


def index_view(request):
    """Routing landing page based on authentication and user role."""
    if not request.user.is_authenticated:
        return seattle_academy_website_view(request)
    return get_user_dashboard_redirect(request.user)



def seattle_academy_website_view(request):
    """Official public homepage website for Seattle Academy."""
    school = School.objects.filter(Q(code='SEA') | Q(code='SEATTLE') | Q(name__icontains='SEATTLE')).first()
    
    if school:
        # Seed initial news items if none exist
        if not SchoolNews.objects.filter(school=school).exists():
            SchoolNews.objects.create(
                school=school,
                title="Ethiopian AI for Good 2025 Robotics Team Arrives in Geneva & Takes 5th Place Globally!!",
                category="International STEM",
                badge_text="🏆 5th Place Globally",
                location="Geneva Airport, Switzerland",
                content="Ethiopian AI for Good 2025 Robotics Teams arrived in Geneva for the ITU AI for Good Event — co-organized by the Ministry of Innovation and Technology (MInT) and Seattle Academy Ethiopia. Competing against top international teams, our team proudly took 5th place globally!",
                image_url="images/news_geneva_robotics_2025.jpg",
                is_published=True
            )
            SchoolNews.objects.create(
                school=school,
                title="Science Fair 2024 (WINNER IN ADDIS ABABA)",
                category="Regional Champion",
                badge_text="🥇 Winner in Addis Ababa",
                location="Addis Ababa, Ethiopia",
                content="Seattle Academy students secured 1st Place in the Addis Ababa Regional Science & Technology Fair 2024! Our students were awarded the championship trophy and honors for outstanding scientific research and innovation.",
                image_url="images/news_science_fair_2024.png",
                is_published=True
            )
        
        # Seed initial gallery items if none exist
        if not SchoolGallery.objects.filter(school=school).exists():
            SchoolGallery.objects.create(
                school=school,
                title="Students at Science Museum Showcase 2024",
                caption="Seattle Academy students presenting mind-blowing innovative STEM projects at the Ethiopian Science Museum (Addis Ababa, 2024)",
                category="Science Museum & Innovations",
                image_url="images/science_museum_innovators_2024.png"
            )
            SchoolGallery.objects.create(
                school=school,
                title="ITU AI for Good Global Summit 2025",
                caption="Geneva Robotics Team 2025 — 5th Place Globally",
                category="Global Competitions",
                image_url="images/news_geneva_robotics_2025.jpg"
            )
            SchoolGallery.objects.create(
                school=school,
                title="Science Fair 2024 Champions",
                caption="Science Fair 2024 Winners in Addis Ababa",
                category="Science Fairs",
                image_url="images/news_science_fair_2024.png"
            )


        # Only show news items selected for main/home page display, respecting custom order sequence
        news_list = SchoolNews.objects.filter(school=school, is_published=True, is_featured=True).order_by('order', '-created_at')
        # Only show gallery items selected for main/home page display, respecting custom order sequence
        gallery_list = SchoolGallery.objects.filter(school=school, is_featured=True).order_by('order', '-created_at')
    else:
        news_list = []
        gallery_list = []

    return render(request, 'public/seattle_academy_home.html', {
        'news_list': news_list,
        'gallery_list': gallery_list,
        'school': school
    })


def seattle_academy_news_gallery_view(request):
    """Dedicated standalone News, Events & Gallery page for Seattle Academy."""
    school = School.objects.filter(Q(code='SEA') | Q(code='SEATTLE') | Q(name__icontains='SEATTLE')).first()
    
    if school:
        # Full news page shows all published articles in custom order sequence
        news_list = SchoolNews.objects.filter(school=school, is_published=True).order_by('order', '-created_at')
        # Full gallery page shows all uploaded items in custom order sequence
        gallery_list = SchoolGallery.objects.filter(school=school).order_by('order', '-created_at')
    else:
        news_list = []
        gallery_list = []


    return render(request, 'public/seattle_academy_news_gallery.html', {
        'news_list': news_list,
        'gallery_list': gallery_list,
        'school': school
    })


def seattle_academy_about_view(request):
    """Dedicated About Us page for Seattle Academy."""
    school = School.objects.filter(Q(code='SEA') | Q(code='SEATTLE') | Q(name__icontains='SEATTLE')).first()
    return render(request, 'public/seattle_academy_about.html', {
        'school': school
    })


@csrf_exempt

def seattle_academy_contact_api(request):
    """API endpoint to receive and store public website contact form messages."""
    if request.method == 'POST':
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST

            sender_name = data.get('sender_name') or data.get('name') or ''
            phone_number = data.get('phone_number') or data.get('phone') or ''
            email = data.get('email') or ''
            subject = data.get('subject') or 'General Inquiry'
            message_text = data.get('message') or ''

            if not sender_name or not phone_number or not message_text:
                return JsonResponse({'success': False, 'error': 'Name, phone number, and message text are required.'}, status=400)

            school = School.objects.filter(code='SEA').first() or School.objects.filter(code='SEATTLE').first() or School.objects.first()

            msg = SchoolContactMessage.objects.create(
                school=school,
                sender_name=sender_name,
                phone_number=phone_number,
                email=email,
                subject=subject,
                message=message_text
            )

            return JsonResponse({
                'success': True,
                'message': 'Thank you! Your message has been sent directly to the Seattle Academy administration inbox.',
                'id': msg.id
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)


@login_required
def manage_contact_messages_view(request):
    """Admin view to inspect, manage, and mark incoming website contact messages."""
    school = getattr(request, 'school', None)
    if not school and hasattr(request.user, 'school'):
        school = request.user.school

    if request.method == 'POST':
        action = request.POST.get('action')
        msg_id = request.POST.get('message_id')
        msg = get_object_or_404(SchoolContactMessage, id=msg_id, school=school) if msg_id else None

        if action == 'mark_read' and msg:
            msg.is_read = True
            msg.save()
            messages.success(request, f"Message from '{msg.sender_name}' marked as read.")
        elif action == 'delete' and msg:
            sender = msg.sender_name
            msg.delete()
            messages.success(request, f"Message from '{sender}' deleted successfully.")
        return redirect('manage_contact_messages')

    contact_messages = SchoolContactMessage.objects.filter(school=school) if school else SchoolContactMessage.objects.all()
    unread_count = contact_messages.filter(is_read=False).count()

    return render(request, 'schools/manage_contact_messages.html', {
        'contact_messages': contact_messages,
        'unread_count': unread_count,
        'school': school
    })





@login_required
@school_context_required
def manage_news_view(request):
    """Admin dashboard page to post, reorder, and manage school news & announcements."""
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Permission denied.")
        return redirect('admin_dashboard')

    school = getattr(request, 'school', None) or request.user.school

    if request.method == 'POST':
        is_json = request.content_type == 'application/json'
        payload = {}
        if is_json:
            try:
                payload = json.loads(request.body)
            except Exception:
                payload = {}

        action = payload.get('action') if is_json else request.POST.get('action')

        if action == 'create_news':
            title = request.POST.get('title')
            category = request.POST.get('category', 'General')
            badge_text = request.POST.get('badge_text', '')
            location = request.POST.get('location', '')
            content = request.POST.get('content', '')
            image = request.FILES.get('image')
            is_featured = request.POST.get('is_featured') in ['on', 'true', '1', True]

            max_order = SchoolNews.objects.filter(school=school).aggregate(Max('order'))['order__max'] or 0

            SchoolNews.objects.create(
                school=school,
                title=title,
                category=category,
                badge_text=badge_text,
                location=location,
                content=content,
                image=image,
                is_published=True,
                is_featured=is_featured,
                order=max_order + 1
            )
            messages.success(request, f"News article '{title}' published successfully!")
            return redirect('manage_news')

        elif action == 'edit_news':
            item_id = request.POST.get('news_id')
            item = get_object_or_404(SchoolNews, id=item_id, school=school)
            item.title = request.POST.get('title', item.title).strip()
            item.category = request.POST.get('category', item.category).strip()
            item.badge_text = request.POST.get('badge_text', '').strip()
            item.location = request.POST.get('location', '').strip()
            item.content = request.POST.get('content', item.content).strip()
            item.is_featured = request.POST.get('is_featured') in ['on', 'true', '1', True]
            if 'image' in request.FILES and request.FILES['image']:
                item.image = request.FILES['image']
            item.save()
            messages.success(request, f"News article '{item.title}' updated successfully!")
            return redirect('manage_news')

        elif action == 'toggle_featured':
            item_id = payload.get('news_id') if is_json else request.POST.get('news_id')
            item = get_object_or_404(SchoolNews, id=item_id, school=school)
            item.is_featured = not item.is_featured
            item.save(update_fields=['is_featured'])

            if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'ok',
                    'is_featured': item.is_featured,
                    'title': item.title,
                    'news_id': item.id,
                    'message': f"'{item.title}' is now {'shown on' if item.is_featured else 'hidden from'} the main home page."
                })

            messages.success(request, f"'{item.title}' is now {'shown on' if item.is_featured else 'hidden from'} the main home page.")
            return redirect('manage_news')

        elif action == 'reorder_news':
            order_ids = payload.get('order_ids') if is_json else request.POST.get('order_ids', '').split(',')
            if not order_ids:
                order_ids = request.POST.getlist('order_ids')

            if order_ids:
                for idx, nid in enumerate(order_ids, start=1):
                    try:
                        nid_int = int(str(nid).strip())
                        SchoolNews.objects.filter(id=nid_int, school=school).update(order=idx)
                    except (ValueError, TypeError):
                        continue

            if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'message': 'News order updated successfully.'})

            messages.success(request, "News article display order updated successfully.")
            return redirect('manage_news')

        elif action in ['move_up', 'move_down']:
            item_id = request.POST.get('news_id')
            item = get_object_or_404(SchoolNews, id=item_id, school=school)
            all_items = list(SchoolNews.objects.filter(school=school).order_by('order', '-created_at'))

            try:
                curr_idx = next(i for i, n in enumerate(all_items) if n.id == item.id)
                target_idx = curr_idx - 1 if action == 'move_up' else curr_idx + 1
                if 0 <= target_idx < len(all_items):
                    all_items[curr_idx], all_items[target_idx] = all_items[target_idx], all_items[curr_idx]
                    for idx, n in enumerate(all_items, start=1):
                        n.order = idx
                        n.save(update_fields=['order'])
                    messages.success(request, f"Moved '{item.title}' {'up' if action == 'move_up' else 'down'} in order.")
            except Exception:
                pass

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok'})
            return redirect('manage_news')

        elif action == 'delete_news':
            item_id = request.POST.get('news_id')
            item = get_object_or_404(SchoolNews, id=item_id, school=school)
            title = item.title
            item.delete()

            for idx, n in enumerate(SchoolNews.objects.filter(school=school).order_by('order', '-created_at'), start=1):
                n.order = idx
                n.save(update_fields=['order'])

            messages.success(request, f"News article '{title}' deleted.")
            return redirect('manage_news')

    news_items = SchoolNews.objects.filter(school=school).order_by('order', '-created_at')
    total_count = news_items.count()
    featured_count = news_items.filter(is_featured=True).count()
    hidden_count = total_count - featured_count

    return render(request, 'schools/manage_news.html', {
        'news_items': news_items,
        'total_count': total_count,
        'featured_count': featured_count,
        'hidden_count': hidden_count,
        'school': school
    })


@login_required
@school_context_required
def manage_gallery_view(request):
    """Admin dashboard page to upload, reorder, and manage school photo gallery."""
    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]:
        messages.error(request, "Permission denied.")
        return redirect('admin_dashboard')

    school = getattr(request, 'school', None) or request.user.school

    if request.method == 'POST':
        # Detect JSON payload from AJAX requests
        is_json = request.content_type == 'application/json'
        payload = {}
        if is_json:
            try:
                payload = json.loads(request.body)
            except Exception:
                payload = {}

        action = payload.get('action') if is_json else request.POST.get('action')

        if action == 'create_gallery':
            title = request.POST.get('title')
            caption = request.POST.get('caption', '')
            category = request.POST.get('category', 'Campus Life')
            image = request.FILES.get('image')
            # Checkbox: on if checked, False if unchecked
            is_featured = request.POST.get('is_featured') in ['on', 'true', '1', True]

            # Place newly uploaded item at the end of custom sequence
            max_order = SchoolGallery.objects.filter(school=school).aggregate(Max('order'))['order__max'] or 0

            SchoolGallery.objects.create(
                school=school,
                title=title,
                caption=caption,
                category=category,
                image=image,
                is_featured=is_featured,
                order=max_order + 1
            )
            messages.success(request, f"Gallery photo '{title}' uploaded successfully!")
            return redirect('manage_gallery')

        elif action == 'edit_gallery':
            item_id = request.POST.get('gallery_id')
            item = get_object_or_404(SchoolGallery, id=item_id, school=school)
            item.title = request.POST.get('title', item.title).strip()
            item.caption = request.POST.get('caption', '').strip()
            item.category = request.POST.get('category', item.category).strip()
            item.is_featured = request.POST.get('is_featured') in ['on', 'true', '1', True]
            if 'image' in request.FILES and request.FILES['image']:
                item.image = request.FILES['image']
            item.save()
            messages.success(request, f"Gallery item '{item.title}' updated successfully!")
            return redirect('manage_gallery')

        elif action == 'toggle_featured':
            item_id = payload.get('gallery_id') if is_json else request.POST.get('gallery_id')
            item = get_object_or_404(SchoolGallery, id=item_id, school=school)
            item.is_featured = not item.is_featured
            item.save(update_fields=['is_featured'])

            if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'ok',
                    'is_featured': item.is_featured,
                    'title': item.title,
                    'gallery_id': item.id,
                    'message': f"'{item.title}' is now {'shown on' if item.is_featured else 'hidden from'} the main home page."
                })

            messages.success(request, f"'{item.title}' is now {'shown on' if item.is_featured else 'hidden from'} the main home page.")
            return redirect('manage_gallery')

        elif action == 'reorder_gallery':
            order_ids = payload.get('order_ids') if is_json else request.POST.get('order_ids', '').split(',')
            if not order_ids:
                order_ids = request.POST.getlist('order_ids')

            if order_ids:
                for idx, gid in enumerate(order_ids, start=1):
                    try:
                        gid_int = int(str(gid).strip())
                        SchoolGallery.objects.filter(id=gid_int, school=school).update(order=idx)
                    except (ValueError, TypeError):
                        continue

            if is_json or request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok', 'message': 'Gallery order updated successfully.'})

            messages.success(request, "Gallery photo order updated successfully.")
            return redirect('manage_gallery')

        elif action in ['move_up', 'move_down']:
            item_id = request.POST.get('gallery_id')
            item = get_object_or_404(SchoolGallery, id=item_id, school=school)
            all_items = list(SchoolGallery.objects.filter(school=school).order_by('order', '-created_at'))

            try:
                curr_idx = next(i for i, g in enumerate(all_items) if g.id == item.id)
                target_idx = curr_idx - 1 if action == 'move_up' else curr_idx + 1
                if 0 <= target_idx < len(all_items):
                    # Swap positions in list and save new orders
                    all_items[curr_idx], all_items[target_idx] = all_items[target_idx], all_items[curr_idx]
                    for idx, g in enumerate(all_items, start=1):
                        g.order = idx
                        g.save(update_fields=['order'])
                    messages.success(request, f"Moved '{item.title}' {'up' if action == 'move_up' else 'down'} in order.")
            except Exception:
                pass

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok'})
            return redirect('manage_gallery')

        elif action == 'delete_gallery':
            item_id = request.POST.get('gallery_id')
            item = get_object_or_404(SchoolGallery, id=item_id, school=school)
            title = item.title
            item.delete()

            # Re-normalize remaining orders 1..N
            for idx, g in enumerate(SchoolGallery.objects.filter(school=school).order_by('order', '-created_at'), start=1):
                g.order = idx
                g.save(update_fields=['order'])

            messages.success(request, f"Gallery photo '{title}' deleted.")
            return redirect('manage_gallery')

    gallery_items = SchoolGallery.objects.filter(school=school).order_by('order', '-created_at')
    total_count = gallery_items.count()
    featured_count = gallery_items.filter(is_featured=True).count()
    hidden_count = total_count - featured_count

    return render(request, 'schools/manage_gallery.html', {
        'gallery_items': gallery_items,
        'total_count': total_count,
        'featured_count': featured_count,
        'hidden_count': hidden_count,
        'school': school
    })



def seattle_academy_login_view(request):
    """Dedicated portal login page for Seattle Academy."""
    if request.user.is_authenticated:
        return get_user_dashboard_redirect(request.user)
    res = render(request, 'auth/seattle_academy_login.html')
    res.set_cookie('last_tenant', 'seattle_academy', max_age=30*24*3600)
    return res




@login_required
@school_context_required
def admin_dashboard(request):
    """
    Comprehensive School Admin Dashboard with Students, Teachers, Non-Teaching Staff,
    Staff HR Documents, School Events Calendar, Staff Attendance & Leave Management.
    """
    school = getattr(request, 'school', None)
    if not school and request.user.school:
        school = request.user.school

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_student':
            SubscriptionService.check_student_limit(school)
            st_id = request.POST.get('student_id')
            fname = request.POST.get('first_name')
            mname = request.POST.get('middle_name', '')
            lname = request.POST.get('last_name')
            gender = request.POST.get('gender', 'M')
            sec_id = request.POST.get('section_id')
            
            parent_phone = request.POST.get('parent_phone', '')
            parent_relationship = request.POST.get('parent_relationship', 'Father')
            parent_name = request.POST.get('parent_name', '')

            # 1. Student User Account — generate username based on first name
            from apps.accounts.utils import generate_unique_username, get_default_role_password
            student_initial_pwd = get_default_role_password(UserRole.STUDENT)
            student_username = generate_unique_username(fname, lname, school=school)

            student_user = User.objects.create_user(
                username=student_username,
                school=school,
                role=UserRole.STUDENT,
                first_name=fname,
                last_name=lname
            )
            student_user.set_password(student_initial_pwd)
            student_user.must_change_password = True
            student_user.save()

            # 2. Student Profile
            student, _ = StudentProfile.objects.get_or_create(
                user=student_user,
                defaults={
                    'school': school,
                    'student_id': st_id,
                    'first_name': fname,
                    'middle_name': mname,
                    'last_name': lname,
                    'gender': gender
                }
            )
            student.school = school
            student.student_id = st_id
            student.first_name = fname
            student.middle_name = mname
            student.last_name = lname
            student.gender = gender
            student.save()

            # 3. Parent Linking / Account Creation
            parent_option = request.POST.get('parent_option', 'new')
            existing_parent_id = request.POST.get('existing_parent_id')
            parent_profile = None

            if parent_option == 'existing' and existing_parent_id:
                parent_profile = ParentProfile.objects.filter(id=existing_parent_id, school=school).first()

            if not parent_profile and parent_phone:
                phone_clean = parent_phone.strip()
                parent_profile = ParentProfile.objects.filter(school=school, phone=phone_clean).first()

            if parent_profile:
                GuardianRelationship.objects.get_or_create(
                    school=school,
                    parent=parent_profile,
                    student=student,
                    defaults={'is_primary': True}
                )
                parent_msg = f"Linked to existing parent family '{parent_profile.user.get_full_name() or parent_profile.user.username}' (Login Username: {parent_profile.user.username}). Both children are now under 1 login!"
            else:
                parent_first = parent_name or lname
                parent_last = "Guardian" if parent_name else "Parent"
                parent_username = generate_unique_username(parent_first, parent_last, school=school, prefix="p_")

                parent_user = User.objects.create_user(
                    username=parent_username,
                    school=school,
                    role=UserRole.PARENT,
                    first_name=parent_first,
                    last_name=parent_last
                )
                parent_initial_pwd = get_default_role_password(UserRole.PARENT)
                parent_user.set_password(parent_initial_pwd)
                parent_user.must_change_password = True
                parent_user.save()


                parent_profile, _ = ParentProfile.objects.get_or_create(
                    user=parent_user,
                    defaults={
                        'school': school,
                        'phone': parent_phone or '+251911000000',
                        'relationship': parent_relationship
                    }
                )
                GuardianRelationship.objects.get_or_create(
                    school=school,
                    parent=parent_profile,
                    student=student,
                    defaults={'is_primary': True}
                )
                parent_msg = f"Parent login username: {parent_user.username} | Password: {parent_initial_pwd} (must change on login)."

            # 4. Initial Enrollment
            if sec_id:
                sec = Section.objects.get(id=sec_id, school=school)
                active_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
                StudentEnrollment.objects.get_or_create(
                    school=school,
                    academic_year=active_ay,
                    student=student,
                    defaults={
                        'grade': sec.grade,
                        'stream': sec.stream,
                        'section': sec,
                        'status': EnrollmentStatus.ACTIVE
                    }
                )

            messages.success(
                request, 
                f"Successfully registered student {fname} {lname}! (Student Login Username: {student_user.username} | Initial Password: {student_initial_pwd}). {parent_msg}"
            )
            return redirect('admin_dashboard')

        elif action == 'add_teacher':
            SubscriptionService.check_teacher_limit(school)
            emp_id = request.POST.get('employee_id')
            fname = request.POST.get('first_name')
            lname = request.POST.get('last_name')
            spec = request.POST.get('specialization')

            from apps.accounts.utils import generate_unique_username
            teacher_username = generate_unique_username(fname, lname, school=school)

            user = User.objects.create_user(
                username=teacher_username,
                school=school,
                role=UserRole.TEACHER,
                first_name=fname,
                last_name=lname
            )
            user.set_password("teacher123")
            user.must_change_password = True
            user.save()

            TeacherProfile.objects.create(
                school=school,
                user=user,
                employee_id=emp_id,
                specialization=spec
            )
            messages.success(request, f"Teacher '{fname} {lname}' created successfully! (Username: '{teacher_username}', Default password: 'teacher123')")
            return redirect('admin_dashboard')

        elif action == 'add_staff':
            emp_id = request.POST.get('employee_id')
            fname = request.POST.get('first_name')
            lname = request.POST.get('last_name')
            dept = request.POST.get('department')
            pos = request.POST.get('position', StaffPosition.OTHER)

            role_map = {
                StaffPosition.REGISTRAR: UserRole.REGISTRAR,
                StaffPosition.ACCOUNTANT: UserRole.ACCOUNTANT,
                StaffPosition.PRINCIPAL: UserRole.PRINCIPAL,
                StaffPosition.VICE_PRINCIPAL: UserRole.PRINCIPAL,
                StaffPosition.LIBRARIAN: UserRole.LIBRARIAN,
            }
            assigned_role = role_map.get(pos, UserRole.SCHOOL_ADMIN)

            from apps.accounts.utils import generate_unique_username
            staff_username = generate_unique_username(fname, lname, school=school)

            user = User.objects.create_user(
                username=staff_username,
                school=school,
                role=assigned_role,
                first_name=fname,
                last_name=lname
            )
            user.set_password("staff123")
            user.must_change_password = True
            user.save()

            StaffProfile.objects.create(
                school=school,
                user=user,
                employee_id=emp_id,
                department=dept,
                position=pos,
                hire_date=datetime.date.today()
            )
            messages.success(request, f"Staff member '{fname} {lname}' ({pos}) created successfully!")
            return redirect('admin_dashboard')

        elif action == 'upload_staff_doc':
            staff_id = request.POST.get('staff_id')
            doc_type = request.POST.get('document_type', StaffDocumentType.EMPLOYMENT)
            title = request.POST.get('title')
            file_obj = request.FILES.get('file')

            staff = get_object_or_404(StaffProfile, id=staff_id, school=school)
            if file_obj:
                StaffDocument.objects.create(
                    school=school,
                    staff=staff,
                    document_type=doc_type,
                    title=title,
                    file=file_obj,
                    uploaded_by=request.user
                )
                messages.success(request, f"HR Document '{title}' uploaded for staff {staff.employee_id}!")
            return redirect('admin_dashboard')

        elif action == 'create_event':
            title = request.POST.get('title')
            evt_type = request.POST.get('event_type', EventType.SCHOOL_EVENT)
            audience = request.POST.get('target_audience', TargetAudience.ALL)
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date') or start_date

            ay = getattr(request, 'academic_year', AcademicYear.objects.filter(school=school, is_active=True).first())
            if ay and start_date:
                SchoolEvent.objects.create(
                    school=school,
                    academic_year=ay,
                    title=title,
                    event_type=evt_type,
                    target_audience=audience,
                    start_date=start_date,
                    end_date=end_date
                )
                messages.success(request, f"School event '{title}' created successfully!")
            return redirect('admin_dashboard')

        elif action == 'review_leave':
            req_id = request.POST.get('request_id')
            review_status = request.POST.get('review_status')
            rejection = request.POST.get('rejection_reason')

            leave_req = get_object_or_404(StaffLeaveRequest, id=req_id, school=school)
            if review_status == 'APPROVE':
                StaffLeaveService.approve_leave_request(leave_req, reviewer=request.user)
                messages.success(request, f"Leave request for {leave_req.staff_user.username} APPROVED!")
            elif review_status == 'REJECT':
                StaffLeaveService.reject_leave_request(leave_req, reviewer=request.user, rejection_reason=rejection)
                messages.warning(request, f"Leave request for {leave_req.staff_user.username} REJECTED!")
            return redirect('admin_dashboard')

        elif action == 'create_invoice':
            st_id = request.POST.get('student_id')
            title = request.POST.get('title', 'Tuition Fee')
            amount = Decimal(request.POST.get('amount', '5000.00'))

            student = get_object_or_404(StudentProfile, id=st_id, school=school)
            ay = getattr(request, 'academic_year', AcademicYear.objects.filter(school=school, is_active=True).first())
            inv_no = f"INV-{datetime.date.today().year}-{StudentInvoice.objects.filter(school=school).count() + 1:03d}"

            StudentInvoice.objects.create(
                school=school,
                student=student,
                academic_year=ay,
                invoice_number=inv_no,
                total_amount=amount,
                due_date=datetime.date.today() + datetime.timedelta(days=30),
                status=InvoiceStatus.UNPAID
            )
            messages.success(request, f"Invoice '{inv_no}' created for {student.full_name}.")
            return redirect('admin_dashboard')

        elif action == 'approve_marks':
            StudentMark.objects.filter(school=school, status=MarkStatus.SUBMITTED).update(status=MarkStatus.APPROVED)
            messages.success(request, "Submitted marks approved successfully!")
            return redirect('admin_dashboard')

        elif action == 'calculate_rankings':
            sec_id = request.POST.get('section_id')
            sec = get_object_or_404(Section, id=sec_id, school=school)
            sem = AcademicPeriod.objects.filter(school=school, is_current=True).first() or AcademicPeriod.objects.filter(school=school).first()
            if sem:
                RankingService.calculate_ranks_for_section(school, sec.academic_year, sem, sec)
                messages.success(request, f"Section rankings calculated for {sec.name}!")
            return redirect('admin_dashboard')

        elif action == 'reset_account_password':
            target_type = request.POST.get('target_type')
            student_id = request.POST.get('student_id')
            new_password = request.POST.get('new_password', '').strip()
            
            if new_password and student_id:
                student = get_object_or_404(StudentProfile, id=student_id, school=school)
                if target_type == 'STUDENT':
                    student.user.set_password(new_password)
                    student.user.must_change_password = True
                    student.user.save()
                    student.current_password_display = new_password
                    student.save()
                    messages.success(request, f"Student password updated to '{new_password}' for {student.full_name}.")
                elif target_type == 'PARENT':
                    parent = student.primary_guardian
                    if parent:
                        parent.user.set_password(new_password)
                        parent.user.must_change_password = True
                        parent.user.save()
                        parent.current_password_display = new_password
                        parent.save()
                        messages.success(request, f"Parent password updated to '{new_password}' for {student.full_name}'s guardian ({parent.user.username}).")
                    else:
                        messages.error(request, f"No parent profile linked to {student.full_name}.")
            return redirect('admin_dashboard')

    academic_years = AcademicYear.objects.filter(school=school)
    current_ay = getattr(request, 'academic_year', None) or academic_years.filter(is_active=True).first() or academic_years.first()

    grade_filter = request.GET.get('st_grade')
    section_filter = request.GET.get('st_section')

    students = StudentProfile.objects.filter(school=school).select_related('user').prefetch_related(
        'guardianships__parent__user', 'enrollments__grade', 'enrollments__section'
    ).order_by('first_name', 'middle_name', 'last_name')

    if grade_filter:
        students = students.filter(enrollments__grade_id=grade_filter)
    if section_filter:
        students = students.filter(enrollments__section_id=section_filter)

    if current_ay:
        teachers = TeacherProfile.objects.filter(school=school, assignments__academic_year=current_ay).distinct()
        sections = Section.objects.filter(school=school)
        invoices = StudentInvoice.objects.filter(school=school, academic_year=current_ay).order_by('-id')
        school_events = SchoolEvent.objects.filter(school=school, academic_year=current_ay).order_by('start_date')
        
        # Pending marks linked to current academic year
        pending_marks = StudentMark.objects.filter(
            school=school, 
            status=MarkStatus.SUBMITTED,
            enrollment__academic_year=current_ay
        ).count()
    else:
        teachers = TeacherProfile.objects.filter(school=school)
        sections = Section.objects.filter(school=school)
        invoices = StudentInvoice.objects.filter(school=school).order_by('-id')
        school_events = SchoolEvent.objects.filter(school=school).order_by('start_date')
        pending_marks = StudentMark.objects.filter(school=school, status=MarkStatus.SUBMITTED).count()

    staff_members = StaffProfile.objects.filter(school=school)
    staff_docs = StaffDocument.objects.filter(school=school).order_by('-uploaded_at')[:10]
    leave_requests = StaffLeaveRequest.objects.filter(school=school).order_by('-created_at')
    pending_leave_count = leave_requests.filter(status=LeaveRequestStatus.PENDING).count()
    
    pending_invoices = invoices.filter(status=InvoiceStatus.UNPAID).count()
    paid_invoices = invoices.filter(status=InvoiceStatus.PAID).count()
    
    # Revenue from invoices in the selected academic year
    total_revenue = Payment.objects.filter(
        school=school, 
        status=PaymentStatus.SUCCESS,
        invoice__in=invoices
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    # Attendance summary for overview chart
    today = datetime.date.today()
    week_start = today - datetime.timedelta(days=6)
    week_att = AttendanceRecord.objects.filter(school=school, date__gte=week_start)
    week_present = week_att.filter(status=AttendanceStatus.PRESENT).count()
    week_total = week_att.count()
    attendance_pct = round((week_present / max(1, week_total)) * 100, 1)

    # Enrollment trends (last 6 months)
    enrollment_months = []
    enrollment_counts = []
    for i in range(5, -1, -1):
        m_date = today.replace(day=1) - datetime.timedelta(days=30 * i)
        count = StudentProfile.objects.filter(school=school, created_at__year=m_date.year, created_at__month=m_date.month).count() if hasattr(StudentProfile, 'created_at') else 0
        enrollment_months.append(m_date.strftime('%b %Y'))
        enrollment_counts.append(count)

    # Standardized Report Preview
    moe_report = EthiopianEducationReportingService.generate_standardized_report(school, current_ay) if current_ay else {}

    existing_parents = ParentProfile.objects.filter(school=school).select_related('user').prefetch_related(
        'guardianships__student__enrollments__grade',
        'guardianships__student__enrollments__section'
    )
    suggested_student_id = StudentProfile.generate_next_student_id(school)
    suggested_teacher_id = TeacherProfile.generate_next_employee_id(school)
    suggested_staff_id = StaffProfile.generate_next_employee_id(school)

    return render(request, 'portals/admin_dashboard.html', {
        'school': school,
        'suggested_student_id': suggested_student_id,
        'suggested_teacher_id': suggested_teacher_id,
        'suggested_staff_id': suggested_staff_id,
        'total_students': students.count(),
        'total_teachers': teachers.count(),
        'total_staff': staff_members.count(),
        'total_invoices': invoices.count(),
        'total_revenue': total_revenue,
        'pending_invoices': pending_invoices,
        'paid_invoices': paid_invoices,
        'attendance_pct': attendance_pct,
        'pending_marks': pending_marks,
        'pending_leave_count': pending_leave_count,
        'students': students,
        'teachers': teachers,
        'staff_members': staff_members,
        'existing_parents': existing_parents,
        'staff_docs': staff_docs,
        'school_events': school_events,
        'leave_requests': leave_requests,
        'sections': sections,
        'grades': Grade.objects.filter(school=school).order_by('level', 'stream_type'),
        'invoices': invoices,
        'academic_years': academic_years,
        'current_ay': current_ay,
        'selected_st_grade': grade_filter,
        'selected_st_section': section_filter,
        'moe_report': moe_report,
        'enrollment_months_json': enrollment_months,
        'enrollment_counts_json': enrollment_counts,
    })


@login_required
def teacher_portal(request):
    """
    Teacher Portal with Homeroom Teacher Dashboard, Attendance, Mark Entry, and Leave Submission.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    teacher_id = request.GET.get('teacher_id')
    if teacher_id and getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL']:
        try:
            teacher = TeacherProfile.objects.get(id=teacher_id, school=school)
        except (TeacherProfile.DoesNotExist, ValueError):
            teacher = getattr(request.user, 'teacher_profile', None)
    else:
        teacher = getattr(request.user, 'teacher_profile', None)
        if not teacher and getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL']:
            teacher = TeacherProfile.objects.filter(school=school).first()

    current_ay = getattr(request, 'academic_year', None)

    if teacher:
        if current_ay:
            assignments = TeacherAssignment.objects.filter(school=school, teacher=teacher, academic_year=current_ay)
        else:
            assignments = TeacherAssignment.objects.filter(school=school, teacher=teacher, academic_year__is_active=True)
    else:
        assignments = TeacherAssignment.objects.none()

    selected_section_id = request.GET.get('section_id') or (assignments.first().section.id if assignments and assignments.exists() else None)
    
    selected_section = Section.objects.filter(id=selected_section_id, school=school).first() if selected_section_id else None

    students = []
    if selected_section and current_ay:
        enrollments = StudentEnrollment.objects.filter(school=school, academic_year=current_ay, section=selected_section, status=EnrollmentStatus.ACTIVE, student__isnull=False).select_related('student')
        students = [e.student for e in enrollments if getattr(e, 'student', None)]

    # Homeroom Dashboard Data
    homeroom_data = HomeroomService.get_homeroom_dashboard(teacher, current_ay) if teacher else {'has_homeroom': False}

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'take_attendance' and selected_section:
            today = datetime.date.today()
            for student in students:
                st_status = request.POST.get(f'att_{student.id}', AttendanceStatus.PRESENT)
                AttendanceRecord.objects.update_or_create(
                    school=school,
                    section=selected_section,
                    student=student,
                    date=today,
                    defaults={'status': st_status, 'recorded_by': request.user}
                )
            messages.success(request, f"Attendance recorded for {selected_section.name} on {today}!")
            return redirect(f"/teacher/?section_id={selected_section.id}")

        elif action == 'save_marks' and selected_section:
            subject_id = request.POST.get('subject_id')
            subject = get_object_or_404(Subject, id=subject_id, school=school)

            # Constraint Check: Homeroom teacher cannot edit marks for subjects they don't teach
            if teacher and not HomeroomService.can_teacher_edit_subject_marks(teacher, selected_section, subject):
                messages.error(request, f"Security Alert: You are not authorized to edit marks for {subject.name}.")
                return redirect(f"/teacher/?section_id={selected_section.id}")

            sem = AcademicPeriod.objects.filter(school=school, is_current=True).first() or AcademicPeriod.objects.filter(school=school).first()
            # Use the resolved current_ay (Section has no academic_year field)
            mark_ay = current_ay or AcademicYear.objects.filter(school=school, is_active=True).first()
            comp, _ = AssessmentComponent.objects.get_or_create(
                school=school,
                academic_year=mark_ay,
                period=sem,
                subject=subject,
                name="Final Assessment",
                defaults={'weight': Decimal('60.00'), 'max_marks': Decimal('60.00')}
            )

            for student in students:
                val_str = request.POST.get(f'mark_{student.id}', '0.0')
                try:
                    val = Decimal(val_str)
                    enrollment = StudentEnrollment.objects.get(school=school, student=student, section=selected_section)
                    StudentMark.objects.update_or_create(
                        school=school,
                        enrollment=enrollment,
                        assessment_component=comp,
                        defaults={'mark_value': val, 'status': MarkStatus.SUBMITTED, 'entered_by': request.user}
                    )
                except Exception:
                    pass

            messages.success(request, "Student marks saved and submitted for approval!")
            return redirect(f"/teacher/?section_id={selected_section.id}")

        elif action == 'submit_leave':
            ltype = request.POST.get('leave_type', LeaveType.ANNUAL)
            sdate = request.POST.get('start_date')
            edate = request.POST.get('end_date')
            reason = request.POST.get('reason')

            StaffLeaveRequest.objects.create(
                school=school,
                staff_user=request.user,
                leave_type=ltype,
                start_date=sdate,
                end_date=edate,
                reason=reason
            )
            messages.success(request, "Leave request submitted successfully for approval!")
            return redirect('/teacher/')

        elif action == 'record_conduct':
            st_id = request.POST.get('student_id')
            c_grade = request.POST.get('conduct_grade', ConductGrade.A)
            remarks = request.POST.get('remarks', '')

            student = get_object_or_404(StudentProfile, id=st_id, school=school)
            ay = selected_section.academic_year if selected_section else AcademicYear.objects.filter(school=school).first()
            sem = AcademicPeriod.objects.filter(school=school, is_current=True).first() or AcademicPeriod.objects.filter(school=school).first()
            enrollment = StudentEnrollment.objects.get(school=school, student=student, section=selected_section)

            StudentConduct.objects.update_or_create(
                school=school,
                enrollment=enrollment,
                academic_year=ay,
                period=sem,
                defaults={'grade': c_grade, 'remarks': remarks, 'recorded_by': request.user}
            )
            messages.success(request, f"Conduct recorded for {student.full_name}!")
            return redirect(f"/teacher/?section_id={selected_section.id}")

    my_leaves = StaffLeaveRequest.objects.filter(school=school, staff_user=request.user).order_by('-created_at')
    school_events = SchoolEvent.objects.filter(school=school, target_audience__in=[TargetAudience.ALL, TargetAudience.TEACHERS]).order_by('start_date')

    # Attendance summary for teacher's sections
    today_date = datetime.date.today()
    today_att = AttendanceRecord.objects.filter(school=school, date=today_date, section=selected_section) if selected_section else AttendanceRecord.objects.none()
    today_present = today_att.filter(status=AttendanceStatus.PRESENT).count()
    today_absent = today_att.filter(status=AttendanceStatus.ABSENT).count()

    # Subject marks for selected section
    section_marks = []
    if selected_section and current_ay:
        assignments_for_section = TeacherAssignment.objects.filter(school=school, teacher=teacher, section=selected_section, academic_year=current_ay) if teacher else []
        section_marks = StudentMark.objects.filter(
            school=school,
            enrollment__academic_year=current_ay,
            enrollment__section=selected_section,
            status__in=[MarkStatus.SUBMITTED, MarkStatus.APPROVED]
        ).select_related('assessment_component__subject', 'enrollment__student').order_by('-id')[:30]

    all_teachers = []
    if getattr(request.user, 'role', None) in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL']:
        all_teachers = TeacherProfile.objects.filter(school=school).select_related('user')

    return render(request, 'portals/teacher_portal.html', {
        'teacher': teacher,
        'all_teachers': all_teachers,
        'assignments': assignments,
        'selected_section': selected_section,
        'students': students,
        'homeroom_data': homeroom_data,
        'my_leaves': my_leaves,
        'school_events': school_events,
        'today_present': today_present,
        'today_absent': today_absent,
        'section_marks': section_marks,
        'leave_types': LeaveType,
        'conduct_grades': ConductGrade,
        'attendance_statuses': AttendanceStatus,
    })


@login_required
def parent_portal(request):
    """
    Parent Dashboard with child academic results, attendance logs, school events, and Chapa fee payments.
    """
    school = getattr(request, 'school', None)
    parent = getattr(request.user, 'parent_profile', None)
    guardianships = GuardianRelationship.objects.filter(school=school, parent=parent, student__isnull=False).select_related('student') if parent else []
    children = [g.student for g in guardianships if getattr(g, 'student', None)]

    current_ay = getattr(request, 'academic_year', None)
    
    child_summaries = []
    for child in children:
        att_records = AttendanceRecord.objects.filter(school=school, student=child)
        if current_ay and current_ay.gregorian_start_date and current_ay.gregorian_end_date:
            att_records = att_records.filter(
                date__gte=current_ay.gregorian_start_date,
                date__lte=current_ay.gregorian_end_date
            )
        total_days = att_records.count()
        present_days = att_records.filter(status=AttendanceStatus.PRESENT).count()
        att_pct = round((present_days / max(1, total_days)) * 100, 1)

        # Marks — only published/approved marks visible to parents
        child_marks = StudentMark.objects.filter(
            school=school,
            enrollment__student=child,
            status__in=[MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]
        ).select_related('assessment_component__subject')
        
        if current_ay:
            child_marks = child_marks.filter(enrollment__academic_year=current_ay)

        # Per-child invoices for Chapa payment
        child_invoices = StudentInvoice.objects.filter(school=school, student=child).order_by('-id')
        if current_ay:
            child_invoices = child_invoices.filter(academic_year=current_ay)

        child_summaries.append({
            'student': child,
            'att_pct': att_pct,
            'marks': child_marks,
            'invoices': child_invoices,
        })

    school_events = SchoolEvent.objects.filter(school=school, target_audience__in=[TargetAudience.ALL, TargetAudience.PARENTS]).order_by('start_date')

    return render(request, 'portals/parent_portal.html', {
        'parent': parent,
        'child_summaries': child_summaries,
        'school_events': school_events,
    })


@login_required
def student_portal(request):
    """
    Student Dashboard with personal marks, timetable, attendance history, school events, and report card download.
    """
    school = getattr(request, 'school', None)
    student = getattr(request.user, 'student_profile', None)

    current_ay = getattr(request, 'academic_year', None)

    enrollment_qs = StudentEnrollment.objects.filter(school=school, student=student)
    if current_ay:
        enrollment = enrollment_qs.filter(academic_year=current_ay).first()
    else:
        enrollment = enrollment_qs.filter(status=EnrollmentStatus.ACTIVE).first()

    timetable = TimetableSlot.objects.filter(school=school, section=enrollment.section).select_related('subject', 'teacher__user') if enrollment else []
    # Use 'academic_marks' to exactly match template variable name
    academic_marks = StudentMark.objects.filter(
        school=school,
        enrollment__student=student,
        status__in=[MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]
    ).select_related('assessment_component__subject') if student else []
    
    if student and current_ay:
        academic_marks = academic_marks.filter(enrollment__academic_year=current_ay)
        
    # Build unsliced queryset first so we can filter for counts
    attendance_qs = AttendanceRecord.objects.filter(school=school, student=student).order_by('-date') if student else AttendanceRecord.objects.none()
    if current_ay and current_ay.gregorian_start_date and current_ay.gregorian_end_date:
        attendance_qs = attendance_qs.filter(
            date__gte=current_ay.gregorian_start_date,
            date__lte=current_ay.gregorian_end_date
        )
    period = AcademicPeriod.objects.filter(school=school, is_current=True).first() or AcademicPeriod.objects.filter(school=school).first()
    school_events = SchoolEvent.objects.filter(school=school, target_audience__in=[TargetAudience.ALL, TargetAudience.STUDENTS]).order_by('start_date')
    if current_ay:
        school_events = school_events.filter(academic_year=current_ay)

    # Attendance percentage — must be computed on unsliced queryset
    total_days = attendance_qs.count()
    present_days = attendance_qs.filter(status=AttendanceStatus.PRESENT).count()
    attendance_pct = round((present_days / max(1, total_days)) * 100, 1)

    # Slice for display only after counts are done
    attendance = attendance_qs[:30]

    # Average score across all marks
    total_score = sum(float(m.mark_value or 0) for m in academic_marks)
    avg_score = round(total_score / max(1, academic_marks.count()), 1) if academic_marks else 0

    return render(request, 'portals/student_portal.html', {
        'student': student,
        'enrollment': enrollment,
        'timetable': timetable,
        'academic_marks': academic_marks,
        'attendance': attendance,
        'attendance_pct': attendance_pct,
        'avg_score': avg_score,
        'period': period,
        'school_events': school_events,
    })


# Def super_admin_dashboard was moved to platform_management

@csrf_exempt
def login_view(request):
    """Universal Login Page View for all user roles with explicit role routing."""
    login_source = request.POST.get('login_source') or ''
    referer = request.META.get('HTTP_REFERER', '')
    cookie_tenant = request.COOKIES.get('last_tenant', '')
    next_url = request.GET.get('next', '')
    portal_override = request.GET.get('portal', '') or request.GET.get('source', '') or request.GET.get('tenant', '')

    if portal_override.lower() in ['main', 'platform', 'generic', 'ethioschool']:
        is_seattle = False
    else:
        is_seattle = (
            login_source == 'seattle_academy' or
            'seattle-academy' in referer or
            cookie_tenant == 'seattle_academy' or
            'seattle' in next_url
        )

    template_name = 'auth/seattle_academy_login.html' if is_seattle else 'auth/login.html'

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Clear any prior active session if a new login attempt is submitted
        if request.user.is_authenticated:
            logout(request)

        client_ip = AuditService.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Block login for non-superadmin users if their school is suspended or inactive
            if user.role != UserRole.SUPER_ADMIN and not user.is_superuser:
                if user.school and (user.school.status == SchoolStatus.SUSPENDED or not user.school.is_active):
                    AuditService.log_login(
                        school=user.school,
                        username_attempted=username,
                        user=user,
                        status='BLOCKED',
                        ip_address=client_ip,
                        user_agent=user_agent,
                        failure_reason="School suspended or inactive"
                    )
                    messages.error(
                        request,
                        f"Access to '{user.school.name}' has been suspended. Please contact your school administrator or platform support."
                    )
                    res = render(request, template_name)
                    if is_seattle:
                        res.set_cookie('last_tenant', 'seattle_academy', max_age=30*24*3600)
                    else:
                        res.delete_cookie('last_tenant')
                    return res

            AuditService.log_login(
                school=user.school,
                username_attempted=username,
                user=user,
                status='SUCCESS',
                ip_address=client_ip,
                user_agent=user_agent
            )
            login(request, user)
            user_school_code = str(getattr(getattr(user, 'school', None), 'code', '')).upper()
            if is_seattle or user_school_code in ['SEA', 'SEATTLE']:
                request.session['login_source'] = 'seattle_academy'

            res = get_user_dashboard_redirect(user)
            if is_seattle or user_school_code in ['SEA', 'SEATTLE']:
                res.set_cookie('last_tenant', 'seattle_academy', max_age=30*24*3600)
            elif portal_override.lower() in ['main', 'platform', 'generic', 'ethioschool']:
                res.delete_cookie('last_tenant')
            return res

        else:
            AuditService.log_login(
                school=getattr(request, 'school', None),
                username_attempted=username or 'unknown',
                user=None,
                status='FAILED',
                ip_address=client_ip,
                user_agent=user_agent,
                failure_reason='Invalid username or password credentials'
            )
            messages.error(request, "Invalid username or password.")
            res = render(request, template_name)
            if is_seattle:
                res.set_cookie('last_tenant', 'seattle_academy', max_age=30*24*3600)
            else:
                res.delete_cookie('last_tenant')
            return res

    elif request.user.is_authenticated:
        return get_user_dashboard_redirect(request.user)

    res = render(request, template_name)
    if is_seattle:
        res.set_cookie('last_tenant', 'seattle_academy', max_age=30*24*3600)
    elif portal_override.lower() in ['main', 'platform', 'generic', 'ethioschool']:
        res.delete_cookie('last_tenant')
    return res







@login_required
def logout_view(request):
    """User Logout View with tenant-aware redirection."""
    user = request.user
    referer = request.META.get('HTTP_REFERER', '')
    session_source = request.session.get('login_source', '')
    school = getattr(request, 'school', None) or getattr(user, 'school', None)

    is_seattle = False
    if school:
        code = str(getattr(school, 'code', '')).upper()
        name = str(getattr(school, 'name', '')).upper()
        if code in ['SEA', 'SEATTLE'] or 'SEATTLE' in name:
            is_seattle = True

    if 'seattle-academy' in referer or 'seattle' in referer or session_source == 'seattle_academy':
        is_seattle = True

    logout(request)

    if is_seattle:
        return redirect('seattle_academy_login')
    return redirect('login')




@login_required
def initiate_chapa_payment_view(request, invoice_id):
    """Initiates Chapa payment for student invoice."""
    school = getattr(request, 'school', None)
    invoice = get_object_or_404(StudentInvoice, id=invoice_id, school=school)

    try:
        callback_url = request.build_absolute_uri('/payments/verify/')
        response_data = ChapaService.initialize_payment(
            school=school,
            invoice=invoice,
            user=request.user,
            amount=invoice.remaining_balance,
            callback_url=callback_url
        )
        checkout_url = response_data.get('checkout_url')
        if checkout_url:
            return redirect(checkout_url)
    except Exception as e:
        messages.error(request, f"Chapa Payment Error: {str(e)}")

    return redirect('parent_portal')


def health_check_view(request):
    return JsonResponse({'status': 'healthy', 'database': 'healthy', 'service': 'Ethiopian School SaaS'})


def readiness_check_view(request):
    return JsonResponse({'status': 'ready', 'database': 'connected', 'cache': 'operational'})


@login_required
def user_management_view(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in ['SUPER_ADMIN', 'SCHOOL_ADMIN', 'PRINCIPAL', 'REGISTRAR']:
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    current_role = request.GET.get('role', 'STUDENT')
    selected_grade_id = request.GET.get('grade')
    selected_section_id = request.GET.get('section')
    search_query = request.GET.get('search', '').strip()

    users_query = User.objects.filter(school=school, role=current_role)

    if search_query:
        from django.db.models import Q
        users_query = users_query.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(username__icontains=search_query)
        )

    current_ay = getattr(request, 'academic_year', None) or AcademicYear.objects.filter(school=school, is_active=True).first()
    selected_academic_status = request.GET.get('status', 'CURRENT')
    selected_ay_id = request.GET.get('ay')
    academic_years = AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date')

    filter_ay = None
    if selected_ay_id:
        filter_ay = AcademicYear.objects.filter(id=selected_ay_id, school=school).first()
    if not filter_ay:
        filter_ay = current_ay

    # Apply Grade, Section, & Status filters for STUDENTS
    if current_role == 'STUDENT':
        if selected_academic_status == 'CURRENT':
            if filter_ay and not filter_ay.is_active:
                # Past Academic Year context: Show all students who were enrolled in this past year
                past_enrolled_ids = StudentEnrollment.objects.filter(school=school, academic_year=filter_ay).values_list('student__user_id', flat=True)
                users_query = users_query.filter(id__in=past_enrolled_ids)
            else:
                # Active Academic Year context: Active in current_ay OR Promoted/Pending placement in current_ay
                active_ids = StudentEnrollment.objects.filter(school=school, academic_year=filter_ay, status=EnrollmentStatus.ACTIVE).values_list('student__user_id', flat=True)
                graduated_ids = StudentEnrollment.objects.filter(school=school, status=EnrollmentStatus.GRADUATED).values_list('student__user_id', flat=True)
                pending_ids = StudentEnrollment.objects.filter(school=school, status=EnrollmentStatus.PROMOTED).exclude(student__user_id__in=active_ids).exclude(student__user_id__in=graduated_ids).values_list('student__user_id', flat=True)
                allowed_ids = set(active_ids) | set(pending_ids)
                users_query = users_query.filter(id__in=allowed_ids)

        elif selected_academic_status == 'ENROLLED':
            enrolled_ids = StudentEnrollment.objects.filter(school=school, academic_year=filter_ay, status=EnrollmentStatus.ACTIVE).values_list('student__user_id', flat=True)
            users_query = users_query.filter(id__in=enrolled_ids)

        elif selected_academic_status == 'PENDING':
            active_ids = StudentEnrollment.objects.filter(school=school, academic_year=filter_ay, status=EnrollmentStatus.ACTIVE).values_list('student__user_id', flat=True)
            graduated_ids = StudentEnrollment.objects.filter(school=school, status=EnrollmentStatus.GRADUATED).values_list('student__user_id', flat=True)
            pending_ids = StudentEnrollment.objects.filter(school=school, status=EnrollmentStatus.PROMOTED).exclude(student__user_id__in=active_ids).exclude(student__user_id__in=graduated_ids).values_list('student__user_id', flat=True)
            users_query = users_query.filter(id__in=pending_ids)

        elif selected_academic_status == 'GRADUATED':
            graduated_ids = StudentEnrollment.objects.filter(school=school, status=EnrollmentStatus.GRADUATED)
            if filter_ay:
                graduated_ids = graduated_ids.filter(academic_year=filter_ay)
            users_query = users_query.filter(id__in=graduated_ids.values_list('student__user_id', flat=True))

        if selected_grade_id or selected_section_id:
            enrollments = StudentEnrollment.objects.filter(school=school)
            if filter_ay:
                enrollments = enrollments.filter(academic_year=filter_ay)
            if selected_grade_id:
                enrollments = enrollments.filter(grade_id=selected_grade_id)
            if selected_section_id:
                enrollments = enrollments.filter(section_id=selected_section_id)
                
            student_user_ids = enrollments.values_list('student__user_id', flat=True)
            users_query = users_query.filter(id__in=student_user_ids)

    # Sort Alphabetically by First Name, Last Name
    users = users_query.order_by('first_name', 'last_name', 'username')

    if current_role == 'STUDENT':
        from django.db.models import Prefetch, Case, When, Value, IntegerField
        if filter_ay:
            enrollments_qs = StudentEnrollment.objects.filter(school=school).select_related(
                'grade', 'section', 'academic_year', 'stream'
            ).annotate(
                is_selected_year=Case(
                    When(academic_year_id=filter_ay.id, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField()
                )
            ).order_by('is_selected_year', '-academic_year__gregorian_start_date', '-id')
        else:
            enrollments_qs = StudentEnrollment.objects.filter(school=school).select_related(
                'grade', 'section', 'academic_year', 'stream'
            ).order_by('-academic_year__gregorian_start_date', '-id')

        users = users.prefetch_related(
            Prefetch(
                'student_profile__enrollments',
                queryset=enrollments_qs,
                to_attr='current_enrollment_list'
            )
        )
    elif current_role == 'PARENT':
        users = users.prefetch_related('parent_profile__guardianships__student')

    # Fetch Grades and Sections for dropdowns
    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school).order_by('name')
    if selected_grade_id:
        sections = sections.filter(grade_id=selected_grade_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        target_user_id = request.POST.get('user_id')
        
        try:
            target_user = User.objects.get(id=target_user_id, school=school)
            
            if action == 'toggle_active':
                if target_user.id == request.user.id:
                    messages.error(request, "You cannot deactivate your own account.")
                else:
                    target_user.is_active = not target_user.is_active
                    target_user.save()
                    status = "Reactivated" if target_user.is_active else "Suspended"
                    messages.success(request, f"User {target_user.username} has been {status}.")

            elif action in ['change_password', 'change_username']:
                is_self = target_user.id == request.user.id
                is_super = request.user.is_superuser or getattr(request.user, 'role', None) == 'SUPER_ADMIN'
                is_school_admin = getattr(request.user, 'role', None) == 'SCHOOL_ADMIN'

                # Security rules:
                # SCHOOL_ADMIN credentials can only be edited by themselves or SUPER_ADMIN.
                # PRINCIPAL credentials can be edited by SCHOOL_ADMIN, SUPER_ADMIN, or themselves.
                if target_user.role == 'SCHOOL_ADMIN' and not (is_self or is_super or is_school_admin):
                    messages.error(request, "Security Restriction: You do not have permission to modify School Admin credentials.")
                elif target_user.role == 'PRINCIPAL' and not (is_self or is_super or is_school_admin):
                    messages.error(request, "Security Restriction: You do not have permission to modify Principal credentials.")
                elif action == 'change_password':

                    new_password = request.POST.get('new_password')
                    if new_password and len(new_password) >= 6:
                        target_user.set_password(new_password)
                        if target_user.id != request.user.id:
                            target_user.must_change_password = True
                        target_user.save()
                        if hasattr(target_user, 'student_profile'):
                            target_user.student_profile.current_password_display = new_password
                            target_user.student_profile.save()
                        if hasattr(target_user, 'parent_profile'):
                            target_user.parent_profile.current_password_display = new_password
                            target_user.parent_profile.save()
                        messages.success(request, f"Password reset successfully for {target_user.username}. They will be prompted to set a new password on their next login.")
                    else:
                        messages.error(request, "Password must be at least 6 characters.")

                elif action == 'change_username':
                    new_username = request.POST.get('new_username', '').strip().lower()
                    if new_username and len(new_username) >= 3:
                        if User.objects.filter(username=new_username).exclude(id=target_user.id).exists():
                            messages.error(request, f"Username '{new_username}' is already taken. Please choose another username.")
                        else:
                            old_username = target_user.username
                            target_user.username = new_username
                            target_user.save()
                            messages.success(request, f"Username changed successfully from '{old_username}' to '{new_username}'.")
                    else:
                        messages.error(request, "Username must be at least 3 characters long.")

        except User.DoesNotExist:
            messages.error(request, "Target user not found.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

        # Maintain query params on redirect
        redirect_url = f"{request.path}?role={current_role}"
        if selected_grade_id: redirect_url += f"&grade={selected_grade_id}"
        if selected_section_id: redirect_url += f"&section={selected_section_id}"
        return redirect(redirect_url)

    # Role tab permissions: Registrars manage all roles except Admins
    if request.user.role == UserRole.REGISTRAR:
        roles_list = [
            r for r in UserRole.choices 
            if r[0] not in [UserRole.SCHOOL_ADMIN, UserRole.SUPER_ADMIN]
        ]
        allowed_roles = [r[0] for r in roles_list]
        if current_role not in allowed_roles:
            current_role = 'STUDENT'
    else:
        roles_list = [r for r in UserRole.choices if r[0] != UserRole.SUPER_ADMIN]

    return render(request, 'schools/user_management.html', {
        'users': users,
        'current_role': current_role,
        'grades': grades,
        'sections': sections,
        'selected_grade_id': selected_grade_id,
        'selected_section_id': selected_section_id,
        'search_query': search_query,
        'roles': roles_list,
        'academic_years': academic_years,
        'selected_academic_status': selected_academic_status,
        'selected_ay_id': selected_ay_id,
        'filter_ay': filter_ay,
    })


@login_required
def portal_selectors_api(request):
    """
    JSON API providing Grade, Section, Student, Teacher, and Parent choices for admin impersonation portal navigation.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    if not school:
        return JsonResponse({'error': 'No active school context'}, status=400)
    
    grade_id = request.GET.get('grade_id')
    section_id = request.GET.get('section_id')
    role = request.GET.get('role', 'STUDENT')

    from apps.academics.models import Grade, Section
    from apps.students.models import StudentProfile
    from apps.teachers.models import TeacherProfile
    from apps.parents.models import ParentProfile
    from apps.enrollment.models import StudentEnrollment

    current_ay = getattr(request, 'academic_year', None)

    grades = list(Grade.objects.filter(school=school).order_by('level').values('id', 'name', 'level'))
    
    sections_qs = Section.objects.filter(school=school)
    if grade_id:
        sections_qs = sections_qs.filter(grade_id=grade_id)
    sections = list(sections_qs.order_by('name').values('id', 'name', 'grade_id'))

    students = []
    teachers = []
    parents = []

    if role == 'STUDENT':
        enrollments = StudentEnrollment.objects.filter(school=school)
        if current_ay:
            enrollments = enrollments.filter(academic_year=current_ay)
        if grade_id:
            enrollments = enrollments.filter(grade_id=grade_id)
        if section_id:
            enrollments = enrollments.filter(section_id=section_id)
        
        enrollments = enrollments.select_related('student__user', 'section', 'grade')[:150]
        for e in enrollments:
            st = e.student
            user = st.user
            sec_name = e.section.name if e.section else 'No Section'
            grd_name = e.grade.name if e.grade else ''
            students.append({
                'id': st.id,
                'name': f"{user.get_full_name() or user.username} [{grd_name} - {sec_name}]",
                'section_id': e.section_id,
                'grade_id': e.grade_id
            })
    elif role == 'TEACHER':
        t_profiles = TeacherProfile.objects.filter(school=school).select_related('user')
        for t in t_profiles:
            teachers.append({
                'id': t.id,
                'name': f"{t.user.get_full_name() or t.user.username} ({t.department or 'Teacher'})"
            })
    elif role == 'PARENT':
        p_profiles = ParentProfile.objects.filter(school=school).select_related('user')[:150]
        for p in p_profiles:
            parents.append({
                'id': p.id,
                'name': f"{p.user.get_full_name() or p.user.username} ({p.phone or 'No phone'})"
            })

    return JsonResponse({
        'grades': grades,
        'sections': sections,
        'students': students,
        'teachers': teachers,
        'parents': parents
    })


@login_required
def centralized_search_api(request):
    """
    JSON API endpoint for Centralized Global Search (⌘K / Ctrl+K).
    Queries Students, Parents, Teachers, Non-Teaching Staff, Invoices, and Payments.
    Works for all roles; returns empty results gracefully when no school context is available.
    """
    school = getattr(request, 'school', None)
    if not school and hasattr(request.user, 'school'):
        school = request.user.school

    query = request.GET.get('q', '').strip()

    if not school or len(query) < 2:
        return JsonResponse({'query': query, 'results': {
            'students': [], 'parents': [], 'teachers': [],
            'staff': [], 'invoices': [], 'payments': []
        }})

    from apps.schools.search import CentralizedSearchEngine
    try:
        results = CentralizedSearchEngine.search(school, query)
    except Exception as e:
        return JsonResponse({'error': str(e), 'results': {}}, status=500)

    return JsonResponse({'query': query, 'results': results})


import io
import base64
import qrcode
from django.db.models import Q
from apps.academics.models import Grade
from apps.enrollment.models import StudentEnrollment
from apps.students.models import StudentProfile
from apps.teachers.models import StaffProfile, TeacherProfile
from apps.parents.models import ParentProfile

def generate_qr_base64(data):
    """Generates a base64 encoded PNG QR code."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=5,
            border=1,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64_str = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{b64_str}"
    except Exception:
        return ""


@login_required
@school_context_required
def id_card_generator_view(request):
    """
    Comprehensive ID Card Studio & Batch Printing Hub for Students, Staff, Teachers, and Parents.
    Includes scannable QR verification codes, custom school branding, and CR80 print dimensions.
    """
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None)
    role_filter = request.GET.get('role', 'all')  # all, student, staff, parent
    grade_id = request.GET.get('grade_id', '')
    search_q = request.GET.get('q', '').strip()
    is_print = request.GET.get('print', 'false') == 'true'

    domain_host = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'

    # Active Academic Year context
    from apps.academics.models import AcademicYear
    current_ay = AcademicYear.objects.filter(school=school, is_active=True).first() or AcademicYear.objects.filter(school=school).order_by('-gregorian_start_date').first()


    cards = []

    # 1. STUDENTS ID CARDS
    if role_filter in ['all', 'student']:
        enrollments = StudentEnrollment.objects.filter(school=school).select_related(
            'student__user', 'grade', 'section', 'academic_year'
        )
        if current_ay and not grade_id:
            current_enrs = enrollments.filter(academic_year=current_ay)
            if current_enrs.exists():
                enrollments = current_enrs

        if grade_id:
            enrollments = enrollments.filter(grade_id=grade_id)
        if search_q:
            enrollments = enrollments.filter(
                Q(student__user__first_name__icontains=search_q) |
                Q(student__user__last_name__icontains=search_q) |
                Q(student__user__username__icontains=search_q) |
                Q(student__student_id__icontains=search_q)
            )

        for en in enrollments[:100]:
            st = en.student
            usr = st.user
            verify_url = f"{scheme}://{domain_host}/verify-id/{usr.username}/"
            qr_b64 = generate_qr_base64(verify_url)

            grd_text = f"Grade {en.grade.level}" if en.grade else "Grade N/A"
            if en.grade and en.grade.stream_type != 'GEN':
                grd_text += f" ({en.grade.get_stream_type_display()})"
            sec_text = f"Sec {en.section.name}" if en.section else ""

            ay_display = en.academic_year.name if en.academic_year else ('Current Year' if current_ay else 'Active Session')

            parent_phone = ""
            g_rel = en.student.guardianships.select_related('parent').first()
            if g_rel and g_rel.parent:
                parent_phone = getattr(g_rel.parent, 'phone', '') or getattr(g_rel.parent.user, 'username', '')

            cards.append({
                'id_number': st.student_id or usr.username,
                'username': usr.username,
                'full_name': usr.get_full_name() or usr.username,
                'role_category': 'STUDENT',
                'badge_title': 'STUDENT IDENTIFICATION',
                'badge_bg': 'from-blue-700 via-indigo-800 to-slate-900',
                'accent_color': 'blue',
                'sub_title': f"{grd_text} • {sec_text}".strip(' •'),
                'meta_line_1': f"Current Year: {ay_display}",
                'meta_line_2': f"Emergency: {parent_phone or '+251 911 000 000'}",
                'photo_url': st.photo.url if hasattr(st, 'photo') and st.photo else (usr.profile_picture.url if hasattr(usr, 'profile_picture') and usr.profile_picture else None),
                'qr_code': qr_b64,
                'verify_url': verify_url,
            })

    # 2. STAFF & TEACHERS ID CARDS
    if role_filter in ['all', 'staff', 'teacher']:
        # Teachers
        teachers = TeacherProfile.objects.filter(school=school).select_related('user')
        if search_q:
            teachers = teachers.filter(
                Q(user__first_name__icontains=search_q) |
                Q(user__last_name__icontains=search_q) |
                Q(user__username__icontains=search_q) |
                Q(employee_id__icontains=search_q)
            )
        for t in teachers[:50]:
            usr = t.user
            verify_url = f"{scheme}://{domain_host}/verify-id/{usr.username}/"
            qr_b64 = generate_qr_base64(verify_url)

            cards.append({
                'id_number': t.employee_id or usr.username,
                'username': usr.username,
                'full_name': usr.get_full_name() or usr.username,
                'role_category': 'TEACHER',
                'badge_title': 'FACULTY / TEACHER',
                'badge_bg': 'from-purple-800 via-indigo-900 to-slate-950',
                'accent_color': 'purple',
                'sub_title': f"Teacher • {t.specialization or 'Academic Dept'}",
                'meta_line_1': f"Emp ID: {t.employee_id or usr.username}",
                'meta_line_2': f"Office: School Main Campus",
                'photo_url': usr.profile_picture.url if hasattr(usr, 'profile_picture') and usr.profile_picture else None,
                'qr_code': qr_b64,
                'verify_url': verify_url,
            })

        # Non-Teaching Staff (Principal, Registrar, Accountant, HR, Librarian, Admin)
        staff_members = StaffProfile.objects.filter(school=school).select_related('user')
        if search_q:
            staff_members = staff_members.filter(
                Q(user__first_name__icontains=search_q) |
                Q(user__last_name__icontains=search_q) |
                Q(user__username__icontains=search_q) |
                Q(employee_id__icontains=search_q)
            )
        for s in staff_members[:50]:
            usr = s.user
            verify_url = f"{scheme}://{domain_host}/verify-id/{usr.username}/"
            qr_b64 = generate_qr_base64(verify_url)

            cards.append({
                'id_number': s.employee_id or usr.username,
                'username': usr.username,
                'full_name': usr.get_full_name() or usr.username,
                'role_category': 'STAFF',
                'badge_title': f"STAFF • {s.get_position_display().upper()}",
                'badge_bg': 'from-slate-800 via-slate-900 to-slate-950',
                'accent_color': 'slate',
                'sub_title': f"{s.get_position_display()} ({s.department or 'Administration'})",
                'meta_line_1': f"Emp ID: {s.employee_id or usr.username}",
                'meta_line_2': f"Hired: {s.hire_date or 'Active Staff'}",
                'photo_url': usr.profile_picture.url if hasattr(usr, 'profile_picture') and usr.profile_picture else None,
                'qr_code': qr_b64,
                'verify_url': verify_url,
            })

    # 3. PARENTS / GUARDIANS ID CARDS
    if role_filter in ['all', 'parent']:
        parents = ParentProfile.objects.filter(school=school).select_related('user')
        if search_q:
            parents = parents.filter(
                Q(user__first_name__icontains=search_q) |
                Q(user__last_name__icontains=search_q) |
                Q(user__username__icontains=search_q) |
                Q(phone__icontains=search_q)
            )
        for p in parents[:50]:
            usr = p.user
            verify_url = f"{scheme}://{domain_host}/verify-id/{usr.username}/"
            qr_b64 = generate_qr_base64(verify_url)

            # Build detailed list of children with their active current grade
            linked_children = p.guardianships.select_related('student__user').all()
            children_data = []
            for g in linked_children:
                ch = g.student
                ch_user = ch.user
                ch_name = ch_user.get_full_name() or ch_user.username
                # Get student's current enrollment grade
                ch_en = StudentEnrollment.objects.filter(student=ch).select_related('grade', 'section').order_by('-academic_year__gregorian_start_date').first()
                if ch_en and ch_en.grade:
                    grd_str = f"Grade {ch_en.grade.level}"
                    if ch_en.grade.stream_type != 'GEN':
                        grd_str += f" {ch_en.grade.stream_type}"
                    ch_name += f" ({grd_str})"
                children_data.append(ch_name)

            rel_type = p.relationship or 'Guardian' # Father, Mother, Guardian
            children_names_str = ", ".join(children_data[:2])

            cards.append({
                'id_number': usr.username,
                'username': usr.username,
                'full_name': usr.get_full_name() or usr.username,
                'role_category': 'PARENT',
                'badge_title': f"{rel_type.upper()} / GUARDIAN CARD",
                'badge_bg': 'from-amber-600 via-orange-700 to-slate-900',
                'accent_color': 'amber',
                'sub_title': f"{rel_type} of: {children_names_str or 'Enrolled Student'}",
                'meta_line_1': f"Phone: {getattr(p, 'phone', 'On File')}",
                'meta_line_2': f"Access: School Campus Pass",
                'photo_url': usr.profile_picture.url if hasattr(usr, 'profile_picture') and usr.profile_picture else None,
                'qr_code': qr_b64,
                'verify_url': verify_url,
            })


    # 4. FILTER BY SELECTED CARDS (IF PRINT SELECTION APPLIED)
    selected_raw = request.GET.get('selected', '').strip()
    if selected_raw:
        selected_set = set(filter(None, selected_raw.split(',')))
        cards = [c for c in cards if c['username'] in selected_set or c['id_number'] in selected_set]

    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')

    template_name = 'schools/id_card_print.html' if is_print else 'schools/id_card_studio.html'
    return render(request, template_name, {
        'school': school,
        'cards': cards,
        'grades': grades,
        'role_filter': role_filter,
        'grade_id': grade_id,
        'search_q': search_q,
        'total_cards': len(cards),
    })


@login_required
@school_context_required
def upload_id_card_photo_view(request):
    """
    Uploads or updates the ID card photo for a student, teacher, staff, or parent.
    """
    from apps.accounts.models import User, UserRole
    if request.method == 'POST':
        username = request.POST.get('username')
        photo_file = request.FILES.get('photo_file')
        if username and photo_file:
            usr = User.objects.filter(username=username).first()
            if usr:
                usr.profile_picture = photo_file
                usr.save()

                if usr.role == UserRole.STUDENT:
                    st = StudentProfile.objects.filter(user=usr).first()
                    if st:
                        st.photo = photo_file
                        st.save()

                messages.success(request, f"Successfully updated photo for {usr.get_full_name() or usr.username}.")
            else:
                messages.error(request, "User record not found.")
        else:
            messages.error(request, "Please select an image file to upload.")

    return redirect('id_card_generator')



def verify_id_card_view(request, username):
    """
    Public QR Code Verification Endpoint.
    Displays valid/invalid status, tenant school seal, and identity credentials when scanned.
    """
    import datetime
    from apps.accounts.models import User, UserRole
    user = User.objects.filter(username=username).select_related('school').first()
    if not user:
        return render(request, 'schools/verify_id_result.html', {'is_valid': False, 'username': username})

    school = user.school
    role_display = user.get_role_display()

    detail_info = {}
    if user.role == UserRole.STUDENT:
        st = StudentProfile.objects.filter(user=user).first()
        en = StudentEnrollment.objects.filter(student=st).select_related('grade', 'section').first() if st else None
        detail_info['student_id'] = st.student_id if st else user.username
        detail_info['grade'] = f"Grade {en.grade.level}" if en and en.grade else 'N/A'
        detail_info['section'] = en.section.name if en and en.section else 'N/A'
    elif user.role == UserRole.TEACHER:
        tp = TeacherProfile.objects.filter(user=user).first()
        detail_info['employee_id'] = tp.employee_id if tp else user.username
        detail_info['specialization'] = tp.specialization if tp else 'Teacher'
    elif user.role in [UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.ACCOUNTANT, UserRole.HR_MANAGER, UserRole.LIBRARIAN]:
        sp = StaffProfile.objects.filter(user=user).first()
        detail_info['employee_id'] = sp.employee_id if sp else user.username
        detail_info['department'] = sp.department if sp else 'Staff'
    elif user.role == UserRole.PARENT:
        pp = ParentProfile.objects.filter(user=user).first()
        detail_info['phone'] = getattr(pp, 'phone', 'On File')

    return render(request, 'schools/verify_id_result.html', {
        'is_valid': True,
        'user_obj': user,
        'school': school,
        'role_display': role_display,
        'detail_info': detail_info,
        'verify_timestamp': datetime.datetime.now(),
    })



