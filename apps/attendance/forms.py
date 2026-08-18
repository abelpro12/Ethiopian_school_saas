from django import forms
from django.forms import modelformset_factory
from .models import AttendanceRecord, StaffAttendanceRecord, AttendanceStatus, StaffAttendanceStatus

class TakeStudentAttendanceForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['student', 'status', 'reason']
        widgets = {
            'student': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'}),
            'reason': forms.TextInput(attrs={'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md', 'placeholder': 'Optional reason'})
        }

StudentAttendanceFormSet = modelformset_factory(
    AttendanceRecord,
    form=TakeStudentAttendanceForm,
    extra=0,
    can_delete=False
)

class TakeStaffAttendanceForm(forms.ModelForm):
    class Meta:
        model = StaffAttendanceRecord
        fields = ['staff_user', 'status', 'time_in', 'time_out', 'remarks']
        widgets = {
            'staff_user': forms.HiddenInput(),
            'status': forms.Select(attrs={'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'}),
            'time_in': forms.TimeInput(attrs={'type': 'time', 'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'}),
            'time_out': forms.TimeInput(attrs={'type': 'time', 'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'}),
            'remarks': forms.TextInput(attrs={'class': 'shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md'})
        }

StaffAttendanceFormSet = modelformset_factory(
    StaffAttendanceRecord,
    form=TakeStaffAttendanceForm,
    extra=0,
    can_delete=False
)
