import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from apps.accounts.models import UserRole
from .models import Book, BookCopy, BorrowRecord, BookStatus
from apps.platform_management.decorators import school_context_required


@login_required
def library_catalog_view(request):
    """Library book catalog with search."""
    school = getattr(request, 'school', None)
    query = request.GET.get('q', '')
    category = request.GET.get('category', '')

    books = Book.objects.filter(school=school)
    if query:
        books = books.filter(Q(title__icontains=query) | Q(author__icontains=query) | Q(subject__icontains=query))
    if category:
        books = books.filter(category=category)

    return render(request, 'library/catalog.html', {
        'books': books,
        'query': query,
        'category': category,
        'categories': Book._meta.get_field('category').choices,
    })


@login_required
@school_context_required
def borrow_dashboard_view(request):
    """Librarian dashboard: active borrows, overdue books, quick return."""
    school = getattr(request, 'school', None)
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.LIBRARIAN]:
        messages.error(request, "Unauthorized.")
        return redirect('index')

    today = datetime.date.today()
    current_ay = getattr(request, 'academic_year', None)
    active_borrows = BorrowRecord.objects.filter(school=school, return_date__isnull=True).select_related(
        'book_copy__book', 'borrower_student', 'borrower_staff', 'issued_by'
    ).order_by('due_date')
    if current_ay:
        from apps.enrollment.models import StudentEnrollment
        from django.db.models import Prefetch
        active_borrows = active_borrows.prefetch_related(
            Prefetch(
                'borrower_student__enrollments',
                queryset=StudentEnrollment.objects.filter(academic_year=current_ay).select_related('grade', 'section'),
                to_attr='active_enrollments'
            )
        )
    overdue = [b for b in active_borrows if b.is_overdue]

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'return_book':
            record_id = request.POST.get('record_id')
            try:
                record = BorrowRecord.objects.get(id=record_id, school=school)
                record.return_date = today
                record.returned_to = user
                record.book_copy.status = BookStatus.AVAILABLE
                record.book_copy.save()
                record.save()
                messages.success(request, f"'{record.book_copy.book.title}' returned successfully.")
            except BorrowRecord.DoesNotExist:
                messages.error(request, "Borrow record not found.")
            return redirect('library:dashboard')

        elif action == 'issue_book':
            book_id = request.POST.get('book_id')
            copy_id = request.POST.get('copy_id')
            student_id = request.POST.get('student_id')
            due_date_str = request.POST.get('due_date')
            try:
                from apps.students.models import StudentProfile
                student = StudentProfile.objects.get(id=student_id, school=school)
                due_date = datetime.datetime.strptime(due_date_str, '%Y-%m-%d').date()

                if book_id:
                    copy = BookCopy.objects.filter(book_id=book_id, school=school, status=BookStatus.AVAILABLE).first()
                elif copy_id:
                    copy = BookCopy.objects.get(id=copy_id, school=school)
                else:
                    copy = None

                if not copy or copy.status != BookStatus.AVAILABLE:
                    messages.error(request, "No available copies for this book.")
                    return redirect('library:dashboard')

                BorrowRecord.objects.create(
                    school=school,
                    book_copy=copy,
                    borrower_student=student,
                    borrowed_date=today,
                    due_date=due_date,
                    issued_by=user
                )
                copy.status = BookStatus.BORROWED
                copy.save()
                messages.success(request, f"'{copy.book.title}' issued to {student.full_name}.")
            except Exception as e:
                messages.error(request, f"Error issuing book: {e}")
            return redirect('library:dashboard')

    from apps.students.models import StudentProfile
    from apps.academics.models import Grade, Section
    from apps.enrollment.models import StudentEnrollment
    from django.db.models import Prefetch, Count, Q

    current_ay = getattr(request, 'academic_year', None)
    students = StudentProfile.objects.filter(school=school).order_by('first_name', 'last_name')
    if current_ay:
        students = students.prefetch_related(
            Prefetch(
                'enrollments',
                queryset=StudentEnrollment.objects.filter(academic_year=current_ay).select_related('grade', 'section'),
                to_attr='active_enrollments'
            )
        )

    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    
    # Group available books by Book title with available copy count
    available_books = Book.objects.filter(school=school, copies__status=BookStatus.AVAILABLE).annotate(
        avail_count=Count('copies', filter=Q(copies__status=BookStatus.AVAILABLE))
    ).order_by('title').distinct()

    return render(request, 'library/borrow_dashboard.html', {
        'active_borrows': active_borrows,
        'overdue': overdue,
        'students': students,
        'grades': grades,
        'sections': sections,
        'available_books': available_books,
        'today': today.isoformat(),
        'overdue_count': len(overdue),
    })


@login_required
def add_book_view(request):
    """Add a new book to the library catalog, with optional immediate issuance to a student/borrower."""
    school = getattr(request, 'school', None)
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.LIBRARIAN]:
        messages.error(request, "Unauthorized.")
        return redirect('library:catalog')

    today = datetime.date.today()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        author = request.POST.get('author', '').strip()
        isbn = request.POST.get('isbn', '').strip() or None
        category = request.POST.get('category')
        subject = request.POST.get('subject', '').strip()
        grade_level = request.POST.get('grade_level', '').strip()
        total_copies_str = request.POST.get('total_copies', '').strip()
        try:
            total_copies = int(total_copies_str) if total_copies_str else 1
        except (ValueError, TypeError):
            total_copies = 1
        publisher = request.POST.get('publisher', '').strip()
        pub_year = request.POST.get('publication_year') or None

        issue_immediately = request.POST.get('issue_immediately') == 'on'
        student_id = request.POST.get('student_id')
        external_borrower_name = request.POST.get('external_borrower_name', '').strip()
        due_date_str = request.POST.get('due_date')

        try:
            book = Book.objects.create(
                school=school, title=title, author=author, isbn=isbn,
                category=category, subject=subject, grade_level=grade_level,
                total_copies=total_copies, publisher=publisher,
                publication_year=int(pub_year) if pub_year else None
            )
            # Create copy records
            created_copies = []
            for i in range(1, total_copies + 1):
                c = BookCopy.objects.create(
                    school=school, book=book, copy_number=f"COPY-{i:03d}"
                )
                created_copies.append(c)

            if issue_immediately and created_copies:
                first_copy = created_copies[0]
                due_date = datetime.datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else (today + datetime.timedelta(days=14))
                
                if student_id:
                    from apps.students.models import StudentProfile
                    student = StudentProfile.objects.get(id=student_id, school=school)
                    BorrowRecord.objects.create(
                        school=school,
                        book_copy=first_copy,
                        borrower_student=student,
                        borrowed_date=today,
                        due_date=due_date,
                        issued_by=user
                    )
                    first_copy.status = BookStatus.BORROWED
                    first_copy.save()
                    messages.success(request, f"🎉 Book '{book.title}' created and immediately issued to {student.full_name}!")
                elif external_borrower_name:
                    from apps.teachers.models import StaffProfile
                    staff = StaffProfile.objects.filter(school=school).first()
                    BorrowRecord.objects.create(
                        school=school,
                        book_copy=first_copy,
                        borrower_staff=staff,
                        borrowed_date=today,
                        due_date=due_date,
                        issued_by=user
                    )
                    first_copy.status = BookStatus.BORROWED
                    first_copy.save()
                    messages.success(request, f"🎉 Book '{book.title}' created and immediately issued to {external_borrower_name}!")
                else:
                    messages.success(request, f"Book '{book.title}' added with {total_copies} copies.")
            else:
                messages.success(request, f"Book '{book.title}' added with {total_copies} copies.")

            return redirect('library:dashboard')
        except Exception as e:
            messages.error(request, f"Error adding book: {e}")

    from apps.students.models import StudentProfile
    from apps.academics.models import Grade, Section
    from apps.enrollment.models import StudentEnrollment
    from django.db.models import Prefetch

    current_ay = getattr(request, 'academic_year', None)
    students = StudentProfile.objects.filter(school=school).order_by('first_name', 'last_name')
    if current_ay:
        students = students.prefetch_related(
            Prefetch(
                'enrollments',
                queryset=StudentEnrollment.objects.filter(academic_year=current_ay).select_related('grade', 'section'),
                to_attr='active_enrollments'
            )
        )

    grades = Grade.objects.filter(school=school).order_by('level')
    sections = Section.objects.filter(school=school).select_related('grade', 'stream').order_by('grade__level', 'name')
    default_due_date = (today + datetime.timedelta(days=14)).isoformat()

    return render(request, 'library/add_book.html', {
        'categories': Book._meta.get_field('category').choices,
        'students': students,
        'grades': grades,
        'sections': sections,
        'default_due_date': default_due_date,
    })


@login_required
def edit_book_view(request, book_id):
    """Edit existing book details in library catalog."""
    school = getattr(request, 'school', None)
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.LIBRARIAN]:
        messages.error(request, "Unauthorized.")
        return redirect('library:catalog')

    book = get_object_or_404(Book, id=book_id, school=school)

    if request.method == 'POST':
        book.title = request.POST.get('title', '').strip()
        book.author = request.POST.get('author', '').strip()
        book.isbn = request.POST.get('isbn', '').strip() or None
        book.category = request.POST.get('category')
        book.subject = request.POST.get('subject', '').strip()
        book.grade_level = request.POST.get('grade_level', '').strip()
        book.publisher = request.POST.get('publisher', '').strip()
        pub_year = request.POST.get('publication_year')
        book.publication_year = int(pub_year) if (pub_year and pub_year.isdigit()) else None

        total_copies_str = request.POST.get('total_copies', '').strip()
        try:
            new_total = int(total_copies_str) if total_copies_str else book.total_copies
        except (ValueError, TypeError):
            new_total = book.total_copies

        current_copies_count = book.copies.count()
        if new_total > current_copies_count:
            for i in range(current_copies_count + 1, new_total + 1):
                BookCopy.objects.create(school=school, book=book, copy_number=f"COPY-{i:03d}")
        book.total_copies = max(new_total, current_copies_count)
        book.save()

        messages.success(request, f"Book '{book.title}' updated successfully.")
        return redirect('library:catalog')

    return render(request, 'library/edit_book.html', {
        'book': book,
        'categories': Book._meta.get_field('category').choices,
    })


@login_required
def delete_book_view(request, book_id):
    """Delete a book and its copies if not currently out on loan."""
    school = getattr(request, 'school', None)
    user = request.user

    if user.role not in [UserRole.SUPER_ADMIN, UserRole.SCHOOL_ADMIN, UserRole.PRINCIPAL, UserRole.REGISTRAR, UserRole.LIBRARIAN]:
        messages.error(request, "Unauthorized.")
        return redirect('library:catalog')

    book = get_object_or_404(Book, id=book_id, school=school)

    if request.method == 'POST':
        # Check if any copy is currently out on loan
        active_loans = BorrowRecord.objects.filter(school=school, book_copy__book=book, return_date__isnull=True).exists()
        if active_loans:
            messages.error(request, f"Cannot delete '{book.title}': One or more copies are currently borrowed.")
            return redirect('library:catalog')

        title = book.title
        book.delete()
        messages.success(request, f"Book '{title}' removed from library catalog.")
        return redirect('library:catalog')

    return redirect('library:catalog')
