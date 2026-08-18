from django.db import models

class UserRole(models.TextChoices):
    SUPER_ADMIN = 'SUPER_ADMIN', 'Platform Super Admin'
    SCHOOL_ADMIN = 'SCHOOL_ADMIN', 'School Admin'
    PRINCIPAL = 'PRINCIPAL', 'Principal'
    REGISTRAR = 'REGISTRAR', 'Registrar'
    ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
    TEACHER = 'TEACHER', 'Teacher'
    STUDENT = 'STUDENT', 'Student'
    PARENT = 'PARENT', 'Parent/Guardian'
