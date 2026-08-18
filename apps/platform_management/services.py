from django.utils import timezone
from apps.tenants.models import School, SchoolStatus
from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus
from apps.audit.services import AuditService
from .models import PlatformAuditLog

class SchoolStatusService:
    @staticmethod
    def _log_platform_action(actor, action, target_school, reason, before_state, after_state, severity='INFO'):
        PlatformAuditLog.objects.create(
            actor=actor,
            action=action,
            target_object=f"School: {target_school.name}",
            target_school=target_school,
            reason=reason,
            before_state=before_state,
            after_state=after_state,
            severity=severity
        )
        AuditService.log_action(
            school=target_school,
            user=actor, 
            action=action, 
            after_val={'details': f"Platform action on {target_school.name}: {reason}"}
        )

    @classmethod
    def suspend_school(cls, school, actor, reason):
        before_state = {'status': school.status, 'is_active': school.is_active}
        
        school.status = SchoolStatus.SUSPENDED
        school.is_active = False
        school.save()

        # Mark active subscriptions as suspended
        SchoolSubscription.objects.filter(
            school=school, 
            status=SubscriptionStatus.ACTIVE
        ).update(status=SubscriptionStatus.SUSPENDED)
        
        after_state = {'status': school.status, 'is_active': school.is_active}
        cls._log_platform_action(
            actor, 'SUSPEND_SCHOOL', school, reason, before_state, after_state, severity='HIGH'
        )
        return True

    @classmethod
    def activate_school(cls, school, actor, reason):
        before_state = {'status': school.status, 'is_active': school.is_active}
        
        school.status = SchoolStatus.ACTIVE
        school.is_active = True
        school.save()

        # Re-activate suspended subscriptions
        SchoolSubscription.objects.filter(
            school=school, 
            status=SubscriptionStatus.SUSPENDED
        ).update(status=SubscriptionStatus.ACTIVE)
        
        after_state = {'status': school.status, 'is_active': school.is_active}
        cls._log_platform_action(
            actor, 'ACTIVATE_SCHOOL', school, reason, before_state, after_state, severity='INFO'
        )
        return True

    @classmethod
    def archive_school(cls, school, actor, reason):
        before_state = {'status': school.status, 'is_active': school.is_active}
        
        school.status = SchoolStatus.ARCHIVED
        school.is_active = False
        school.save()

        # Cancel active/suspended subscriptions
        SchoolSubscription.objects.filter(
            school=school, 
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.SUSPENDED]
        ).update(status=SubscriptionStatus.CANCELLED)
        
        after_state = {'status': school.status, 'is_active': school.is_active}
        cls._log_platform_action(
            actor, 'ARCHIVE_SCHOOL', school, reason, before_state, after_state, severity='CRITICAL'
        )
        return True

class SchoolContextService:
    SESSION_KEY = 'active_school_context_id'

    @classmethod
    def enter_school_context(cls, request, school):
        previous_context_id = request.session.get(cls.SESSION_KEY)
        
        request.session[cls.SESSION_KEY] = str(school.id)
        
        if previous_context_id and previous_context_id != str(school.id):
            action = 'SCHOOL_CONTEXT_SWITCHED'
            previous_school = School.objects.filter(id=previous_context_id).first()
            before_state = {'context': str(previous_school.id) if previous_school else None}
        else:
            action = 'SCHOOL_CONTEXT_ENTERED'
            before_state = {'context': 'PLATFORM_CONTEXT'}
        
        PlatformAuditLog.objects.create(
            actor=request.user,
            action=action,
            target_object=f"Context: {school.name}",
            target_school=school,
            reason="Super Admin entered school context",
            before_state=before_state,
            after_state={'context': str(school.id)},
            severity='INFO',
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        return True

    @classmethod
    def exit_school_context(cls, request):
        active_school_id = request.session.pop(cls.SESSION_KEY, None)
        if active_school_id:
            school = School.objects.filter(id=active_school_id).first()
            PlatformAuditLog.objects.create(
                actor=request.user,
                action='SCHOOL_CONTEXT_EXITED',
                target_object=f"Context: {school.name}" if school else "Context: Unknown",
                target_school=school,
                reason="Super Admin exited school context",
                before_state={'context': active_school_id},
                after_state={'context': 'PLATFORM_CONTEXT'},
                severity='INFO',
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
        return True

    @classmethod
    def get_active_school(cls, request):
        if not hasattr(request, 'session'):
            return None
            
        active_school_id = request.session.get(cls.SESSION_KEY)
        if not active_school_id:
            return None
            
        try:
            # We must validate it exists
            return School.objects.get(id=active_school_id)
        except (School.DoesNotExist, ValueError):
            # Invalid ID in session, clean it up
            request.session.pop(cls.SESSION_KEY, None)
            return None

    @classmethod
    def is_in_school_context(cls, request):
        return bool(cls.get_active_school(request))
