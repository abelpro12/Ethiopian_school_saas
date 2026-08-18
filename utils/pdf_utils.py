"""
PDF and QR Code Utility Service
Handles generation of official report cards, payment receipts, public verification QR codes, and transcripts.
"""

import io
import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


def generate_qr_code_image(data_str: str) -> io.BytesIO:
    """Generates a QR code image as BytesIO stream."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def generate_report_card_pdf(school_info: dict, student_info: dict, results_info: list, verification_url: str, attendance_info: dict = None) -> bytes:
    """
    Generates a production PDF Report Card using ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#1E3A8A')
    )
    subtitle_style = ParagraphStyle(
        'HeaderSub',
        parent=styles['Normal'],
        fontSize=11,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#4B5563')
    )
    bold_cell = ParagraphStyle('BoldCell', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold')
    normal_cell = ParagraphStyle('NormalCell', parent=styles['Normal'], fontSize=9)

    elements = []

    # Header / School Branding
    elements.append(Paragraph(f"<b>{school_info.get('name', 'Ethiopian Academy')}</b>", title_style))
    elements.append(Paragraph(f"{school_info.get('address', 'Addis Ababa, Ethiopia')} | Phone: {school_info.get('phone', 'N/A')}", subtitle_style))
    elements.append(Paragraph("<b>OFFICIAL STUDENT REPORT CARD</b>", ParagraphStyle('ReportCardHead', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor('#065F46'))))
    elements.append(Spacer(1, 10))

    # Student Info Table
    student_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell),
            Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell),
        ],
        [
            Paragraph(f"<b>Grade & Section:</b> {student_info.get('grade_section')}", normal_cell),
            Paragraph(f"<b>Academic Year:</b> {student_info.get('academic_year')}", normal_cell),
        ],
        [
            Paragraph(f"<b>Stream:</b> {student_info.get('stream', 'General')}", normal_cell),
            Paragraph(f"<b>Semester:</b> {student_info.get('semester', 'Semester 1')}", normal_cell),
        ]
    ]
    info_table = Table(student_table_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F4F6')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # Results Table Header
    headers = ["Subject", "Assgn (10)", "Quiz (10)", "Mid (20)", "Final (60)", "Total (100)", "Grade", "Rank"]
    table_data = [[Paragraph(f"<b>{h}</b>", bold_cell) for h in headers]]

    total_marks_sum = 0
    subject_count = 0

    for r in results_info:
        table_data.append([
            Paragraph(r.get('subject_name', ''), normal_cell),
            Paragraph(str(r.get('assignment', '-')), normal_cell),
            Paragraph(str(r.get('quiz', '-')), normal_cell),
            Paragraph(str(r.get('midterm', '-')), normal_cell),
            Paragraph(str(r.get('final', '-')), normal_cell),
            Paragraph(f"<b>{r.get('total', 0)}</b>", normal_cell),
            Paragraph(f"<b>{r.get('letter_grade', 'F')}</b>", normal_cell),
            Paragraph(str(r.get('subject_rank', '-')), normal_cell),
        ])
        total_marks_sum += r.get('total', 0)
        subject_count += 1

    results_table = Table(table_data, colWidths=[140, 55, 55, 55, 55, 65, 55, 60])
    results_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(results_table)
    elements.append(Spacer(1, 12))

    # Attendance Info Section
    if attendance_info:
        att_data = [
            [
                Paragraph("<b>Attendance Record</b>", bold_cell),
                Paragraph(f"Present: {attendance_info.get('present', 0)} days", normal_cell),
                Paragraph(f"Absent: {attendance_info.get('absent', 0)} days", normal_cell),
                Paragraph(f"Late: {attendance_info.get('late', 0)} days", normal_cell),
                Paragraph(f"Total: {attendance_info.get('total', 0)} days", normal_cell),
            ]
        ]
        att_table = Table(att_data, colWidths=[140, 100, 100, 100, 100])
        att_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#F3F4F6')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(att_table)
        elements.append(Spacer(1, 10))

    # Summary & QR Code Section
    avg_score = round(total_marks_sum / max(1, subject_count), 2)
    summary_text = f"<b>Total Subjects:</b> {subject_count} | <b>Average Score:</b> {avg_score}% | <b>Section Rank:</b> {student_info.get('rank', 'N/A')}"
    elements.append(Paragraph(summary_text, ParagraphStyle('SummaryStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#1E293B'))))
    elements.append(Spacer(1, 10))

    # QR Code & Verification Token Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=1.0*inch, height=1.0*inch)
    
    footer_data = [
        [
            qr_img,
            Paragraph(f"<b>Official Verification Code:</b> {student_info.get('doc_number', 'ETH-DOC-1001')}<br/>"
                      f"<font size=8 color='#6B7280'>Scan QR code or visit school verification page to verify authenticity.</font>", normal_cell)
        ]
    ]
    footer_table = Table(footer_data, colWidths=[80, 460])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_receipt_pdf(school_info: dict, student_info: dict, payment_info: dict, verification_url: str) -> bytes:
    """Generates an official digital payment receipt PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('RecTitle', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    normal_cell = ParagraphStyle('RecCell', parent=styles['Normal'], fontSize=10)

    elements = []
    elements.append(Paragraph(f"<b>{school_info.get('name', 'Ethiopian School')}</b>", title_style))
    elements.append(Paragraph("<b>OFFICIAL PAYMENT RECEIPT (ETB)</b>", ParagraphStyle('RecSub', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor('#047857'))))
    elements.append(Spacer(1, 15))

    receipt_table_data = [
        [Paragraph(f"<b>Receipt No:</b> {payment_info.get('receipt_no')}", normal_cell), Paragraph(f"<b>Date:</b> {payment_info.get('date')}", normal_cell)],
        [Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell), Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell)],
        [Paragraph(f"<b>Fee Type:</b> {payment_info.get('fee_title')}", normal_cell), Paragraph(f"<b>Invoice No:</b> {payment_info.get('invoice_no')}", normal_cell)],
        [Paragraph(f"<b>Amount Paid:</b> {payment_info.get('amount_paid')} ETB", normal_cell), Paragraph(f"<b>Payment Method:</b> {payment_info.get('method', 'Chapa Mobile/Card')}", normal_cell)],
        [Paragraph(f"<b>Remaining Balance:</b> {payment_info.get('remaining_balance')} ETB", normal_cell), Paragraph(f"<b>Reference:</b> {payment_info.get('tx_ref')}", normal_cell)],
    ]

    rec_table = Table(receipt_table_data, colWidths=[270, 270])
    rec_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(rec_table)
    elements.append(Spacer(1, 15))

    # QR Code
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=0.9*inch, height=0.9*inch)
    footer_table = Table([[qr_img, Paragraph(f"Verify Receipt: {verification_url}", normal_cell)]], colWidths=[70, 470])
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_transcript_pdf(school_info: dict, student_info: dict, grades_data: list, verification_url: str) -> bytes:
    """
    Generates an official Student Transcript (Grades 9-12).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TransTitle', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    normal_cell = ParagraphStyle('TransCell', parent=styles['Normal'], fontSize=9)
    bold_cell = ParagraphStyle('TransBoldCell', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold')

    elements = []
    elements.append(Paragraph(f"<b>{school_info.get('name', 'Ethiopian School')}</b>", title_style))
    elements.append(Paragraph("<b>OFFICIAL STUDENT TRANSCRIPT (GRADES 9-12)</b>", ParagraphStyle('TransSub', parent=styles['Heading2'], alignment=1, textColor=colors.HexColor('#047857'))))
    elements.append(Spacer(1, 15))

    # Student Info Table
    student_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell),
            Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell),
        ]
    ]
    info_table = Table(student_table_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F4F6')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    for grade_record in grades_data:
        elements.append(Paragraph(f"<b>{grade_record['grade_name']} ({grade_record['academic_year']})</b>", ParagraphStyle('GradeLevel', parent=styles['Heading3'])))
        elements.append(Spacer(1, 5))
        
        headers = ["Subject", "Sem 1", "Sem 2", "Average", "Grade"]
        table_data = [[Paragraph(f"<b>{h}</b>", bold_cell) for h in headers]]
        
        for subj in grade_record['subjects']:
            table_data.append([
                Paragraph(subj['name'], normal_cell),
                Paragraph(str(subj['sem1']), normal_cell),
                Paragraph(str(subj['sem2']), normal_cell),
                Paragraph(str(subj['avg']), normal_cell),
                Paragraph(f"<b>{subj['letter']}</b>", normal_cell),
            ])
            
        results_table = Table(table_data, colWidths=[240, 75, 75, 75, 75])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(results_table)
        elements.append(Spacer(1, 15))

    # QR Code & Verification Token Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=1.0*inch, height=1.0*inch)
    
    footer_data = [
        [
            qr_img,
            Paragraph(f"<b>Official Verification Code:</b> {student_info.get('doc_number', 'TRANS-1001')}<br/>"
                      f"<font size=8 color='#6B7280'>Scan QR code or visit school verification page to verify authenticity.</font>", normal_cell)
        ]
    ]
    footer_table = Table(footer_data, colWidths=[80, 460])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_transfer_certificate_pdf(school_info: dict, student_info: dict, transfer_info: dict, verification_url: str) -> bytes:
    """
    Generates an official Ethiopian School Transfer Certificate PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CertTitle', parent=styles['Heading1'], fontSize=18, leading=22, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    sub_style = ParagraphStyle('CertSub', parent=styles['Heading2'], fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#991B1B'))
    normal_cell = ParagraphStyle('CertCell', parent=styles['Normal'], fontSize=10, leading=14)

    elements = []
    elements.append(Paragraph(f"<b>{school_info.get('name', 'Ethiopian School')}</b>", title_style))
    elements.append(Paragraph(f"{school_info.get('address', 'Addis Ababa, Ethiopia')} | Phone: {school_info.get('phone', 'N/A')}", ParagraphStyle('CertAddr', parent=styles['Normal'], alignment=1, fontSize=9, textColor=colors.HexColor('#4B5563'))))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<b>OFFICIAL STUDENT TRANSFER CERTIFICATE</b>", sub_style))
    elements.append(Spacer(1, 20))

    cert_text = f"""
    This is to certify that <b>{student_info.get('full_name')}</b> (Student ID: <b>{student_info.get('student_id')}</b>), 
    was a bonafide student of this institution in <b>{transfer_info.get('last_grade', 'Grade 10')}</b> 
    during the <b>{transfer_info.get('academic_year', '2018 E.C.')}</b> Academic Year.<br/><br/>
    <b>Admission Number:</b> {student_info.get('admission_number', 'N/A')}<br/>
    <b>Date of Birth:</b> {student_info.get('date_of_birth', 'N/A')}<br/>
    <b>General Conduct & Behavior:</b> {transfer_info.get('conduct_grade', 'Excellent (A)')}<br/>
    <b>Reason for Transfer:</b> {transfer_info.get('reason', 'Parent request / External school transfer')}<br/>
    <b>Destination School:</b> {transfer_info.get('destination_school', 'To whom it may concern')}<br/><br/>
    All financial dues and school property obligations have been fully cleared as of <b>{transfer_info.get('issue_date', 'Today')}</b>.
    """
    elements.append(Paragraph(cert_text, normal_cell))
    elements.append(Spacer(1, 40))

    # Signatures Table
    sig_data = [
        [
            Paragraph("_______________________<br/><b>School Registrar</b>", normal_cell),
            Paragraph("_______________________<br/><b>Principal / Headmaster</b>", normal_cell),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[270, 270])
    sig_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(sig_table)
    elements.append(Spacer(1, 30))

    # QR Code Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=0.9*inch, height=0.9*inch)
    footer_table = Table([[qr_img, Paragraph(f"<b>Document Verification:</b> {verification_url}<br/><font size=8 color='#6B7280'>Scan QR code to verify validity on official school server.</font>", normal_cell)]], colWidths=[70, 470])
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_enrollment_certificate_pdf(school_info: dict, student_info: dict, enrollment_info: dict, verification_url: str) -> bytes:
    """
    Generates an official Certificate of Active Student Enrollment PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('EncTitle', parent=styles['Heading1'], fontSize=18, leading=22, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    sub_style = ParagraphStyle('EncSub', parent=styles['Heading2'], fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#047857'))
    normal_cell = ParagraphStyle('EncCell', parent=styles['Normal'], fontSize=10, leading=15)

    elements = []
    elements.append(Paragraph(f"<b>{school_info.get('name', 'Ethiopian School')}</b>", title_style))
    elements.append(Paragraph(f"{school_info.get('address', 'Addis Ababa, Ethiopia')} | Phone: {school_info.get('phone', 'N/A')}", ParagraphStyle('EncAddr', parent=styles['Normal'], alignment=1, fontSize=9, textColor=colors.HexColor('#4B5563'))))
    elements.append(Spacer(1, 15))
    elements.append(Paragraph("<b>CERTIFICATE OF ACTIVE ENROLLMENT</b>", sub_style))
    elements.append(Spacer(1, 20))

    cert_text = f"""
    To Whom It May Concern:<br/><br/>
    This letter officially confirms that <b>{student_info.get('full_name')}</b> (Student ID: <b>{student_info.get('student_id')}</b>) 
    is currently enrolled as an active student at <b>{school_info.get('name')}</b> for the <b>{enrollment_info.get('academic_year', '2018 E.C.')}</b> Academic Year.<br/><br/>
    <b>Current Grade Level:</b> {enrollment_info.get('grade_name', 'Grade 10')}<br/>
    <b>Section:</b> {enrollment_info.get('section_name', 'A')}<br/>
    <b>Stream Pathway:</b> {enrollment_info.get('stream_name', 'General')}<br/>
    <b>Enrollment Date:</b> {enrollment_info.get('enrollment_date', 'N/A')}<br/>
    <b>Enrollment Status:</b> ACTIVE<br/><br/>
    This certificate is issued upon student request for official administrative and verification purposes.
    """
    elements.append(Paragraph(cert_text, normal_cell))
    elements.append(Spacer(1, 50))

    # Signatures Table
    sig_data = [
        [
            Paragraph("_______________________<br/><b>Director of Admissions</b>", normal_cell),
            Paragraph("_______________________<br/><b>School Principal</b>", normal_cell),
        ]
    ]
    sig_table = Table(sig_data, colWidths=[270, 270])
    sig_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(sig_table)
    elements.append(Spacer(1, 30))

    # QR Code Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=0.9*inch, height=0.9*inch)
    footer_table = Table([[qr_img, Paragraph(f"<b>Verify Document:</b> {verification_url}", normal_cell)]], colWidths=[70, 470])
    elements.append(footer_table)

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def generate_attendance_pdf(school_name: str, title: str, section_name: str, date_str: str, controller_name: str, records: list) -> bytes:
    """
    Generates an official PDF attendance sheet using ReportLab.
    records is a list of dicts: [{'student_id': ..., 'student_name': ..., 'status': ..., 'reason': ...}]
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Heading1'],
        fontSize=16,
        leading=20,
        alignment=1,
        textColor=colors.HexColor('#1E1B4B')
    )
    subtitle_style = ParagraphStyle(
        'HeaderSub',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569')
    )

    elements = []
    elements.append(Paragraph(f"<b>{school_name}</b>", title_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"{title} &mdash; Section: <b>{section_name}</b> | Date: <b>{date_str}</b>", subtitle_style))
    if controller_name:
        elements.append(Paragraph(f"Teacher / Controller: <b>{controller_name}</b>", subtitle_style))
    elements.append(Spacer(1, 14))

    table_data = [["Student ID", "Student Name", "Attendance Status", "Remarks / Reason"]]
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=9, leading=11)
    header_style = ParagraphStyle('Header', parent=styles['Normal'], fontSize=9, leading=11, fontName="Helvetica-Bold", textColor=colors.white)

    for r in records:
        table_data.append([
            Paragraph(r.get('student_id', ''), cell_style),
            Paragraph(r.get('student_name', ''), cell_style),
            Paragraph(r.get('status', ''), cell_style),
            Paragraph(r.get('reason', ''), cell_style),
        ])

    formatted_table_data = []
    for row_idx, row in enumerate(table_data):
        formatted_row = []
        for col in row:
            if row_idx == 0:
                formatted_row.append(Paragraph(str(col), header_style))
            else:
                formatted_row.append(col if isinstance(col, Paragraph) else Paragraph(str(col), cell_style))
        formatted_table_data.append(formatted_row)

    t = Table(formatted_table_data, colWidths=[1.2*inch, 2.5*inch, 1.4*inch, 2.1*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4C1D95')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))

    elements.append(t)
    doc.build(elements)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value

