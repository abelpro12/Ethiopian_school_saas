import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Avg, F, Count, Q
from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.academics.models import Subject, Section, AcademicYear, AcademicPeriod, Grade, Stream
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus, AcademicPeriodResult, MarkEntryLock, GradingScale
from apps.assessments.grading_service import GradingService
from apps.teachers.models import TeacherAssignment
from apps.platform_management.decorators import school_context_required
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.audit.services import AuditService

def get_school(request):
    school = getattr(request, 'school', None) or getattr(request.user, 'school', None) or getattr(request, 'active_school', None)
    if not school:
        school_id = request.session.get('school_id') if hasattr(request, 'session') else None
        if school_id:
            from apps.schools.models import School
            school = School.objects.filter(id=school_id).first()
    if not school:
        from apps.schools.models import School
        school = School.objects.filter(code='SEA').first() or School.objects.first()
    return school

def get_active_term(request):
    school = get_school(request)
    ay = getattr(request, 'academic_year', None)
    if not ay:
        ay = AcademicYear.objects.filter(school=school, is_active=True).first()
        if not ay:
            ay = AcademicYear.objects.filter(school=school).first()
    
    sem = None
    if ay:
        sem = AcademicPeriod.objects.filter(academic_year=ay, is_current=True).first()
        if not sem:
            sem = AcademicPeriod.objects.filter(academic_year=ay).first()
            if not sem:
                sem, _ = AcademicPeriod.objects.get_or_create(
                    school=school,
                    academic_year=ay,
                    name="Semester 1",
                    defaults={
                        'period_type': 'SEMESTER',
                        'start_date': ay.gregorian_start_date,
                        'end_date': ay.gregorian_end_date,
                        'is_current': True
                    }
                )
    return ay, sem

def check_admin_access(user):
    return user.role in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR]

@login_required
def manage_components(request):

    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = get_school(request)
    ay, sem = get_active_term(request)

    grades = Grade.objects.filter(school=school).order_by('level')
    streams = Stream.objects.filter(school=school).order_by('name')

    selected_grade_id = request.GET.get('grade') or request.POST.get('selected_grade_id') or ''
    selected_stream_id = request.GET.get('stream') or request.POST.get('selected_stream_id') or ''

    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ['add_component', 'bulk_add_component']:
            name = request.POST.get('name', '').strip()
            weight = request.POST.get('weight')
            max_marks = request.POST.get('max_marks', 100.0)
            target_grade_id = request.POST.get('grade_id')
            target_stream_id = request.POST.get('stream_id')
            
            if not name:
                messages.error(request, "Component name is required.")
                return redirect('assessments:components')

            try:
                subjects = Subject.objects.filter(school=school)
                if target_grade_id:
                    subjects = subjects.filter(grade_id=target_grade_id)
                if target_stream_id:
                    subjects = subjects.filter(stream_id=target_stream_id)

                created_count = 0
                if subjects.exists():
                    for subject in subjects:
                        _, created = AssessmentComponent.objects.get_or_create(
                            school=school,
                            academic_year=ay,
                            period=sem,
                            subject=subject,
                            name=name,
                            defaults={
                                'weight': weight,
                                'max_marks': max_marks
                            }
                        )
                        if created:
                            created_count += 1
                    target_desc = ""
                    if target_grade_id:
                        g_obj = grades.filter(id=target_grade_id).first()
                        if g_obj: target_desc += f" {g_obj.name}"
                    if target_stream_id:
                        s_obj = streams.filter(id=target_stream_id).first()
                        if s_obj: target_desc += f" ({s_obj.name})"
                    messages.success(request, f"Assessment component '{name}' ({weight}%) saved for{target_desc or ' all subjects'}.")
                else:
                    messages.error(request, "No matching subjects found for the selected Grade & Stream.")

            except Exception as e:
                messages.error(request, f"Error adding component: {e}")
                
        elif action == 'delete_component':
            comp_name = request.POST.get('component_name')
            comp_id = request.POST.get('component_id')
            target_grade_id = request.POST.get('grade_id')
            target_stream_id = request.POST.get('stream_id')
            try:
                comps = AssessmentComponent.objects.filter(school=school, academic_year=ay, period=sem)
                if comp_name:
                    comps = comps.filter(name=comp_name)
                elif comp_id:
                    comp = AssessmentComponent.objects.get(id=comp_id, school=school)
                    comps = comps.filter(name=comp.name)

                if target_grade_id:
                    comps = comps.filter(subject__grade_id=target_grade_id)
                if target_stream_id:
                    comps = comps.filter(subject__stream_id=target_stream_id)

                comps.delete()
                messages.success(request, "Component deleted successfully.")
            except Exception as e:
                messages.error(request, f"Error deleting component: {e}")
                
        elif action == 'edit_component':
            old_name = request.POST.get('old_name')
            new_name = request.POST.get('name', '').strip()
            weight = request.POST.get('weight')
            max_marks = request.POST.get('max_marks')
            target_grade_id = request.POST.get('grade_id')
            target_stream_id = request.POST.get('stream_id')
            
            try:
                comps = AssessmentComponent.objects.filter(school=school, academic_year=ay, period=sem, name=old_name)
                if target_grade_id:
                    comps = comps.filter(subject__grade_id=target_grade_id)
                if target_stream_id:
                    comps = comps.filter(subject__stream_id=target_stream_id)

                update_dict = {'weight': weight, 'max_marks': max_marks}
                if new_name:
                    update_dict['name'] = new_name
                comps.update(**update_dict)
                messages.success(request, f"Assessment component '{new_name or old_name}' updated successfully.")
            except Exception as e:
                messages.error(request, f"Error updating component: {e}")
                
        elif action in ['import_past_config', 'replicate_past_year_scheme']:
            source_year_id = request.POST.get('source_year_id')
            source_grade_id = request.POST.get('source_grade_id')
            source_stream_id = request.POST.get('source_stream_id')
            source_section_id = request.POST.get('source_section_id')

            target_grade_id = request.POST.get('target_grade_id')
            target_stream_id = request.POST.get('target_stream_id')
            target_section_id = request.POST.get('target_section_id')
            target_period_id = request.POST.get('target_period_id')
            source_period_name = request.POST.get('source_period_name', '').strip()
            source_period_id = request.POST.get('source_period_id')
            overwrite_existing = request.POST.get('overwrite_existing') == 'true'

            if not source_year_id:
                messages.error(request, "Please select a source past academic year.")
            else:
                try:
                    source_year = AcademicYear.objects.get(id=source_year_id, school=school)
                    
                    # 1. Resolve source evaluation period
                    source_sem = None
                    if source_period_id:
                        source_sem = AcademicPeriod.objects.filter(id=source_period_id, school=school, academic_year=source_year).first()
                    elif source_period_name:
                        source_sem = AcademicPeriod.objects.filter(school=school, academic_year=source_year, name__iexact=source_period_name).first()
                    
                    if not source_sem:
                        # Auto-match by current period name (e.g. "Semester 1" -> "Semester 1")
                        source_sem = AcademicPeriod.objects.filter(
                            school=school, academic_year=source_year, name__iexact=sem.name
                        ).first()
                    if not source_sem:
                        # Fallback by period_type (e.g. SEMESTER)
                        source_sem = AcademicPeriod.objects.filter(
                            school=school, academic_year=source_year, period_type=sem.period_type
                        ).first()
                    if not source_sem:
                        source_sem = AcademicPeriod.objects.filter(school=school, academic_year=source_year).first()

                    # 2. Resolve target evaluation period
                    target_period = sem
                    if target_period_id:
                        p_obj = AcademicPeriod.objects.filter(id=target_period_id, school=school).first()
                        if p_obj: target_period = p_obj

                    if not source_sem:
                        messages.error(request, f"No evaluation periods found in past year '{source_year.name}'.")
                    else:
                        source_comps = AssessmentComponent.objects.filter(
                            school=school, academic_year=source_year, period=source_sem
                        ).select_related('subject__grade', 'subject__stream')

                        if source_grade_id:
                            source_comps = source_comps.filter(subject__grade_id=source_grade_id)
                        if source_stream_id:
                            source_comps = source_comps.filter(subject__stream_id=source_stream_id)

                        if not source_comps.exists():
                            messages.warning(request, f"No assessment components found in {source_year.name} ({source_sem.name}) for the selected criteria.")
                        else:
                            from collections import defaultdict
                            subject_comps_grouped = defaultdict(list)
                            for sc in source_comps:
                                if sc.subject:
                                    subject_comps_grouped[sc.subject].append(sc)

                            subject_map = {}
                            subject_name_map = {}
                            grade_stream_schemes = {}
                            global_clean_scheme = []

                            for s_subj, s_comps in subject_comps_grouped.items():
                                g_level = s_subj.grade.level if s_subj.grade else None
                                str_code = s_subj.stream.code if s_subj.stream else 'GEN'
                                comp_list = [
                                    {'name': c.name, 'weight': c.weight, 'max_marks': c.max_marks}
                                    for c in s_comps
                                ]
                                total_w = sum(float(c['weight']) for c in comp_list)

                                key_code = (s_subj.code.upper().strip(), g_level, str_code)
                                key_name = (s_subj.name.lower().strip(), g_level, str_code)
                                subject_map[key_code] = comp_list
                                subject_name_map[key_name] = comp_list

                                g_key = (g_level, str_code)
                                if round(total_w, 2) == 100.0 and g_key not in grade_stream_schemes:
                                    grade_stream_schemes[g_key] = comp_list
                                    if not global_clean_scheme:
                                        global_clean_scheme = comp_list

                            for s_subj, s_comps in subject_comps_grouped.items():
                                g_level = s_subj.grade.level if s_subj.grade else None
                                str_code = s_subj.stream.code if s_subj.stream else 'GEN'
                                g_key = (g_level, str_code)
                                if g_key not in grade_stream_schemes:
                                    grade_stream_schemes[g_key] = [
                                        {'name': c.name, 'weight': c.weight, 'max_marks': c.max_marks}
                                        for c in s_comps
                                    ]

                            if not global_clean_scheme and grade_stream_schemes:
                                global_clean_scheme = list(grade_stream_schemes.values())[0]

                            target_subjects = Subject.objects.filter(school=school).select_related('grade', 'stream')
                            if target_grade_id:
                                target_subjects = target_subjects.filter(grade_id=target_grade_id)
                            elif source_grade_id:
                                src_g = Grade.objects.filter(id=source_grade_id, school=school).first()
                                if src_g:
                                    target_subjects = target_subjects.filter(grade__level=src_g.level, grade__stream_type=src_g.stream_type)

                            if target_stream_id:
                                target_subjects = target_subjects.filter(stream_id=target_stream_id)

                            imported_count = 0
                            with transaction.atomic():
                                for t_subj in target_subjects:
                                    t_g_level = t_subj.grade.level if t_subj.grade else None
                                    t_str_code = t_subj.stream.code if t_subj.stream else 'GEN'

                                    # 1. Exact subject match by code & grade
                                    t_key_code = (t_subj.code.upper().strip(), t_g_level, t_str_code)
                                    target_comps = subject_map.get(t_key_code)

                                    # 2. Subject match by name & grade
                                    if not target_comps:
                                        t_key_name = (t_subj.name.lower().strip(), t_g_level, t_str_code)
                                        target_comps = subject_name_map.get(t_key_name)

                                    # 3. Match across streams by code & level
                                    if not target_comps:
                                        for (sc_code, sc_lvl, _), c_list in subject_map.items():
                                            if sc_code == t_subj.code.upper().strip() and sc_lvl == t_g_level:
                                                target_comps = c_list
                                                break

                                    # 4. Fallback to (grade, stream) scheme
                                    if not target_comps:
                                        target_comps = grade_stream_schemes.get((t_g_level, t_str_code))

                                    # 5. Fallback to global clean scheme
                                    if not target_comps:
                                        target_comps = grade_stream_schemes.get((t_g_level, 'GEN')) or global_clean_scheme

                                    if not target_comps:
                                        continue

                                    # Overwrite cleanup: remove un-marked components first
                                    if overwrite_existing:
                                        existing_comps = AssessmentComponent.objects.filter(
                                            school=school, academic_year=ay, period=target_period, subject=t_subj
                                        )
                                        for ec in existing_comps:
                                            if not StudentMark.objects.filter(assessment_component=ec).exists():
                                                ec.delete()

                                    for c_def in target_comps:
                                        if overwrite_existing:
                                            _, created = AssessmentComponent.objects.update_or_create(
                                                school=school,
                                                academic_year=ay,
                                                period=target_period,
                                                subject=t_subj,
                                                name=c_def['name'],
                                                defaults={
                                                    'weight': c_def['weight'],
                                                    'max_marks': c_def['max_marks']
                                                }
                                            )
                                            imported_count += 1
                                        else:
                                            _, created = AssessmentComponent.objects.get_or_create(
                                                school=school,
                                                academic_year=ay,
                                                period=target_period,
                                                subject=t_subj,
                                                name=c_def['name'],
                                                defaults={
                                                    'weight': c_def['weight'],
                                                    'max_marks': c_def['max_marks']
                                                }
                                            )
                                            if created:
                                                imported_count += 1

                            messages.success(
                                request,
                                f"Successfully replicated assessment schemes from {source_year.name} ({source_sem.name}) into {ay.name} ({target_period.name})! ({imported_count} subject components configured with 100% accurate weights)."
                            )
                except Exception as e:
                    messages.error(request, f"Error replicating past year assessment scheme: {e}")

        elif action == 'seed_standard_scheme':
            target_grade_id = request.POST.get('grade_id')
            preset = request.POST.get('preset', 'STANDARD_5')
            overwrite_existing = request.POST.get('overwrite_existing') == 'true'
            
            if preset == 'STANDARD_5':
                scheme_defs = [
                    {'name': 'Class Activity / Assignment', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Quiz & Homework', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Project / Practical Work', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Midterm Exam', 'weight': 20.0, 'max_marks': 20.0},
                    {'name': 'Final Exam', 'weight': 50.0, 'max_marks': 50.0},
                ]
            elif preset == 'STANDARD_3':
                scheme_defs = [
                    {'name': 'Continuous Assessment (CA)', 'weight': 30.0, 'max_marks': 30.0},
                    {'name': 'Midterm Examination', 'weight': 20.0, 'max_marks': 20.0},
                    {'name': 'Final Examination', 'weight': 50.0, 'max_marks': 50.0},
                ]
            else:
                scheme_defs = [
                    {'name': 'Classwork & Homework', 'weight': 15.0, 'max_marks': 15.0},
                    {'name': 'Project & Practical', 'weight': 15.0, 'max_marks': 15.0},
                    {'name': 'Midterm Exam', 'weight': 20.0, 'max_marks': 20.0},
                    {'name': 'Final Exam', 'weight': 50.0, 'max_marks': 50.0},
                ]

            target_subjects = Subject.objects.filter(school=school)
            if target_grade_id:
                target_subjects = target_subjects.filter(grade_id=target_grade_id)

            if not target_subjects.exists():
                messages.error(request, "No subjects found to apply the assessment scheme. Please add subjects first.")
            else:
                created_total = 0
                with transaction.atomic():
                    for subj in target_subjects:
                        if overwrite_existing:
                            existing_comps = AssessmentComponent.objects.filter(
                                school=school, academic_year=ay, period=sem, subject=subj
                            )
                            for ec in existing_comps:
                                if not StudentMark.objects.filter(assessment_component=ec).exists():
                                    ec.delete()

                        for comp_def in scheme_defs:
                            if overwrite_existing:
                                _, created = AssessmentComponent.objects.update_or_create(
                                    school=school,
                                    academic_year=ay,
                                    period=sem,
                                    subject=subj,
                                    name=comp_def['name'],
                                    defaults={
                                        'weight': comp_def['weight'],
                                        'max_marks': comp_def['max_marks']
                                    }
                                )
                                created_total += 1
                            else:
                                _, created = AssessmentComponent.objects.get_or_create(
                                    school=school,
                                    academic_year=ay,
                                    period=sem,
                                    subject=subj,
                                    name=comp_def['name'],
                                    defaults={
                                        'weight': comp_def['weight'],
                                        'max_marks': comp_def['max_marks']
                                    }
                                )
                                if created:
                                    created_total += 1
                messages.success(request, f"Standard Ethiopian 100% Assessment Scheme initialized successfully! ({created_total} components created).")

        elif action == 'replicate_grade_scheme':
            source_grade_id = request.POST.get('source_grade_id')
            source_stream_id = request.POST.get('source_stream_id')
            target_grade_id = request.POST.get('target_grade_id')
            target_stream_id = request.POST.get('target_stream_id')
            overwrite_existing = request.POST.get('overwrite_existing') == 'true'

            if not source_grade_id:
                messages.error(request, "Please select a source grade to copy from.")
            else:
                source_comps = AssessmentComponent.objects.filter(
                    school=school, academic_year=ay, period=sem, subject__grade_id=source_grade_id
                ).select_related('subject')

                if source_stream_id:
                    source_comps = source_comps.filter(subject__stream_id=source_stream_id)

                if not source_comps.exists():
                    messages.error(request, "The source grade does not have any assessment components configured yet.")
                else:
                    from collections import defaultdict
                    source_by_subj = defaultdict(list)
                    for sc in source_comps:
                        if sc.subject:
                            source_by_subj[sc.subject].append(sc)

                    subject_code_map = {}
                    subject_name_map = {}
                    grade_clean_scheme = []

                    for s_subj, s_comps in source_by_subj.items():
                        c_list = [{'name': c.name, 'weight': c.weight, 'max_marks': c.max_marks} for c in s_comps]
                        total_w = sum(float(c['weight']) for c in c_list)
                        subject_code_map[s_subj.code.upper().strip()] = c_list
                        subject_name_map[s_subj.name.lower().strip()] = c_list
                        if round(total_w, 2) == 100.0 and not grade_clean_scheme:
                            grade_clean_scheme = c_list

                    if not grade_clean_scheme and source_by_subj:
                        first_subj_comps = list(source_by_subj.values())[0]
                        grade_clean_scheme = [{'name': c.name, 'weight': c.weight, 'max_marks': c.max_marks} for c in first_subj_comps]

                    if target_grade_id:
                        target_grades = grades.filter(id=target_grade_id)
                    else:
                        target_grades = grades.exclude(id=source_grade_id)

                    replicated_count = 0
                    with transaction.atomic():
                        for tg in target_grades:
                            tg_subjects = Subject.objects.filter(school=school, grade=tg)
                            if target_stream_id:
                                tg_subjects = tg_subjects.filter(stream_id=target_stream_id)

                            for t_subj in tg_subjects:
                                t_comps = subject_code_map.get(t_subj.code.upper().strip()) or subject_name_map.get(t_subj.name.lower().strip()) or grade_clean_scheme

                                if not t_comps:
                                    continue

                                if overwrite_existing:
                                    existing_comps = AssessmentComponent.objects.filter(
                                        school=school, academic_year=ay, period=sem, subject=t_subj
                                    )
                                    for ec in existing_comps:
                                        if not StudentMark.objects.filter(assessment_component=ec).exists():
                                            ec.delete()

                                for c_def in t_comps:
                                    if overwrite_existing:
                                        _, was_created = AssessmentComponent.objects.update_or_create(
                                            school=school,
                                            academic_year=ay,
                                            period=sem,
                                            subject=t_subj,
                                            name=c_def['name'],
                                            defaults={
                                                'weight': c_def['weight'],
                                                'max_marks': c_def['max_marks']
                                            }
                                        )
                                        replicated_count += 1
                                    else:
                                        _, was_created = AssessmentComponent.objects.get_or_create(
                                            school=school,
                                            academic_year=ay,
                                            period=sem,
                                            subject=t_subj,
                                            name=c_def['name'],
                                            defaults={
                                                'weight': c_def['weight'],
                                                'max_marks': c_def['max_marks']
                                            }
                                        )
                                        if was_created:
                                            replicated_count += 1

                    source_grade_name = Grade.objects.filter(id=source_grade_id).first()
                    messages.success(request, f"Successfully replicated assessment structure from {source_grade_name} across target grades ({replicated_count} components created).")

        redirect_url = request.path
        params = []
        if selected_grade_id: params.append(f"grade={selected_grade_id}")
        if selected_stream_id: params.append(f"stream={selected_stream_id}")
        if params: redirect_url += "?" + "&".join(params)
        return redirect(redirect_url)

    # Calculate per-grade grouped breakdown & validation
    all_components_raw = AssessmentComponent.objects.filter(
        school=school, academic_year=ay, period=sem
    ).select_related('subject__grade', 'subject__stream').order_by('name')

    grade_groups = []
    unique_components = []
    seen_global_keys = set()

    for g in grades:
        g_comps = []
        g_seen = set()
        g_raw = all_components_raw.filter(subject__grade=g)
        
        # Calculate subject-by-subject total weights
        g_subjects = Subject.objects.filter(school=school, grade=g)
        subject_weights = []
        for subj in g_subjects:
            s_comps = g_raw.filter(subject=subj)
            if s_comps.exists():
                sw = sum(float(c.weight) for c in s_comps)
                subject_weights.append(sw)

        for comp in g_raw:
            k = (comp.name, comp.weight, comp.max_marks, comp.subject.stream_id if comp.subject.stream else None)
            if k not in g_seen:
                g_seen.add(k)
                comp.scope_grade = g
                comp.scope_stream = comp.subject.stream
                g_comps.append(comp)

            # Also maintain unique components list for flat view
            gk = (comp.name, comp.weight, comp.max_marks, g.id, comp.subject.stream_id if comp.subject.stream else None)
            if gk not in seen_global_keys:
                seen_global_keys.add(gk)
                unique_components.append(comp)

        if subject_weights:
            is_valid_grade = all(round(sw, 2) == 100.0 for sw in subject_weights)
            g_weight = round(sum(subject_weights) / len(subject_weights), 2)
        else:
            is_valid_grade = False
            g_weight = 0.0

        grade_groups.append({
            'grade': g,
            'components': g_comps,
            'total_weight': g_weight,
            'is_valid': is_valid_grade,
            'component_count': len(g_comps),
        })

    # Determine scope summary metrics
    if selected_grade_id:
        filtered_groups = [gg for gg in grade_groups if str(gg['grade'].id) == str(selected_grade_id)]
        selected_group = filtered_groups[0] if filtered_groups else None
        scope_total_weight = selected_group['total_weight'] if selected_group else 0.0
        is_scope_valid = (scope_total_weight == 100.0)
        scope_title = f"{selected_group['grade'].name} Scheme" if selected_group else "Selected Grade"
        displayed_groups = filtered_groups
    else:
        configured_groups = [gg for gg in grade_groups if gg['component_count'] > 0]
        configured_count = len(configured_groups)
        valid_count = sum(1 for gg in configured_groups if gg['is_valid'])
        is_scope_valid = (configured_count > 0 and valid_count == configured_count)
        scope_total_weight = 100.0 if is_scope_valid else (
            round(sum(gg['total_weight'] for gg in configured_groups) / max(1, configured_count), 1) if configured_count > 0 else 0.0
        )
        scope_title = "All Grade Schemes"
        displayed_groups = grade_groups

    past_years = AcademicYear.objects.filter(school=school).exclude(id=ay.id).order_by('-gregorian_start_date') if ay else []
    sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    periods = AcademicPeriod.objects.filter(school=school, academic_year=ay).order_by('start_date') if ay else []
    all_period_names = list(AcademicPeriod.objects.filter(school=school).values_list('name', flat=True).distinct())

    return render(request, 'assessments/components.html', {
        'components': unique_components,
        'grade_groups': displayed_groups,
        'all_grade_groups': grade_groups,
        'scope_total_weight': scope_total_weight,
        'is_scope_valid': is_scope_valid,
        'scope_title': scope_title,
        'total_configured_grades': sum(1 for gg in grade_groups if gg['component_count'] > 0),
        'total_valid_grades': sum(1 for gg in grade_groups if gg['is_valid']),
        'total_school_grades': len(grades),
        'ay': ay,
        'sem': sem,
        'grades': grades,
        'streams': streams,
        'sections': sections,
        'periods': periods,
        'past_years': past_years,
        'all_period_names': all_period_names,
        'selected_grade_id': selected_grade_id,
        'selected_stream_id': selected_stream_id,
    })



@login_required
def mark_entry(request):
    """Dashboard for teachers/admins to select which class/subject to enter or view marks for."""
    school = get_school(request)
    ay, sem = get_active_term(request)
    
    selected_subject_id = request.GET.get('subject_id')
    subjects = Subject.objects.filter(school=school).order_by('name')

    # Teachers can only enter marks for sections they are assigned to
    if request.user.role == UserRole.TEACHER:
        assignments_qs = TeacherAssignment.objects.filter(
            school=school, teacher__user=request.user
        )
    else:
        assignments_qs = TeacherAssignment.objects.filter(
            school=school
        )

    if selected_subject_id:
        assignments_qs = assignments_qs.filter(subject_id=selected_subject_id)

    if ay:
        assignments = assignments_qs.filter(academic_year=ay).select_related('section__grade', 'subject', 'teacher__user')
        if not assignments.exists() and not selected_subject_id:
            assignments = assignments_qs.select_related('section__grade', 'subject', 'teacher__user')
    else:
        assignments = assignments_qs.select_related('section__grade', 'subject', 'teacher__user')
        
    # Annotate assignments with lock status
    assignment_list = list(assignments)
    for assign in assignment_list:
        is_l, l_reason, _ = MarkEntryLock.check_lock(
            school=school,
            academic_year=ay,
            period=sem,
            grade=assign.section.grade,
            subject=assign.subject,
            teacher=assign.teacher.user,
            section=assign.section
        )
        assign.is_locked = is_l
        assign.lock_reason = l_reason

    active_locks = MarkEntryLock.objects.filter(school=school, is_active=True).select_related(
        'grade', 'subject', 'teacher', 'locked_by'
    )
    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    teachers = User.objects.filter(school=school, role=UserRole.TEACHER).order_by('first_name', 'last_name')
    all_subjects = Subject.objects.filter(school=school).order_by('name')

    return render(request, 'assessments/mark_entry_dashboard.html', {
        'assignments': assignment_list,
        'subjects': subjects,
        'all_subjects': all_subjects,
        'grades': grades,
        'teachers': teachers,
        'active_locks': active_locks,
        'total_active_locks': active_locks.count(),
        'selected_subject_id': selected_subject_id,
        'ay': ay,
        'sem': sem,
        'school': school,
    })

@login_required
def mark_entry_grid(request, section_id, subject_id):
    school = get_school(request)
    ay, sem = get_active_term(request)
    
    section = get_object_or_404(Section, id=section_id, school=school)
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    # Verify permission (if teacher, must be assigned)
    if request.user.role == UserRole.TEACHER:
        is_assigned = TeacherAssignment.objects.filter(
            school=school, teacher__user=request.user, section=section, subject=subject
        ).exists()
        if not is_assigned:
            messages.error(request, "You are not assigned to this subject/section.")
            return redirect('assessments:mark_entry')

    components_qs = AssessmentComponent.objects.filter(
        school=school, subject=subject
    )
    if ay:
        components_qs = components_qs.filter(academic_year=ay)
    if sem:
        components_qs = components_qs.filter(period=sem)

    # Check master components defined for this active period
    master_comp_names = list(AssessmentComponent.objects.filter(
        school=school, period=sem
    ).values_list('name', flat=True).distinct()) if sem else []

    if master_comp_names:
        # Remove any stale/unwanted components for this subject and period that do not belong to current period config
        stale_comps = components_qs.exclude(name__in=master_comp_names)
        for sc in stale_comps:
            if not StudentMark.objects.filter(assessment_component=sc).exists():
                sc.delete()
        components_qs = components_qs.filter(name__in=master_comp_names)

    components = components_qs.order_by('id')
    
    if not components.exists():
        source_comps = AssessmentComponent.objects.none()
        if sem:
            sem_master = AssessmentComponent.objects.filter(school=school, period=sem)
            if sem_master.exists():
                source_comps = sem_master
            else:
                # Find single latest period prior to this one
                latest_comp = AssessmentComponent.objects.filter(school=school).exclude(period=sem).order_by('-id').first()
                if latest_comp and latest_comp.period:
                    source_comps = AssessmentComponent.objects.filter(school=school, period=latest_comp.period)

        if source_comps.exists():
            seen_names = set()
            for mc in source_comps:
                if mc.name not in seen_names:
                    seen_names.add(mc.name)
                    AssessmentComponent.objects.get_or_create(
                        school=school,
                        academic_year=ay or mc.academic_year,
                        period=sem or mc.period,
                        subject=subject,
                        name=mc.name,
                        defaults={'weight': mc.weight, 'max_marks': mc.max_marks}
                    )
        else:
            if ay and sem:
                defaults = [
                    ('Continuous Assessment', 30.0, 30.0),
                    ('Midterm Exam', 30.0, 30.0),
                    ('Final Exam', 40.0, 40.0),
                ]
                for cname, cweight, cmax in defaults:
                    AssessmentComponent.objects.get_or_create(
                        school=school,
                        academic_year=ay,
                        period=sem,
                        subject=subject,
                        name=cname,
                        defaults={'weight': cweight, 'max_marks': cmax}
                    )

        # Re-fetch components for subject
        components_qs = AssessmentComponent.objects.filter(school=school, subject=subject)
        if ay:
            components_qs = components_qs.filter(academic_year=ay)
        if sem:
            components_qs = components_qs.filter(period=sem)
        components = components_qs.order_by('id')
        if not components.exists():
            components = AssessmentComponent.objects.filter(school=school, subject=subject).order_by('id')

    enrollments_qs = StudentEnrollment.objects.filter(
        school=school, section=section
    )
    if ay:
        enrollments_qs = enrollments_qs.filter(academic_year=ay)
    
    enrollments = enrollments_qs.exclude(
        status__in=[EnrollmentStatus.WITHDRAWN, EnrollmentStatus.TRANSFERRED]
    ).select_related('student__user').order_by('student__user__first_name', 'student__user__last_name')

    # Fetch existing marks
    existing_marks = StudentMark.objects.filter(
        school=school, enrollment__in=enrollments, assessment_component__in=components
    )

    # Determine assigned teacher for lock evaluation and admin quick-toggle
    teacher_to_check = request.user if request.user.role == UserRole.TEACHER else None
    assigned_tch = TeacherAssignment.objects.filter(school=school, section=section, subject=subject).select_related('teacher__user').first()
    if not teacher_to_check and assigned_tch:
        teacher_to_check = assigned_tch.teacher.user

    from apps.academics.models import PeriodStatus
    is_period_locked = (sem and sem.status in [PeriodStatus.LOCKED, PeriodStatus.CLOSED, PeriodStatus.ARCHIVED])

    # Granular Lock check (by Grade, Subject, Teacher, Section)
    rule_locked, lock_reason, lock_obj = MarkEntryLock.check_lock(
        school=school,
        academic_year=ay,
        period=sem,
        grade=section.grade,
        subject=subject,
        teacher=teacher_to_check,
        section=section
    )

    # Annotate each component with its individual lock status
    component_list = list(components)
    for comp in component_list:
        comp_locked, comp_reason, comp_obj = MarkEntryLock.check_lock(
            school=school,
            academic_year=ay,
            period=sem,
            grade=section.grade,
            subject=subject,
            teacher=teacher_to_check,
            section=section,
            assessment_component=comp
        )
        comp.is_locked = is_period_locked or rule_locked or comp_locked
        comp.lock_reason = comp_reason if comp_locked else lock_reason
        comp.lock_obj = comp_obj or lock_obj

    is_locked = is_period_locked or rule_locked or any(m.status == MarkStatus.LOCKED for m in existing_marks)
    if not lock_reason:
        if is_period_locked:
            lock_reason = f"Academic term '{sem.name}' is globally locked."
        elif any(m.status == MarkStatus.LOCKED for m in existing_marks):
            lock_reason = "Individual student marks have been locked."
        elif not is_locked:
            lock_reason = ""

    # Status of lock toggles for this section/subject for admin/teacher toolbar
    grade_lock_active = MarkEntryLock.objects.filter(school=school, grade=section.grade, subject__isnull=True, teacher__isnull=True, section__isnull=True, is_active=True).exists()
    subject_lock_active = MarkEntryLock.objects.filter(school=school, subject=subject, grade__isnull=True, teacher__isnull=True, section__isnull=True, is_active=True).exists()
    section_subject_lock_active = MarkEntryLock.objects.filter(school=school, subject=subject, section=section, is_active=True).exists()
    teacher_lock_active = False
    if teacher_to_check:
        teacher_lock_active = MarkEntryLock.objects.filter(school=school, teacher=teacher_to_check, grade__isnull=True, subject__isnull=True, is_active=True).exists()
    
    # Grading Scale and Thresholds (<60% Below Avg, >=90% High Perf)
    scale = GradingScale.get_effective_scale(school, grade=section.grade)
    below_thresh = float(scale.below_average_threshold) if scale else 60.0
    high_thresh = float(scale.high_performance_threshold) if scale else 90.0

    # Map for easy rendering: mark_dict[enrollment_id][component_id] = mark
    mark_dict = {e.id: {} for e in enrollments}
    status = MarkStatus.DRAFT
    
    for mark in existing_marks:
        max_m = float(mark.assessment_component.max_marks or 100.0)
        pct = (float(mark.mark_value) / max_m * 100.0) if max_m > 0 else 0.0
        mark.percentage = round(pct, 2)
        if pct < below_thresh:
            mark.performance_tier = 'BELOW_AVERAGE'
        elif pct >= high_thresh:
            mark.performance_tier = 'HIGH_PERFORMANCE'
        else:
            mark.performance_tier = 'NORMAL'

        mark_dict[mark.enrollment.id][mark.assessment_component.id] = mark
        status = mark.status

    return render(request, 'assessments/mark_entry_grid.html', {
        'section': section,
        'subject': subject,
        'components': component_list,
        'enrollments': enrollments,
        'mark_dict': mark_dict,
        'status': status,
        'is_locked': is_locked,
        'is_period_locked': is_period_locked,
        'lock_reason': lock_reason,
        'lock_obj': lock_obj,
        'grade_lock_active': grade_lock_active,
        'subject_lock_active': subject_lock_active,
        'section_subject_lock_active': section_subject_lock_active,
        'teacher_lock_active': teacher_lock_active,
        'teacher_to_check': teacher_to_check,
        'scale': scale,
        'below_thresh': below_thresh,
        'high_thresh': high_thresh,
        'MarkStatus': MarkStatus,
        'ay': ay,
        'sem': sem
    })

@login_required
def save_marks(request):
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)
        
    school = get_school(request)
    action = request.POST.get('action', 'save') # 'save', 'submit', or 'publish'
    is_htmx = request.headers.get('HX-Request') or request.headers.get('x-requested-with') == 'XMLHttpRequest'

    from apps.academics.models import PeriodStatus
    
    try:
        saved_count = 0
        saved_students = set()
        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith('mark_'):
                    parts = key.split('_')
                    if len(parts) == 3:
                        enrollment_id = parts[1]
                        component_id = parts[2]
                        
                        comp = AssessmentComponent.objects.get(id=component_id, school=school)
                        if comp.period and comp.period.status == PeriodStatus.LOCKED:
                            err_msg = "Error: Academic results are LOCKED for this year by Admin and cannot be edited."
                            if is_htmx:
                                return HttpResponse(f"<div class='p-3 bg-red-100 text-red-800 rounded border border-red-200 mt-4'><i class='fa-solid fa-lock mr-2'></i>{err_msg}</div>", status=403)
                            messages.error(request, err_msg)
                            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))

                        enrollment = StudentEnrollment.objects.get(id=enrollment_id, school=school)

                        # Support Option B (Direct Letter Grade Entry e.g. A+, A, B, C, D, F)
                        val_str = str(value).strip().upper()
                        letters = {'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D', 'F', 'P'}
                        given_letter = None
                        if val_str in letters:
                            converted_score = GradingService.convert_letter_to_score(
                                school=school,
                                letter_grade=val_str,
                                max_marks=float(comp.max_marks or 100.0),
                                grade=enrollment.grade
                            )
                            mark_val = float(converted_score or 0.0)
                            given_letter = val_str
                        else:
                            try:
                                mark_val = float(value)
                            except ValueError:
                                continue

                        if mark_val < 0:
                            err_msg = f"Error: Mark cannot be negative (got {mark_val} for {comp.name})"
                            if is_htmx:
                                return HttpResponse(f"<div class='p-2 bg-red-100 text-red-800 rounded'>{err_msg}</div>", status=400)
                            messages.error(request, err_msg)
                            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))

                        if mark_val > float(comp.max_marks):
                            err_msg = f"Error: Mark {mark_val} exceeds max {comp.max_marks} for {comp.name}"
                            if is_htmx:
                                return HttpResponse(f"<div class='p-2 bg-red-100 text-red-800 rounded'>{err_msg}</div>", status=400)
                            messages.error(request, err_msg)
                            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))

                        # Granular Lock check (by Grade, Subject, Teacher, Section, and Assessment Component)
                        rule_locked, lock_reason, _ = MarkEntryLock.check_lock(
                            school=school,
                            academic_year=comp.academic_year,
                            period=comp.period,
                            grade=enrollment.grade,
                            subject=comp.subject,
                            teacher=request.user if request.user.role == UserRole.TEACHER else None,
                            section=enrollment.section,
                            assessment_component=comp
                        )
                        if rule_locked and not check_admin_access(request.user):
                            err_msg = lock_reason or "Error: Mark entry is locked for this class by School Administration."
                            if is_htmx:
                                return HttpResponse(f"<div class='p-3 bg-red-100 text-red-800 rounded border border-red-200 mt-4 font-bold'><i class='fa-solid fa-lock mr-2'></i>{err_msg}</div>", status=403)
                            messages.error(request, err_msg)
                            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))
                        
                        defaults_dict = {
                            'mark_value': mark_val,
                            'entered_by': request.user,
                        }
                        if given_letter:
                            defaults_dict['letter_grade'] = given_letter

                        mark_obj, created = StudentMark.objects.update_or_create(
                            school=school,
                            enrollment=enrollment,
                            assessment_component=comp,
                            defaults=defaults_dict
                        )
                        saved_count += 1
                        saved_students.add(enrollment_id)
                        
                        if action == 'submit':
                            mark_obj.status = MarkStatus.SUBMITTED
                            mark_obj.save(update_fields=['status', 'mark_value', 'entered_by'])
                        elif action == 'publish':
                            # Only admins/principals can directly publish marks
                            if check_admin_access(request.user):
                                mark_obj.status = MarkStatus.PUBLISHED
                                mark_obj.save(update_fields=['status', 'mark_value', 'entered_by'])
                            else:
                                # Teacher attempted direct publish — silently downgrade to SUBMITTED
                                mark_obj.status = MarkStatus.SUBMITTED
                                mark_obj.save(update_fields=['status', 'mark_value', 'entered_by'])
                            
            student_count = len(saved_students)
            if saved_count > 0:
                client_ip = AuditService.get_client_ip(request)
                action_label = 'MARK_SUBMIT' if action == 'submit' else ('MARK_PUBLISH' if action == 'publish' else 'MARK_SAVE')
                AuditService.log_action(
                    school=school,
                    user=request.user,
                    action=action_label,
                    object_type="StudentMarks",
                    object_id=f"{saved_count}_records",
                    after_val={
                        'marks_updated': saved_count,
                        'students_affected': student_count,
                        'action': action
                    },
                    ip_address=client_ip
                )

            if action == 'submit':
                msg = f"Submitted {saved_count} marks for {student_count} student{'s' if student_count != 1 else ''} for review successfully!"
            elif action == 'publish':
                msg = f"Published & updated {saved_count} marks for {student_count} student{'s' if student_count != 1 else ''} successfully!"
            else:
                msg = f"Successfully saved {saved_count} mark entries for {student_count} student{'s' if student_count != 1 else ''}."

            if is_htmx:
                return HttpResponse(f"<div class='p-3 bg-emerald-100 text-emerald-800 font-bold rounded-xl border border-emerald-200 mt-4 shadow-sm flex items-center gap-2'><i class='fa-solid fa-check-circle text-emerald-600 text-lg'></i>{msg}</div>")
            
            messages.success(request, msg)
            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))

    except Exception as e:
        err_msg = f"Error saving marks: {str(e)}"
        if is_htmx:
            return HttpResponse(f"<div class='p-3 bg-rose-100 text-rose-800 rounded-xl border border-rose-200 mt-4 font-semibold'>Error: {str(e)}</div>", status=400)
        messages.error(request, err_msg)
        return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))

@login_required
def mark_review(request):
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = get_school(request)
    ay, sem = get_active_term(request)
    
    # We need to find all unique (section, subject) combinations that have SUBMITTED marks
    submitted_marks = StudentMark.objects.filter(
        school=school, status=MarkStatus.SUBMITTED
    )
    if ay:
        submitted_marks = submitted_marks.filter(assessment_component__academic_year=ay)

    submitted_batches = submitted_marks.values(
        'enrollment__section__id', 
        'enrollment__section__name',
        'enrollment__section__grade__name',
        'assessment_component__subject__id',
        'assessment_component__subject__name'
    ).annotate(count=Count('id'))
    
    return render(request, 'assessments/review.html', {
        'submitted_batches': submitted_batches,
        'ay': ay,
        'sem': sem
    })

@login_required
def approve_marks(request):
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)
        
    school = get_school(request)
    section_id = request.POST.get('section_id')
    subject_id = request.POST.get('subject_id')
    
    approved_count = StudentMark.objects.filter(
        school=school,
        enrollment__section_id=section_id,
        assessment_component__subject_id=subject_id,
        status=MarkStatus.SUBMITTED
    ).update(status=MarkStatus.APPROVED)
    
    client_ip = AuditService.get_client_ip(request)
    AuditService.log_action(
        school=school,
        user=request.user,
        action="MARKS_APPROVED",
        object_type="SectionSubjectMarks",
        object_id=f"Sec_{section_id}_Subj_{subject_id}",
        after_val={'approved_count': approved_count, 'section_id': section_id, 'subject_id': subject_id},
        ip_address=client_ip
    )
    
    messages.success(request, f"{approved_count} marks approved successfully.")
    return redirect('assessments:review')

@login_required
@school_context_required
def period_close(request):
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access.")
        return redirect('index')

    school = get_school(request)
    ay, sem = get_active_term(request)
    
    if request.method == 'POST':
        # Simple AcademicPeriod Close Engine implementation
        enrollments = StudentEnrollment.objects.filter(school=school, academic_year=ay, status='ACTIVE')
        
        processed = 0
        for enrollment in enrollments:
            # Include all valid recorded marks for this enrollment and period
            marks = StudentMark.objects.filter(
                school=school, 
                enrollment=enrollment
            ).filter(
                Q(assessment_component__period=sem) | Q(assessment_component__academic_year=ay)
            ).filter(
                status__in=[MarkStatus.DRAFT, MarkStatus.SUBMITTED, MarkStatus.APPROVED, MarkStatus.PUBLISHED, MarkStatus.LOCKED]
            ).select_related('assessment_component', 'assessment_component__subject')
            
            # Aggregate marks per subject
            subject_dict = {}
            for mark in marks:
                sub = mark.assessment_component.subject
                if sub.id not in subject_dict:
                    subject_dict[sub.id] = {
                        'code': sub.code,
                        'name': sub.name,
                        'total': 0.0,
                        'max_total': 0.0
                    }
                
                try:
                    subject_dict[sub.id]['total'] += float(mark.mark_value)
                    subject_dict[sub.id]['max_total'] += float(mark.assessment_component.max_marks)
                except (ValueError, TypeError):
                    pass
                
            if not subject_dict:
                continue
                
            subject_results = []
            passed_count = 0
            failed_count = 0
            sum_normalized = 0.0

            for sub_id, sdata in subject_dict.items():
                raw = round(sdata['total'], 2)
                max_p = round(sdata['max_total'], 2) if sdata['max_total'] > 0 else 100.0
                normalized = round((raw / max_p * 100.0), 1) if max_p > 0 else raw
                sum_normalized += normalized

                if normalized >= 90: letter = 'A+'
                elif normalized >= 83: letter = 'A'
                elif normalized >= 75: letter = 'B'
                elif normalized >= 65: letter = 'C'
                elif normalized >= 50: letter = 'D'
                else: letter = 'F'

                is_pass = normalized >= 50
                if is_pass:
                    passed_count += 1
                else:
                    failed_count += 1

                subject_results.append({
                    'code': sdata['code'],
                    'name': sdata['name'],
                    'raw_score': raw,
                    'normalized': normalized,
                    'letter': letter,
                    'passed': is_pass
                })

            total_score = round(sum_normalized, 2)
            avg_score = round(sum_normalized / len(subject_results), 2)
            
            # Calculate Attendance Statistics
            period_attendance = AttendanceRecord.objects.filter(
                school=school,
                student=enrollment.student,
                date__gte=sem.start_date,
                date__lte=sem.end_date
            )
            
            att_present = period_attendance.filter(status=AttendanceStatus.PRESENT).count()
            att_absent = period_attendance.filter(status=AttendanceStatus.ABSENT).count()
            att_late = period_attendance.filter(status=AttendanceStatus.LATE).count()

            AcademicPeriodResult.objects.update_or_create(
                school=school,
                enrollment=enrollment,
                period=sem,
                defaults={
                    'total_score': total_score,
                    'average_score': avg_score,
                    'subjects_passed': passed_count,
                    'subjects_failed': failed_count,
                    'results_json': subject_results,
                    'is_published': True,
                    'attendance_present': att_present,
                    'attendance_absent': att_absent,
                    'attendance_late': att_late
                }
            )
            
            # Update mark status to published
            marks.update(status=MarkStatus.PUBLISHED)
            processed += 1
            
        # Rank computation — use bulk_update to avoid N+1 DB writes
        sections = Section.objects.filter(school=school)
        for section in sections:
            results = list(AcademicPeriodResult.objects.filter(
                school=school, period=sem, enrollment__section=section
            ).order_by('-average_score'))
            for i, res in enumerate(results, 1):
                res.section_rank = i
            AcademicPeriodResult.objects.bulk_update(results, ['section_rank'])
                
        # Auto-lock period after computation to prevent further edits by teachers
        from apps.academics.models import PeriodStatus
        if sem:
            sem.status = PeriodStatus.LOCKED
            sem.save()

        messages.success(request, f"AcademicPeriod closed & locked! Computed results for {processed} students.")
        return redirect('assessments:period_close')

    results_exist = AcademicPeriodResult.objects.filter(school=school, period=sem).exists()
    return render(request, 'assessments/period_close.html', {
        'ay': ay,
        'sem': sem,
        'results_exist': results_exist
    })

@login_required
@school_context_required
def toggle_period_lock(request, period_id):
    """
    Allows School Admins to lock or unlock mark data entry for an academic period anytime.
    """
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    from apps.academics.models import AcademicPeriod, PeriodStatus
    period = get_object_or_404(AcademicPeriod, id=period_id, school=school)

    if period.status == PeriodStatus.LOCKED:
        period.status = PeriodStatus.OPEN
        messages.success(request, f"Mark entry UNLOCKED for {period.name}. Teachers can now edit marks.")
    else:
        period.status = PeriodStatus.LOCKED
        messages.success(request, f"Mark entry LOCKED for {period.name}. Teachers can no longer alter marks.")

    period.save()

    referer = request.META.get('HTTP_REFERER')
    return redirect(referer or 'assessments:period_close')

@login_required
def report_cards(request):
    school = get_school(request)
    ay, sem = get_active_term(request)
    
    sections = Section.objects.filter(school=school)
    
    section_id = request.GET.get('section_id')
    results = []
    selected_section = None
    
    if section_id:
        selected_section = get_object_or_404(Section, id=section_id, school=school)
        results = AcademicPeriodResult.objects.filter(
            school=school, period=sem, enrollment__section=selected_section, is_published=True
        ).select_related('enrollment__student').order_by('section_rank')
        
    return render(request, 'assessments/report_cards.html', {
        'sections': sections,
        'selected_section': selected_section,
        'results': results,
        'ay': ay,
        'sem': sem,
    })


@login_required
def manage_mark_locks(request):
    """
    Control center for locking and unlocking mark entry by:
    - Grade (e.g. Grade 10)
    - Subject (e.g. Biology)
    - Teacher (e.g. Dawit Tadesse)
    - Section / Targeted combination
    """
    if not check_admin_access(request.user):
        messages.error(request, "Unauthorized access: Mark locking is restricted to School Administration.")
        return redirect('index')

    school = get_school(request)
    ay, sem = get_active_term(request)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_lock':
            lock_type = request.POST.get('lock_type', 'CUSTOM')
            grade_id = request.POST.get('grade_id') or None
            subject_id = request.POST.get('subject_id') or None
            teacher_id = request.POST.get('teacher_id') or None
            section_id = request.POST.get('section_id') or None
            reason = request.POST.get('reason', '').strip()

            grade = Grade.objects.filter(id=grade_id, school=school).first() if grade_id else None
            subject = Subject.objects.filter(id=subject_id, school=school).first() if subject_id else None
            teacher = User.objects.filter(id=teacher_id, school=school).first() if teacher_id else None
            section = Section.objects.filter(id=section_id, school=school).first() if section_id else None

            if not (grade or subject or teacher or section):
                messages.error(request, "Please select at least one target to lock (Grade, Subject, Teacher, or Section).")
            else:
                lock_obj, created = MarkEntryLock.objects.update_or_create(
                    school=school,
                    grade=grade,
                    subject=subject,
                    teacher=teacher,
                    section=section,
                    defaults={
                        'lock_type': lock_type,
                        'academic_year': ay,
                        'period': sem,
                        'reason': reason or "Locked by Administrator",
                        'is_active': True,
                        'locked_by': request.user
                    }
                )
                AuditService.log_action(
                    school=school,
                    user=request.user,
                    action="MARK_LOCK_CREATED",
                    object_type="MarkEntryLock",
                    object_id=str(lock_obj.id),
                    after_val={
                        'lock_type': lock_type,
                        'grade': grade.name if grade else None,
                        'subject': subject.name if subject else None,
                        'teacher': teacher.username if teacher else None,
                        'reason': reason
                    },
                    ip_address=AuditService.get_client_ip(request)
                )
                messages.success(request, f"Mark entry lock created: {str(lock_obj)}")

        elif action == 'quick_lock_grade':
            grade_id = request.POST.get('grade_id')
            grade = get_object_or_404(Grade, id=grade_id, school=school)
            lock_obj, _ = MarkEntryLock.objects.update_or_create(
                school=school,
                grade=grade,
                subject=None,
                teacher=None,
                section=None,
                defaults={
                    'lock_type': 'GRADE',
                    'academic_year': ay,
                    'period': sem,
                    'is_active': True,
                    'reason': f"Grade {grade.name} mark entry locked by Administrator",
                    'locked_by': request.user
                }
            )
            AuditService.log_action(
                school=school,
                user=request.user,
                action="MARK_LOCK_GRADE",
                object_type="Grade",
                object_id=str(grade.id),
                after_val={'grade': grade.name},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Mark entry LOCKED for all sections and subjects in {grade.name}.")

        elif action == 'unlock_all':
            count = MarkEntryLock.objects.filter(school=school, is_active=True).update(is_active=False)
            AuditService.log_action(
                school=school,
                user=request.user,
                action="MARK_LOCKS_UNLOCKED_ALL",
                object_type="MarkEntryLock",
                object_id=str(count),
                after_val={'unlocked_count': count},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"All mark entry locks deactivated ({count} lock rules unlocked).")

        return redirect('assessments:manage_locks')

    # GET
    locks = MarkEntryLock.objects.filter(school=school).select_related(
        'grade', 'subject', 'teacher', 'section', 'locked_by', 'period'
    ).order_by('-is_active', '-created_at')

    grades = Grade.objects.filter(school=school).order_by('level', 'stream_type')
    subjects = Subject.objects.filter(school=school).order_by('name')
    teachers = User.objects.filter(school=school, role=UserRole.TEACHER).order_by('first_name', 'last_name')
    sections = Section.objects.filter(school=school).select_related('grade').order_by('grade__level', 'name')

    total_active = locks.filter(is_active=True).count()
    grade_locks_count = locks.filter(is_active=True, grade__isnull=False, subject__isnull=True, teacher__isnull=True).count()
    subject_locks_count = locks.filter(is_active=True, subject__isnull=False).count()
    teacher_locks_count = locks.filter(is_active=True, teacher__isnull=False).count()

    return render(request, 'assessments/mark_entry_locks.html', {
        'locks': locks,
        'grades': grades,
        'subjects': subjects,
        'teachers': teachers,
        'sections': sections,
        'total_active': total_active,
        'grade_locks_count': grade_locks_count,
        'subject_locks_count': subject_locks_count,
        'teacher_locks_count': teacher_locks_count,
        'ay': ay,
        'sem': sem,
    })


@login_required
def toggle_mark_lock(request, lock_id):
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    lock = get_object_or_404(MarkEntryLock, id=lock_id, school=school)
    lock.is_active = not lock.is_active
    lock.save(update_fields=['is_active'])

    AuditService.log_action(
        school=school,
        user=request.user,
        action="MARK_LOCK_TOGGLED",
        object_type="MarkEntryLock",
        object_id=str(lock.id),
        after_val={'is_active': lock.is_active, 'rule': str(lock)},
        ip_address=AuditService.get_client_ip(request)
    )

    status_str = "LOCKED" if lock.is_active else "UNLOCKED"
    messages.success(request, f"Mark entry rule is now {status_str}: {str(lock)}")
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer or 'assessments:manage_locks')


@login_required
def delete_mark_lock(request, lock_id):
    if not check_admin_access(request.user) or request.method != 'POST':
        return HttpResponse("Unauthorized", status=403)

    school = get_school(request)
    lock = get_object_or_404(MarkEntryLock, id=lock_id, school=school)
    lock_desc = str(lock)
    lock.delete()

    AuditService.log_action(
        school=school,
        user=request.user,
        action="MARK_LOCK_DELETED",
        object_type="MarkEntryLock",
        object_id=str(lock_id),
        after_val={'rule_deleted': lock_desc},
        ip_address=AuditService.get_client_ip(request)
    )

    messages.success(request, f"Lock rule removed: {lock_desc}")
    return redirect('assessments:manage_locks')


@login_required
def quick_toggle_grid_lock(request):
    """
    Instant lock/unlock toggle directly from the mark entry grid toolbar:
    - Assessment Component (individual component lock e.g. Midterm only)
    - Section & Subject (class mark-list lock)
    - Grade, Subject, or Teacher
    Teachers can lock/unlock their own assigned classes or components.
    """
    if request.method != 'POST':
        return HttpResponse("Method not allowed", status=405)

    school = get_school(request)
    ay, sem = get_active_term(request)
    target_type = request.POST.get('target_type')  # 'component', 'section_subject', 'grade', 'subject', 'teacher'
    target_id = request.POST.get('target_id')
    section_id = request.POST.get('section_id')
    reason = request.POST.get('reason', '').strip()
    referer = request.POST.get('referer') or request.META.get('HTTP_REFERER')

    is_admin = check_admin_access(request.user)
    is_teacher = (request.user.role == UserRole.TEACHER)

    from django.utils import timezone

    if target_type == 'component':
        comp_obj = get_object_or_404(AssessmentComponent, id=target_id, school=school)
        sec_obj = get_object_or_404(Section, id=section_id, school=school) if section_id else None

        if is_teacher and not is_admin:
            is_assigned = TeacherAssignment.objects.filter(
                school=school, teacher__user=request.user, section=sec_obj, subject=comp_obj.subject
            ).exists()
            if not is_assigned:
                return HttpResponse("Unauthorized: You are not assigned to this class.", status=403)

        existing = MarkEntryLock.objects.filter(
            school=school, assessment_component=comp_obj, section=sec_obj
        ).first()

        if existing and existing.is_active:
            existing.is_active = False
            existing.unlocked_by = request.user
            existing.unlocked_at = timezone.now()
            existing.unlock_reason = reason or "Unlocked by authorized user"
            existing.save(update_fields=['is_active', 'unlocked_by', 'unlocked_at', 'unlock_reason'])
            AuditService.log_action(
                school=school, user=request.user, action="MARK_LOCK_COMPONENT_UNLOCKED",
                object_type="AssessmentComponent", object_id=str(comp_obj.id),
                after_val={'component': comp_obj.name, 'reason': existing.unlock_reason},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Component '{comp_obj.name}' mark entry UNLOCKED.")
        else:
            lock_obj, _ = MarkEntryLock.objects.update_or_create(
                school=school, assessment_component=comp_obj, section=sec_obj,
                defaults={
                    'lock_type': 'COMPONENT',
                    'academic_year': ay,
                    'period': sem,
                    'subject': comp_obj.subject,
                    'grade': sec_obj.grade if sec_obj else comp_obj.subject.grade,
                    'is_active': True,
                    'reason': reason or f"Component '{comp_obj.name}' locked by {request.user.get_full_name() or request.user.username}",
                    'locked_by': request.user
                }
            )
            AuditService.log_action(
                school=school, user=request.user, action="MARK_LOCK_COMPONENT_LOCKED",
                object_type="AssessmentComponent", object_id=str(comp_obj.id),
                after_val={'component': comp_obj.name, 'reason': lock_obj.reason},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Component '{comp_obj.name}' mark entry LOCKED.")

    elif target_type == 'section_subject':
        subj_obj = get_object_or_404(Subject, id=target_id, school=school)
        sec_obj = get_object_or_404(Section, id=section_id, school=school)

        if is_teacher and not is_admin:
            is_assigned = TeacherAssignment.objects.filter(
                school=school, teacher__user=request.user, section=sec_obj, subject=subj_obj
            ).exists()
            if not is_assigned:
                return HttpResponse("Unauthorized: You are not assigned to this class.", status=403)

        existing = MarkEntryLock.objects.filter(
            school=school, subject=subj_obj, section=sec_obj, assessment_component__isnull=True
        ).first()

        if existing and existing.is_active:
            existing.is_active = False
            existing.unlocked_by = request.user
            existing.unlocked_at = timezone.now()
            existing.unlock_reason = reason or "Unlocked by authorized user"
            existing.save(update_fields=['is_active', 'unlocked_by', 'unlocked_at', 'unlock_reason'])
            AuditService.log_action(
                school=school, user=request.user, action="MARK_LOCK_SECTION_SUBJECT_UNLOCKED",
                object_type="Subject", object_id=str(subj_obj.id),
                after_val={'subject': subj_obj.name, 'section': sec_obj.name, 'reason': existing.unlock_reason},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Marks UNLOCKED for {subj_obj.name} ({sec_obj.name}).")
        else:
            lock_obj, _ = MarkEntryLock.objects.update_or_create(
                school=school, subject=subj_obj, section=sec_obj, assessment_component__isnull=True,
                defaults={
                    'lock_type': 'SECTION',
                    'academic_year': ay,
                    'period': sem,
                    'grade': sec_obj.grade,
                    'is_active': True,
                    'reason': reason or f"Class mark-list locked by {request.user.get_full_name() or request.user.username}",
                    'locked_by': request.user
                }
            )
            AuditService.log_action(
                school=school, user=request.user, action="MARK_LOCK_SECTION_SUBJECT_LOCKED",
                object_type="Subject", object_id=str(subj_obj.id),
                after_val={'subject': subj_obj.name, 'section': sec_obj.name, 'reason': lock_obj.reason},
                ip_address=AuditService.get_client_ip(request)
            )
            messages.success(request, f"Marks LOCKED for {subj_obj.name} ({sec_obj.name}).")

    elif not is_admin:
        return HttpResponse("Unauthorized: Broad administrative locking requires School Admin role.", status=403)

    elif target_type == 'grade':
        target_obj = get_object_or_404(Grade, id=target_id, school=school)
        existing = MarkEntryLock.objects.filter(school=school, grade=target_obj, subject__isnull=True, teacher__isnull=True, section__isnull=True).first()
        if existing and existing.is_active:
            existing.is_active = False
            existing.unlocked_by = request.user
            existing.unlocked_at = timezone.now()
            existing.unlock_reason = reason or "Unlocked by Administrator"
            existing.save(update_fields=['is_active', 'unlocked_by', 'unlocked_at', 'unlock_reason'])
            messages.success(request, f"Grade {target_obj.name} mark entry UNLOCKED.")
        else:
            MarkEntryLock.objects.update_or_create(
                school=school, grade=target_obj, subject__isnull=True, teacher__isnull=True, section__isnull=True,
                defaults={'lock_type': 'GRADE', 'academic_year': ay, 'period': sem, 'is_active': True, 'reason': reason or f"Grade {target_obj.name} locked via Gradebook", 'locked_by': request.user}
            )
            messages.success(request, f"Grade {target_obj.name} mark entry LOCKED.")

    elif target_type == 'subject':
        target_obj = get_object_or_404(Subject, id=target_id, school=school)
        existing = MarkEntryLock.objects.filter(school=school, subject=target_obj, grade__isnull=True, teacher__isnull=True, section__isnull=True, assessment_component__isnull=True).first()
        if existing and existing.is_active:
            existing.is_active = False
            existing.unlocked_by = request.user
            existing.unlocked_at = timezone.now()
            existing.unlock_reason = reason or "Unlocked by Administrator"
            existing.save(update_fields=['is_active', 'unlocked_by', 'unlocked_at', 'unlock_reason'])
            messages.success(request, f"Subject {target_obj.name} mark entry UNLOCKED.")
        else:
            MarkEntryLock.objects.update_or_create(
                school=school, subject=target_obj, grade__isnull=True, teacher__isnull=True, section__isnull=True, assessment_component__isnull=True,
                defaults={'lock_type': 'SUBJECT', 'academic_year': ay, 'period': sem, 'is_active': True, 'reason': reason or f"Subject {target_obj.name} locked via Gradebook", 'locked_by': request.user}
            )
            messages.success(request, f"Subject {target_obj.name} mark entry LOCKED.")

    elif target_type == 'teacher':
        target_obj = get_object_or_404(User, id=target_id, school=school)
        existing = MarkEntryLock.objects.filter(school=school, teacher=target_obj, grade__isnull=True, subject__isnull=True).first()
        if existing and existing.is_active:
            existing.is_active = False
            existing.unlocked_by = request.user
            existing.unlocked_at = timezone.now()
            existing.unlock_reason = reason or "Unlocked by Administrator"
            existing.save(update_fields=['is_active', 'unlocked_by', 'unlocked_at', 'unlock_reason'])
            messages.success(request, f"Teacher {target_obj.get_full_name() or target_obj.username} mark entry UNLOCKED.")
        else:
            MarkEntryLock.objects.update_or_create(
                school=school, teacher=target_obj, grade__isnull=True, subject__isnull=True,
                defaults={'lock_type': 'TEACHER', 'academic_year': ay, 'period': sem, 'is_active': True, 'reason': reason or f"Teacher locked via Gradebook", 'locked_by': request.user}
            )
            messages.success(request, f"Teacher {target_obj.get_full_name() or target_obj.username} mark entry LOCKED.")

    return redirect(referer or 'assessments:mark_entry')

