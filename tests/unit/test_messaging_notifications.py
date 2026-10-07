import pytest
from django.urls import reverse
from apps.accounts.models import User, UserRole
from apps.schools.models import School
from apps.messaging.models import Conversation, Message
from apps.messaging.context_processors import unread_messages_context
from django.test import RequestFactory


@pytest.mark.django_db
class TestMessagingNotifications:

    def setup_method(self):
        self.school = School.objects.create(name="Notification Academy", code="NOTIF_SCH")
        self.sender = User.objects.create_user(
            username="sender_teacher",
            password="testpassword123",
            role=UserRole.TEACHER,
            school=self.school,
            first_name="Abebe",
            last_name="Kebede"
        )
        self.recipient = User.objects.create_user(
            username="recipient_parent",
            password="testpassword123",
            role=UserRole.PARENT,
            school=self.school,
            first_name="Almaz",
            last_name="Tadesse"
        )
        self.factory = RequestFactory()

    def test_unread_messages_context_processor(self):
        # Create conversation and unread message
        conv = Conversation.objects.create(
            school=self.school,
            subject="Student Progress Discussion",
            created_by=self.sender
        )
        conv.participants.add(self.sender, self.recipient)
        msg1 = Message.objects.create(
            school=self.school,
            conversation=conv,
            sender=self.sender,
            body="Hello parent, your child did great on the exam!"
        )

        request = self.factory.get('/portals/parent/')
        request.user = self.recipient
        request.school = self.school

        context = unread_messages_context(request)
        assert context['unread_messages_count'] == 1

        # Sender should have 0 unread
        request_sender = self.factory.get('/portals/teacher/')
        request_sender.user = self.sender
        request_sender.school = self.school
        assert unread_messages_context(request_sender)['unread_messages_count'] == 0

        # Mark message read
        msg1.is_read = True
        msg1.save()
        assert unread_messages_context(request)['unread_messages_count'] == 0

    def test_unread_count_api_endpoint(self, client):
        client.login(username="recipient_parent", password="testpassword123")
        
        # Initial check should be 0
        url = reverse('messaging:unread_count_api')
        res = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res.status_code == 200
        data = res.json()
        assert data['unread_count'] == 0
        assert data['latest_message'] is None

        # Add message
        conv = Conversation.objects.create(
            school=self.school,
            subject="Urgent Notice",
            created_by=self.sender
        )
        conv.participants.add(self.sender, self.recipient)
        Message.objects.create(
            school=self.school,
            conversation=conv,
            sender=self.sender,
            body="Meeting scheduled for tomorrow at 10 AM."
        )

        res2 = client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2['unread_count'] == 1
        assert data2['latest_message'] is not None
        assert "Abebe Kebede" in data2['latest_message']['sender']
        assert "Meeting scheduled" in data2['latest_message']['body']
