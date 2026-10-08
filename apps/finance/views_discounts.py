import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum

from apps.accounts.models import UserRole
from apps.finance.models import (
    DiscountPolicy, DiscountType, DiscountCategory, StudentDiscount,
    StudentInvoice, FeeCategory
)
from apps.finance.discount_service import DiscountService
from apps.academics.models import AcademicYear, Grade
from apps.students.models import StudentProfile
from apps.parents.models import ParentProfile, GuardianRelationship

logger = logging.getLogger(__name__)


@login_required
def discounts_dashboard(request):
    school = getattr(request, 'school', None)
    if not school and getattr(request.user, 'school', None):
        school = request.user.school

    if request.user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.ACCOUNTANT, UserRole.PRINCIPAL]:
        messages.error(request, "Unauthorized access to Discount & Scholarship Management.")
        return redirect('finance:dashboard')

    current_ay = getattr(request, 'academic_year', None)
    if not current_ay:
        current_ay = AcademicYear.objects.filter(school=school, is_active=True).first()

    # Ensure default Ethiopian policies exist if none
    if not DiscountPolicy.objects.filter(school=school).exists():
        DiscountService.ensure_default_policies(school)

    # Handle POST Actions
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_policy':
            name = request.POST.get('name', '').strip()
            category = request.POST.get('discount_category', DiscountCategory.CUSTOM)
            disc_type = request.POST.get('discount_type', DiscountType.PERCENTAGE)
            val = request.POST.get('value', '0')
            sibling_order = request.POST.get('sibling_order')
            fee_cat_id = request.POST.get('fee_category_id')
            auto_apply = request.POST.get('auto_apply') == 'on'
            description = request.POST.get('description', '')

            try:
                fee_cat = FeeCategory.objects.get(id=fee_cat_id, school=school) if fee_cat_id else None
                order_val = int(sibling_order) if sibling_order and sibling_order.isdigit() else None

                DiscountPolicy.objects.create(
                    school=school,
                    name=name,
                    discount_category=category,
                    discount_type=disc_type,
                    value=Decimal(val),
                    sibling_order=order_val,
                    fee_category=fee_cat,
                    auto_apply=auto_apply,
                    description=description
                )
                messages.success(request, f"Discount policy '{name}' created successfully.")
            except Exception as e:
                messages.error(request, f"Error creating discount policy: {str(e)}")
            return redirect('finance:discounts_dashboard')

        elif action == 'toggle_policy':
            policy_id = request.POST.get('policy_id')
            policy = get_object_or_404(DiscountPolicy, id=policy_id, school=school)
            policy.is_active = not policy.is_active
            policy.save()
            status_str = "activated" if policy.is_active else "deactivated"
            messages.success(request, f"Policy '{policy.name}' {status_str}.")
            return redirect('finance:discounts_dashboard')

        elif action == 'assign_student_discount':
            student_id = request.POST.get('student_id')
            policy_id = request.POST.get('policy_id')
            ay_id = request.POST.get('academic_year_id') or (current_ay.id if current_ay else None)
            notes = request.POST.get('notes', '')

            try:
                student = StudentProfile.objects.get(id=student_id, school=school)
                policy = DiscountPolicy.objects.get(id=policy_id, school=school)
                ay = AcademicYear.objects.get(id=ay_id, school=school)

                sd, created = StudentDiscount.objects.update_or_create(
                    school=school,
                    student=student,
                    academic_year=ay,
                    discount_policy=policy,
                    defaults={
                        'approved_by': request.user,
                        'is_active': True,
                        'notes': notes
                    }
                )

                # Reapply to current student's invoice for this year
                inv = StudentInvoice.objects.filter(school=school, student=student, academic_year=ay).first()
                if inv:
                    DiscountService.apply_discount_to_invoice(inv, policy=policy, user=request.user)

                messages.success(request, f"Assigned {policy.name} to {student.full_name}.")
            except Exception as e:
                messages.error(request, f"Error assigning discount: {str(e)}")
            return redirect('finance:discounts_dashboard')

        elif action == 'batch_recalculate':
            if current_ay:
                result = DiscountService.batch_apply_discounts(school=school, academic_year=current_ay)
                messages.success(
                    request,
                    f"Recalculated discounts for {result['processed_count']} invoices. "
                    f"Awarded discounts on {result['discounted_count']} invoices (Total: ETB {result['total_discount_awarded']:,.2f})."
                )
            else:
                messages.error(request, "No active academic year found for recalculation.")
            return redirect('finance:discounts_dashboard')

    # Data fetching
    policies = DiscountPolicy.objects.filter(school=school).select_related('fee_category').order_by('discount_category', 'sibling_order')
    student_discounts = StudentDiscount.objects.filter(school=school).select_related('student', 'discount_policy', 'academic_year', 'approved_by')[:50]
    
    fee_categories = FeeCategory.objects.filter(school=school)
    academic_years = AcademicYear.objects.filter(school=school)
    students = StudentProfile.objects.filter(school=school, status='ACTIVE').order_by('first_name')[:100]

    # Metrics
    total_discounts_awarded = StudentInvoice.objects.filter(school=school).aggregate(total=Sum('discount_amount'))['total'] or Decimal('0.00')
    invoices_with_discount = StudentInvoice.objects.filter(school=school, discount_amount__gt=Decimal('0.00')).count()

    # Discover multi-child families
    parents_with_multiple_children = ParentProfile.objects.filter(school=school).annotate(
        child_count=Count('guardianships__student', distinct=True)
    ).filter(child_count__gte=2).select_related('user')

    family_groups = []
    for p in parents_with_multiple_children[:15]:
        children = []
        for g in p.guardianships.select_related('student').all():
            st = g.student
            info = DiscountService.detect_sibling_info(st)
            children.append({
                'student': st,
                'order': info['sibling_order'],
                'has_discount': StudentInvoice.objects.filter(school=school, student=st, discount_amount__gt=0).exists()
            })
        family_groups.append({
            'parent': p,
            'children': sorted(children, key=lambda c: c['order'])
        })

    return render(request, 'finance/discounts_dashboard.html', {
        'policies': policies,
        'student_discounts': student_discounts,
        'fee_categories': fee_categories,
        'academic_years': academic_years,
        'students': students,
        'current_ay': current_ay,
        'total_discounts_awarded': total_discounts_awarded,
        'invoices_with_discount': invoices_with_discount,
        'family_groups': family_groups,
        'discount_categories': DiscountCategory.choices,
        'discount_types': DiscountType.choices,
    })
