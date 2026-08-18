import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.db.models import Sum, Avg, F, Count, Q
from django.db import transaction

from apps.accounts.models import UserRole
from apps.academics.models import Subject, Section, AcademicYear, AcademicPeriod, Grade, Stream
from apps.enrollment.models import StudentEnrollment, EnrollmentStatus
from apps.assessments.models import AssessmentComponent, StudentMark, MarkStatus, AcademicPeriodResult
from apps.teachers.models import TeacherAssignment
from apps.platform_management.decorators import school_context_required
from apps.attendance.models import AttendanceRecord, AttendanceStatus

def get_school(request):
    return getattr(request, 'school', None) or getattr(request.user, 'school', None)

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
            overwrite_existing = request.POST.get('overwrite_existing') == 'true'

            if not source_year_id:
                messages.error(request, "Please select a source past academic year.")
            else:
                try:
                    source_year = AcademicYear.objects.get(id=source_year_id, school=school)
                    source_sem = AcademicPeriod.objects.filter(
                        school=school, academic_year=source_year, period_type=sem.period_type
                    ).first() or AcademicPeriod.objects.filter(school=school, academic_year=source_year).first()

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
                            messages.warning(request, f"No assessment components found in {source_year.name} for the selected criteria.")
                        else:
                            # Map unique schemes per (grade level/stream_type) and a flat list of definitions
                            grade_stream_schemes = {}
                            flat_defs = []
                            for sc in source_comps:
                                if sc.subject and sc.subject.grade:
                                    g_key = (sc.subject.grade.level, sc.subject.grade.stream_type)
                                    if g_key not in grade_stream_schemes:
                                        grade_stream_schemes[g_key] = []
                                    if not any(d['name'] == sc.name for d in grade_stream_schemes[g_key]):
                                        grade_stream_schemes[g_key].append({
                                            'name': sc.name,
                                            'weight': sc.weight,
                                            'max_marks': sc.max_marks
                                        })
                                if not any(d['name'] == sc.name for d in flat_defs):
                                    flat_defs.append({
                                        'name': sc.name,
                                        'weight': sc.weight,
                                        'max_marks': sc.max_marks
                                    })

                            imported_count = 0
                            with transaction.atomic():
                                if target_grade_id:
                                    # Targeted to a specific grade and stream
                                    t_subjects = Subject.objects.filter(school=school, grade_id=target_grade_id)
                                    if target_stream_id:
                                        t_subjects = t_subjects.filter(stream_id=target_stream_id)

                                    for c_def in flat_defs:
                                        for subj in t_subjects:
                                            if overwrite_existing:
                                                _, created = AssessmentComponent.objects.update_or_create(
                                                    school=school,
                                                    academic_year=ay,
                                                    period=target_period,
                                                    subject=subj,
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
                                                    subject=subj,
                                                    name=c_def['name'],
                                                    defaults={
                                                        'weight': c_def['weight'],
                                                        'max_marks': c_def['max_marks']
                                                    }
                                                )
                                                if created:
                                                    imported_count += 1
                                else:
                                    # Auto-map across all matching grades & streams
                                    for (g_level, g_stream_type), comp_defs in grade_stream_schemes.items():
                                        target_grades = grades.filter(level=g_level, stream_type=g_stream_type)
                                        for tg in target_grades:
                                            tg_subjects = Subject.objects.filter(school=school, grade=tg)
                                            if target_stream_id:
                                                tg_subjects = tg_subjects.filter(stream_id=target_stream_id)
                                            for c_def in comp_defs:
                                                for subj in tg_subjects:
                                                    if overwrite_existing:
                                                        _, created = AssessmentComponent.objects.update_or_create(
                                                            school=school,
                                                            academic_year=ay,
                                                            period=target_period,
                                                            subject=subj,
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
                                                            subject=subj,
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
                                f"Successfully replicated assessment schemes from {source_year.name} into {ay.name}! ({imported_count} components mapped across target grades, sections & streams)."
                            )
                except Exception as e:
                    messages.error(request, f"Error replicating past year assessment scheme: {e}")

        elif action == 'seed_standard_scheme':
            target_grade_id = request.POST.get('grade_id')
            preset = request.POST.get('preset', 'STANDARD_5')
            
            if preset == 'STANDARD_5':
                # Standard Ethiopian MoE 5-Component Scheme (Total 100%)
                scheme_defs = [
                    {'name': 'Class Activity / Assignment', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Quiz & Homework', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Project / Practical Work', 'weight': 10.0, 'max_marks': 10.0},
                    {'name': 'Midterm Exam', 'weight': 20.0, 'max_marks': 20.0},
                    {'name': 'Final Exam', 'weight': 50.0, 'max_marks': 50.0},
                ]
            elif preset == 'STANDARD_3':
                # 3-Component Scheme (Total 100%)
                scheme_defs = [
                    {'name': 'Continuous Assessment (CA)', 'weight': 30.0, 'max_marks': 30.0},
                    {'name': 'Midterm Examination', 'weight': 20.0, 'max_marks': 20.0},
                    {'name': 'Final Examination', 'weight': 50.0, 'max_marks': 50.0},
                ]
            else:
                # 4-Component Scheme (Total 100%)
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
                for comp_def in scheme_defs:
                    for subj in target_subjects:
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
                    # Get unique component definitions from source grade
                    unique_defs = {}
                    for c in source_comps:
                        if c.name not in unique_defs:
                            unique_defs[c.name] = {'weight': c.weight, 'max_marks': c.max_marks}

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
                            for c_name, c_props in unique_defs.items():
                                for subj in tg_subjects:
                                    if overwrite_existing:
                                        _, was_created = AssessmentComponent.objects.update_or_create(
                                            school=school,
                                            academic_year=ay,
                                            period=sem,
                                            subject=subj,
                                            name=c_name,
                                            defaults={
                                                'weight': c_props['weight'],
                                                'max_marks': c_props['max_marks']
                                            }
                                        )
                                        replicated_count += 1
                                    else:
                                        _, was_created = AssessmentComponent.objects.get_or_create(
                                            school=school,
                                            academic_year=ay,
                                            period=sem,
                                            subject=subj,
                                            name=c_name,
                                            defaults={
                                                'weight': c_props['weight'],
                                                'max_marks': c_props['max_marks']
                                            }
                                        )
                                        if was_created:
                                            replicated_count += 1

                    source_grade_name = Grade.objects.filter(id=source_grade_id).first()
                    messages.success(request, f"Successfully replicated assessment structure from {source_grade_name} across target grades and streams ({replicated_count} components created).")

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
        g_weight = 0.0
        g_raw = all_components_raw.filter(subject__grade=g)
        for comp in g_raw:
            k = (comp.name, comp.weight, comp.max_marks, comp.subject.stream_id if comp.subject.stream else None)
            if k not in g_seen:
                g_seen.add(k)
                comp.scope_grade = g
                comp.scope_stream = comp.subject.stream
                g_comps.append(comp)
                try:
                    g_weight += float(comp.weight)
                except (ValueError, TypeError):
                    pass

            # Also maintain unique components list for flat view
            gk = (comp.name, comp.weight, comp.max_marks, g.id, comp.subject.stream_id if comp.subject.stream else None)
            if gk not in seen_global_keys:
                seen_global_keys.add(gk)
                unique_components.append(comp)

        g_weight = round(g_weight, 2)
        grade_groups.append({
            'grade': g,
            'components': g_comps,
            'total_weight': g_weight,
            'is_valid': (g_weight == 100.0),
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
        
    return render(request, 'assessments/mark_entry_dashboard.html', {
        'assignments': assignments,
        'subjects': subjects,
        'selected_subject_id': selected_subject_id,
        'ay': ay,
        'sem': sem
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
        school=school, section=section, status=EnrollmentStatus.ACTIVE
    )
    if ay:
        enrollments_qs = enrollments_qs.filter(academic_year=ay)
    enrollments = enrollments_qs.select_related('student').order_by('student__first_name', 'student__last_name')
    if not enrollments.exists():
        enrollments = StudentEnrollment.objects.filter(
            school=school, section=section
        ).select_related('student').order_by('student__first_name', 'student__last_name')
    
    # Fetch existing marks
    existing_marks = StudentMark.objects.filter(
        school=school, enrollment__in=enrollments, assessment_component__in=components
    )

    from apps.academics.models import PeriodStatus
    is_locked = (
        sem and sem.status == PeriodStatus.LOCKED
    ) or any(m.status == MarkStatus.LOCKED for m in existing_marks)
    
    # Map for easy rendering: mark_dict[enrollment_id][component_id] = mark
    mark_dict = {e.id: {} for e in enrollments}
    status = MarkStatus.DRAFT
    
    for mark in existing_marks:
        mark_dict[mark.enrollment.id][mark.assessment_component.id] = mark
        status = mark.status

    return render(request, 'assessments/mark_entry_grid.html', {
        'section': section,
        'subject': subject,
        'components': components,
        'enrollments': enrollments,
        'mark_dict': mark_dict,
        'status': status,
        'is_locked': is_locked,
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

                        if value.strip() == "":
                            continue
                            
                        try:
                            mark_val = float(value)
                        except ValueError:
                            continue
                        
                        if mark_val > float(comp.max_marks):
                            err_msg = f"Error: Mark {mark_val} exceeds max {comp.max_marks} for {comp.name}"
                            if is_htmx:
                                return HttpResponse(f"<div class='p-2 bg-red-100 text-red-800 rounded'>{err_msg}</div>", status=400)
                            messages.error(request, err_msg)
                            return redirect(request.META.get('HTTP_REFERER', 'assessments:mark_entry'))
                            
                        enrollment = StudentEnrollment.objects.get(id=enrollment_id, school=school)
                        
                        mark_obj, created = StudentMark.objects.update_or_create(
                            school=school,
                            enrollment=enrollment,
                            assessment_component=comp,
                            defaults={
                                'mark_value': mark_val,
                                'entered_by': request.user,
                            }
                        )
                        saved_count += 1
                        saved_students.add(enrollment_id)
                        
                        if action == 'submit':
                            mark_obj.status = MarkStatus.SUBMITTED
                            mark_obj.save()
                        elif action == 'publish':
                            mark_obj.status = MarkStatus.PUBLISHED
                            mark_obj.save()
                            
            student_count = len(saved_students)
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
    
    StudentMark.objects.filter(
        school=school,
        enrollment__section_id=section_id,
        assessment_component__subject_id=subject_id,
        status=MarkStatus.SUBMITTED
    ).update(status=MarkStatus.APPROVED)
    
    messages.success(request, "Marks approved successfully.")
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
            
        # Rank computation (Simple)
        sections = Section.objects.filter(school=school)
        for section in sections:
            results = AcademicPeriodResult.objects.filter(school=school, period=sem, enrollment__section=section).order_by('-average_score')
            for i, res in enumerate(results, 1):
                res.section_rank = i
                res.save()
                
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
