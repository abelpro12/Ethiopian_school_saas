from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from apps.support.models import SupportTicket, TicketMessage, TicketStatus, TicketPriority


@login_required
def support_tickets_list_create_view(request):
    """
    List or create support tickets for a school.
    """
    school = request.school

    if request.method == 'POST':
        subject = request.POST.get('subject', 'General Inquiry')
        desc = request.POST.get('description', '')
        priority = request.POST.get('priority', TicketPriority.MEDIUM)

        ticket = SupportTicket.objects.create(
            school=school,
            subject=subject,
            description=desc,
            priority=priority,
            created_by=request.user
        )

        return JsonResponse({
            'status': 'success',
            'ticket_id': ticket.id,
            'message': 'Support ticket submitted successfully.'
        })

    tickets = SupportTicket.objects.filter(school=school).order_by('-created_at')
    data = [{
        'id': t.id,
        'subject': t.subject,
        'priority': t.priority,
        'status': t.status,
        'created_at': t.created_at.strftime('%Y-%m-%d %H:%M')
    } for t in tickets]

    return JsonResponse({'tickets': data})
