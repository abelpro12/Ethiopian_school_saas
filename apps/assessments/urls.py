from django.urls import path
from . import views, annual_views, views_grading, views_interventions

app_name = 'assessments'

urlpatterns = [
    path('components/', views.manage_components, name='components'),
    path('marks/entry/', views.mark_entry, name='mark_entry'),
    path('marks/entry/<int:section_id>/<int:subject_id>/', views.mark_entry_grid, name='mark_entry_grid'),
    path('marks/save/', views.save_marks, name='save_marks'),
    path('marks/review/', views.mark_review, name='review'),
    path('marks/approve/', views.approve_marks, name='approve_marks'),
    path('period-close/', views.period_close, name='period_close'),
    path('period-lock/<int:period_id>/toggle/', views.toggle_period_lock, name='toggle_period_lock'),
    path('locks/', views.manage_mark_locks, name='manage_locks'),
    path('locks/<int:lock_id>/toggle/', views.toggle_mark_lock, name='toggle_mark_lock'),
    path('locks/<int:lock_id>/delete/', views.delete_mark_lock, name='delete_mark_lock'),
    path('locks/quick-toggle/', views.quick_toggle_grid_lock, name='quick_toggle_grid_lock'),
    path('report-cards/', views.report_cards, name='report_cards'),

    # Flexible Grading Scale & Policy Routes
    path('grading-scales/', views_grading.grading_scale_list, name='grading_scales'),
    path('grading-scales/save/', views_grading.save_grading_scale, name='save_grading_scale'),
    path('grading-scales/rule/save/', views_grading.save_grading_rule, name='save_grading_rule'),
    path('grading-scales/rule/<int:rule_id>/delete/', views_grading.delete_grading_rule, name='delete_grading_rule'),
    path('grading-scales/<int:scale_id>/set-default/', views_grading.set_default_grading_scale, name='set_default_grading_scale'),

    # Academic Intervention & Performance Tracking Routes
    path('interventions/', views_interventions.intervention_dashboard, name='interventions'),
    path('interventions/create/', views_interventions.create_intervention_view, name='create_intervention'),
    path('interventions/<int:pk>/update/', views_interventions.update_intervention_view, name='update_intervention'),
    path('interventions/<int:pk>/sms/', views_interventions.send_parent_sms_view, name='send_parent_sms'),

    # Annual Promotion Engine
    path('annual-dashboard/', annual_views.annual_dashboard, name='annual_dashboard'),
    path('annual-calculate-all/', annual_views.calculate_all_annual_results, name='calculate_all_annual_results'),
    path('annual-calculate/<int:section_id>/', annual_views.calculate_annual_results, name='calculate_annual_results'),
    path('annual-review/<int:section_id>/', annual_views.annual_review, name='annual_review'),
    path('annual-rollover/<int:section_id>/', annual_views.execute_rollover, name='execute_rollover'),
    path('annual-rollover-all/', annual_views.execute_all_rollovers, name='execute_all_rollovers'),
]

