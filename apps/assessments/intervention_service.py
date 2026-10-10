import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth import get_user_model

User = get_user_model()

from apps.assessments.models import (
    AcademicIntervention, InterventionType, InterventionStatus,
    StudentMark, AssessmentComponent, GradingScale
)
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.academics.models import Subject, Grade, Section, AcademicYear, AcademicPeriod
from apps.communication.models import NotificationChannel
from apps.notifications.services import NotificationService as NotificationDispatcher
from apps.audit.services import AuditService

logger = logging.getLogger(__name__)


class AcademicInterventionService:
    """
    Automates detection of below-average academic performance (<60%),
    manages intervention workflows, triggers parent SMS alerts,
    and monitors follow-up performance recovery.
    """

    @classmethod
    def detect_below_average_students(
        cls,
        school,
        period: Optional[AcademicPeriod] = None,
        academic_year: Optional[AcademicYear] = None,
        grade_id: Optional[int] = None,
        section_id: Optional[int] = None,
        subject_id: Optional[int] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans all student marks to identify scores below the configured threshold (default 60%).
        Returns enriched records containing student info, subject, component, teacher, score,
        and existing intervention status.
        """
        # Resolve threshold from effective grading scale if not passed
        if threshold is None:
            scale = GradingScale.get_effective_scale(school)
            threshold = float(scale.below_average_threshold) if scale else 60.0

        marks_qs = StudentMark.objects.filter(
            school=school
        ).exclude(
            enrollment__status__in=[EnrollmentStatus.WITHDRAWN, EnrollmentStatus.TRANSFERRED]
        ).select_related(
            'enrollment__student__user',
            'enrollment__grade',
            'enrollment__section',
            'assessment_component__subject',
            'assessment_component__period',
            'assessment_component__academic_year',
            'entered_by'
        )

        if period:
            marks_qs = marks_qs.filter(assessment_component__period=period)
        if academic_year:
            marks_qs = marks_qs.filter(assessment_component__academic_year=academic_year)
        if grade_id:
            marks_qs = marks_qs.filter(enrollment__grade_id=grade_id)
        if section_id:
            marks_qs = marks_qs.filter(enrollment__section_id=section_id)
        if subject_id:
            marks_qs = marks_qs.filter(assessment_component__subject_id=subject_id)

        detected_list = []
        for mark in marks_qs:
            max_m = float(mark.assessment_component.max_marks or 100.0)
            if max_m <= 0:
                continue
            percent = (float(mark.mark_value) / max_m) * 100.0

            if percent < threshold:
                student = mark.enrollment.student
                subj = mark.assessment_component.subject
                comp = mark.assessment_component

                # Check if active intervention already recorded
                existing_int = AcademicIntervention.objects.filter(
                    school=school,
                    enrollment=mark.enrollment,
                    subject=subj,
                    assessment_component=comp,
                    status__in=[InterventionStatus.IDENTIFIED, InterventionStatus.IN_PROGRESS]
                ).first()

                detected_list.append({
                    'mark_id': mark.id,
                    'student_id': str(student.id),
                    'student_code': student.student_id,
                    'student_name': student.full_name,
                    'grade_name': mark.enrollment.grade.name if mark.enrollment.grade else '',
                    'section_name': mark.enrollment.section.name if mark.enrollment.section else '',
                    'section_id': mark.enrollment.section_id,
                    'enrollment_id': mark.enrollment.id,
                    'subject_id': subj.id,
                    'subject_name': subj.name,
                    'subject_code': subj.code,
                    'component_id': comp.id,
                    'component_name': comp.name,
                    'raw_score': float(mark.mark_value),
                    'max_marks': max_m,
                    'percentage': round(percent, 2),
                    'threshold': threshold,
                    'teacher_name': mark.entered_by.get_full_name() if mark.entered_by else 'Unassigned',
                    'teacher_id': mark.entered_by.id if mark.entered_by else None,
                    'period_name': comp.period.name if comp.period else '',
                    'has_active_intervention': existing_int is not None,
                    'intervention_id': existing_int.id if existing_int else None,
                    'intervention_status': existing_int.status if existing_int else None,
                })

        # Order by highest urgency (lowest percentage)
        detected_list.sort(key=lambda x: x['percentage'])
        return detected_list

    @classmethod
    def create_intervention(
        cls,
        school,
        enrollment_id: Any,
        subject_id: Any,
        trigger_score: float,
        intervention_type: str,
        action_plan: str,
        student_id: Optional[str] = None,
        component_id: Optional[Any] = None,
        scheduled_date=None,
        assigned_teacher_id: Optional[Any] = None,
        notify_parent: bool = False,
        user=None,
        ip_address: Optional[str] = None
    ) -> AcademicIntervention:
        """
        Creates an official academic intervention, schedules remedial action,
        and dispatches SMS alert to registered parent/guardian if enabled.
        """
        enrollment = None
        if enrollment_id:
            try:
                enrollment = StudentEnrollment.objects.filter(id=enrollment_id, school=school).select_related('student', 'grade', 'section', 'academic_year').first()
            except Exception:
                enrollment = None
        if not enrollment and student_id:
            enrollment = StudentEnrollment.objects.filter(student_id=student_id, school=school).select_related('student', 'grade', 'section', 'academic_year').order_by('-academic_year__gregorian_start_date', '-id').first()
        if not enrollment:
            raise ValueError("Student enrollment record could not be found.")

        student = enrollment.student
        subject = Subject.objects.filter(id=subject_id, school=school).first()
        if not subject:
            raise ValueError(f"Subject not found.")

        component = AssessmentComponent.objects.filter(id=component_id, school=school).first() if component_id else None

        scale = GradingScale.get_effective_scale(school, grade=enrollment.grade)
        applied_threshold = scale.below_average_threshold if scale else Decimal('60.00')

        period = component.period if component and component.period else enrollment.academic_year.periods.first()

        assigned_teacher = None
        if assigned_teacher_id:
            if isinstance(assigned_teacher_id, User):
                assigned_teacher = assigned_teacher_id
            else:
                tid_str = str(assigned_teacher_id).strip()
                # 1. Try User lookup by UUID/pk
                try:
                    assigned_teacher = User.objects.filter(id=tid_str, school=school).first()
                except Exception:
                    assigned_teacher = None

                # 2. Try TeacherProfile lookup if User query didn't find or if an integer ID was passed
                if not assigned_teacher:
                    try:
                        from apps.teachers.models import TeacherProfile
                        tp = None
                        if tid_str.isdigit():
                            tp = TeacherProfile.objects.filter(id=int(tid_str), school=school).select_related('user').first()
                        if not tp:
                            tp = TeacherProfile.objects.filter(school=school, employee_id=tid_str).select_related('user').first()
                        if tp:
                            assigned_teacher = tp.user
                    except Exception:
                        pass

        # Ensure scheduled_date is parsed to date object if passed as string
        parsed_date = scheduled_date
        if isinstance(parsed_date, str) and parsed_date.strip():
            try:
                import datetime
                parsed_date = datetime.date.fromisoformat(parsed_date.strip())
            except Exception:
                try:
                    from django.utils.dateparse import parse_date
                    parsed_date = parse_date(parsed_date.strip())
                except Exception:
                    parsed_date = None

        intervention = AcademicIntervention.objects.create(
            school=school,
            student=student,
            enrollment=enrollment,
            subject=subject,
            assessment_component=component,
            academic_year=enrollment.academic_year,
            period=period,
            trigger_score=Decimal(str(round(float(trigger_score), 2))),
            threshold_applied=applied_threshold,
            intervention_type=intervention_type,
            status=InterventionStatus.IN_PROGRESS if parsed_date else InterventionStatus.IDENTIFIED,
            assigned_teacher=assigned_teacher,
            created_by=user,
            action_plan=action_plan or f"Academic remediation and revision plan for {subject.name}.",
            scheduled_date=parsed_date,
        )

        # Parent SMS Notification Trigger
        if notify_parent:
            cls.dispatch_parent_notification(intervention, school=school)

        AuditService.log_action(
            school=school,
            user=user,
            action="ACADEMIC_INTERVENTION_CREATED",
            object_type="AcademicIntervention",
            object_id=str(intervention.id),
            after_val={
                'student': student.full_name,
                'subject': subject.name,
                'trigger_score': float(trigger_score),
                'type': intervention_type,
                'notify_parent': notify_parent
            },
            ip_address=ip_address
        )

        return intervention

    @classmethod
    def dispatch_parent_notification(cls, intervention: AcademicIntervention, school=None) -> bool:
        """
        Dispatches SMS to student parent/guardian regarding below-average score and intervention.
        Supports Ethiopic Amharic and English templating and live gateway routing.
        """
        school = school or intervention.school
        student = intervention.student

        # 1. Resolve Parent / Guardian
        guardian_rel = None
        try:
            from apps.parents.models import GuardianRelationship
            guardian_rel = GuardianRelationship.objects.filter(
                school=school, student=student, is_primary=True
            ).select_related('parent__user').first()
            if not guardian_rel:
                guardian_rel = GuardianRelationship.objects.filter(
                    school=school, student=student
                ).select_related('parent__user').first()
        except Exception:
            guardian_rel = None

        parent = guardian_rel.parent if guardian_rel else None
        if not parent:
            try:
                parent = student.primary_guardian
            except Exception:
                parent = None

        parent_user = getattr(parent, 'user', None) if parent else None

        # 2. Resolve Contact Phone Number
        raw_phone = (
            (parent.phone if parent and getattr(parent, 'phone', None) else '')
            or (getattr(parent_user, 'phone', '') if parent_user else '')
            or (student.phone or '')
            or (student.emergency_contact or '')
            or (getattr(student.user, 'phone', '') if getattr(student, 'user', None) else '')
        )
        phone = "".join(ch for ch in str(raw_phone).strip() if ch.isdigit() or ch == '+')

        if not phone or len([c for c in phone if c.isdigit()]) < 8:
            logger.warning(
                f"[Intervention SMS] No valid phone number found for student {student.student_id} "
                f"or primary guardian. Skipping SMS alert."
            )
            return False

        # 3. Resolve Language & Text
        lang = getattr(parent, 'preferred_language', 'am') if parent else 'am'

        sch_date = intervention.scheduled_date
        if isinstance(sch_date, str) and sch_date.strip():
            try:
                import datetime
                sch_date = datetime.date.fromisoformat(sch_date.strip())
            except Exception:
                try:
                    from django.utils.dateparse import parse_date
                    sch_date = parse_date(sch_date.strip())
                except Exception:
                    pass

        if hasattr(sch_date, 'strftime'):
            date_en = sch_date.strftime('%b %d, %Y')
            date_am = sch_date.strftime('%Y-%m-%d')
        elif sch_date:
            date_en = str(sch_date)
            date_am = str(sch_date)
        else:
            date_en = "this week"
            date_am = "በዚህ ሳምንት"

        date_str = date_am if lang == 'am' else date_en

        type_map_am = {
            'TUTORIAL': 'ተጨማሪ የማጠናከሪያ ትምህርት (Tutorial)',
            'PARENT_MEETING': 'የወላጅ ውይይት (Parent Conference)',
            'COUNSELING': 'የትምህርት ምክርና ድጋፍ (Counseling)',
            'PEER_TUTORING': 'የእኩዮች ድጋፍ (Peer Tutoring)',
            'BEHAVIOR_CONTRACT': 'የትምህርት እቅድ ስምምነት (Study Contract)',
            'CUSTOM': 'ልዩ የትምህርት ድጋፍ (Academic Support)',
        }
        type_display = type_map_am.get(intervention.intervention_type, intervention.get_intervention_type_display()) if lang == 'am' else intervention.get_intervention_type_display()

        stu_name = (student.amharic_name if (lang == 'am' and student.amharic_name) else None) or student.full_name
        school_name = school.name
        action_plan_brief = (intervention.action_plan[:75] + '...') if len(intervention.action_plan or '') > 75 else (intervention.action_plan or '')

        context = {
            'student_name': stu_name,
            'subject_name': intervention.subject.name,
            'score': f"{intervention.trigger_score:g}",
            'intervention_type': type_display,
            'date': date_str,
            'action_plan': action_plan_brief,
            'school_name': school_name,
        }

        # Render via configured SMS Template
        msg = ""
        try:
            from apps.communication.services import render_sms_template
            from apps.communication.models import SMSTemplateType
            msg = render_sms_template(school, SMSTemplateType.BELOW_AVERAGE_ALERT, context, lang=lang)
        except Exception as e:
            logger.warning(f"[Intervention SMS] Failed rendering template: {e}")

        # High-standard Ethiopic / English fallback
        if not msg or not msg.strip():
            if lang == 'am':
                msg = (
                    f"ክቡር ወላጅ፣ ተማሪ {stu_name} በ{intervention.subject.name} ትምህርት {intervention.trigger_score:g}% አስመዝግቧል:: "
                    f"የትምህርት ማሻሻያ ድጋፍ ({type_display}) ቀን: {date_str} ተዘጋጅቷል:: {school_name}::"
                )
            else:
                msg = (
                    f"Dear Parent/Guardian, {student.full_name} scored {intervention.trigger_score:g}% "
                    f"in {intervention.subject.name}. An academic support session ({type_display}) has been "
                    f"scheduled on {date_en}. Please contact {school_name} administration for details."
                )

        # 4. Resolve Recipient User (non-null for NotificationLog)
        recipient_user = (
            parent_user
            or getattr(student, 'user', None)
            or intervention.created_by
            or school.users.first()
        )

        success = NotificationDispatcher.send_notification(
            school=school,
            recipient_user=recipient_user,
            channel=NotificationChannel.SMS,
            message=msg,
            subject=f"Academic Support Alert: {student.full_name}",
            category='announcement',
            phone_number=phone
        )

        if success:
            intervention.parent_notified = True
            intervention.parent_notified_at = timezone.now()
            intervention.parent_notification_channel = 'SMS'
            intervention.save(update_fields=['parent_notified', 'parent_notified_at', 'parent_notification_channel'])

        return bool(success)

    @classmethod
    def update_intervention(
        cls,
        intervention_id: int,
        school,
        status: Optional[str] = None,
        follow_up_date=None,
        follow_up_score: Optional[float] = None,
        outcome_notes: Optional[str] = None,
        user=None,
        ip_address: Optional[str] = None
    ) -> AcademicIntervention:
        """
        Updates intervention status, records follow-up retest scores,
        and resolves intervention if performance improved.
        """
        intervention = AcademicIntervention.objects.get(id=intervention_id, school=school)
        before_status = intervention.status

        if follow_up_date:
            intervention.follow_up_date = follow_up_date
        if follow_up_score is not None:
            intervention.follow_up_score = Decimal(str(round(float(follow_up_score), 2)))
            # If follow up score is >= threshold or passing mark, auto-set to RESOLVED if not explicitly overridden
            if float(follow_up_score) >= float(intervention.threshold_applied) and not status:
                status = InterventionStatus.RESOLVED

        if outcome_notes:
            intervention.outcome_notes = outcome_notes

        if status:
            intervention.status = status
            if status == InterventionStatus.RESOLVED and not intervention.resolved_at:
                intervention.resolved_at = timezone.now()

        intervention.save()

        AuditService.log_action(
            school=school,
            user=user,
            action="ACADEMIC_INTERVENTION_UPDATED",
            object_type="AcademicIntervention",
            object_id=str(intervention.id),
            before_val={'status': before_status},
            after_val={
                'status': intervention.status,
                'follow_up_score': float(intervention.follow_up_score) if intervention.follow_up_score else None,
                'outcome_notes': intervention.outcome_notes
            },
            ip_address=ip_address
        )

        return intervention
