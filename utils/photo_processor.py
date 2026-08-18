import io
from PIL import Image
from django.core.files.base import ContentFile
from apps.students.models import StudentProfile, StudentPhotoHistory
from apps.accounts.models import User


class PhotoProcessingService:
    """
    Student Photo Management Service (Requirement 4).
    Handles profile photo uploads, image compression, 150x150 thumbnail generation,
    archiving old photos to StudentPhotoHistory, and private storage access.
    """
    @staticmethod
    def update_student_photo(student: StudentProfile, image_file, uploaded_by: User = None) -> StudentProfile:
        school = student.school

        # Open image using Pillow
        img = Image.open(image_file)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # 1. Compress main image to max 800x800
        main_img = img.copy()
        main_img.thumbnail((800, 800))
        main_io = io.BytesIO()
        main_img.save(main_io, format='JPEG', quality=85)
        main_content = ContentFile(main_io.getvalue(), name=f"student_{student.student_id}.jpg")

        # 2. Generate 150x150 thumbnail
        thumb_img = img.copy()
        thumb_img.thumbnail((150, 150))
        thumb_io = io.BytesIO()
        thumb_img.save(thumb_io, format='JPEG', quality=80)
        thumb_content = ContentFile(thumb_io.getvalue(), name=f"thumb_{student.student_id}.jpg")

        # 3. Archive existing active photo to StudentPhotoHistory
        if student.photo:
            StudentPhotoHistory.objects.filter(student=student, is_active=True).update(is_active=False)

        # 4. Save main photo & thumbnail to StudentProfile
        student.photo.save(f"photo_{student.student_id}.jpg", main_content, save=False)
        student.thumbnail.save(f"thumb_{student.student_id}.jpg", thumb_content, save=False)
        student.save()

        # 5. Add new record in StudentPhotoHistory
        StudentPhotoHistory.objects.create(
            school=school,
            student=student,
            photo=student.photo,
            thumbnail=student.thumbnail,
            uploaded_by=uploaded_by,
            is_active=True
        )

        return student
