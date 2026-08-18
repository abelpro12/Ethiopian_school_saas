import datetime
from django.db import models
from apps.tenants.models import TenantAwareModel
from apps.accounts.models import User
from apps.students.models import StudentProfile


class BookStatus(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Available'
    BORROWED = 'BORROWED', 'Borrowed Out'
    LOST = 'LOST', 'Lost / Missing'
    DAMAGED = 'DAMAGED', 'Damaged'
    RESERVED = 'RESERVED', 'Reserved'


class BookCategory(models.TextChoices):
    TEXTBOOK = 'TEXTBOOK', 'Textbook'
    REFERENCE = 'REFERENCE', 'Reference'
    FICTION = 'FICTION', 'Fiction / Literature'
    NONFICTION = 'NONFICTION', 'Non-Fiction'
    SCIENCE = 'SCIENCE', 'Science & Technology'
    HISTORY = 'HISTORY', 'History & Social Studies'
    RELIGION = 'RELIGION', 'Religion / Ethics'
    MAGAZINE = 'MAGAZINE', 'Magazine / Periodical'
    OTHER = 'OTHER', 'Other'


class Book(TenantAwareModel):
    """Library book record (the bibliographic entity)."""
    title = models.CharField(max_length=300)
    author = models.CharField(max_length=200, blank=True, null=True)
    isbn = models.CharField(max_length=20, blank=True, null=True)
    publisher = models.CharField(max_length=200, blank=True, null=True)
    publication_year = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=30, choices=BookCategory.choices, default=BookCategory.TEXTBOOK)
    subject = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Mathematics, Physics")
    grade_level = models.CharField(max_length=50, blank=True, null=True, help_text="e.g. Grade 9-10")
    description = models.TextField(blank=True, null=True)
    cover_image = models.ImageField(upload_to='library/covers/', blank=True, null=True)
    total_copies = models.IntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('school', 'isbn')
        ordering = ['title']

    def __str__(self):
        return f"{self.title} by {self.author or 'Unknown'}"

    @property
    def available_copies(self):
        borrowed = self.copies.filter(status=BookStatus.BORROWED).count()
        return self.total_copies - borrowed

    @property
    def is_available(self):
        return self.available_copies > 0


class BookCopy(TenantAwareModel):
    """A physical copy of a book."""
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='copies')
    copy_number = models.CharField(max_length=20)  # e.g., "COPY-001"
    status = models.CharField(max_length=20, choices=BookStatus.choices, default=BookStatus.AVAILABLE)
    condition_notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('school', 'book', 'copy_number')

    def __str__(self):
        return f"{self.book.title} - Copy #{self.copy_number} ({self.status})"


class BorrowRecord(TenantAwareModel):
    """Tracks borrowing of library books by students or staff."""
    book_copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE, related_name='borrow_records')
    borrower_student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='library_borrows')
    borrower_staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='library_borrows')
    borrowed_date = models.DateField(default=datetime.date.today)
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_books')
    returned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_books')
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-borrowed_date']

    def __str__(self):
        borrower = self.borrower_student.full_name if self.borrower_student else (self.borrower_staff.get_full_name() if self.borrower_staff else "Unknown")
        return f"{self.book_copy.book.title} → {borrower} (Due: {self.due_date})"

    @property
    def is_returned(self):
        return self.return_date is not None

    @property
    def is_overdue(self):
        if self.return_date:
            return False
        return self.due_date < datetime.date.today()

    @property
    def overdue_days(self):
        if self.is_overdue:
            return (datetime.date.today() - self.due_date).days
        return 0
