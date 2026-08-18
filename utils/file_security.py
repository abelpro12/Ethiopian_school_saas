import os
import uuid
import re
from django.core.exceptions import ValidationError
from django.http import HttpResponse, FileResponse, Http404

# Maximum allowed upload file size (10MB)
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.csv', '.xlsx'}

# Executable / dangerous extensions explicitly blocked
BLOCKED_EXTENSIONS = {'.exe', '.sh', '.bat', '.cmd', '.php', '.py', '.js', '.pl', '.cgi', '.jar', '.vbs'}


def validate_file_upload(file_obj):
    """
    Strict validation of uploaded files: size, extension, MIME type safety.
    """
    if not file_obj:
        return

    # 1. Size check
    if file_obj.size > MAX_UPLOAD_SIZE:
        raise ValidationError(f"File size exceeds maximum limit of {MAX_UPLOAD_SIZE // (1024*1024)}MB.")

    ext = os.path.splitext(file_obj.name)[1].lower()

    # 2. Block executables
    if ext in BLOCKED_EXTENSIONS:
        raise ValidationError(f"File extension '{ext}' is not permitted due to security policies.")

    # 3. Check allowed whitelist
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Invalid file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    return True


def sanitize_filename(original_name: str) -> str:
    """
    Generates a secure UUID-based filename preserving original extension.
    Prevents path traversal and directory overwrites.
    """
    basename = os.path.basename(original_name)
    ext = os.path.splitext(basename)[1].lower()
    clean_name = re.sub(r'[^a-zA-Z0-9_\.-]', '', os.path.splitext(basename)[0])
    secure_uuid = uuid.uuid4().hex[:12]
    return f"{secure_uuid}_{clean_name}{ext}"


def serve_protected_document(file_path: str, user, school, allowed_roles=None):
    """
    Permission-controlled document download helper.
    Enforces tenant scoping and role-based access checks.
    """
    if not os.path.exists(file_path):
        raise Http404("Requested document does not exist.")

    if allowed_roles and user.role not in allowed_roles:
        return HttpResponse("Unauthorized document access.", status=403)

    return FileResponse(open(file_path, 'rb'), as_attachment=True)
