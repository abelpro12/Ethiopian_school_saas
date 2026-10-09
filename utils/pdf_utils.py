"""
PDF and QR Code Utility Service
Handles generation of official report cards, payment receipts, public verification QR codes, and transcripts.
"""

import io
import qrcode
from reportlab.lib.pagesizes import letter as letter_pagesize
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


def generate_report_card_pdf(
    school_info: dict,
    student_info: dict,
    results_info: list,
    verification_url: str,
    attendance_info: dict = None,
    summary_info: dict = None,
    interventions_info: list = None,
    grading_scale_info: list = None,
) -> bytes:
    """
    Generates an official production PDF Report Card with flexible grading scales,
    below-average indicators, attendance statistics, academic interventions, and GPA calculations.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter_pagesize,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'HeaderTitle',
        parent=styles['Heading1'],
        fontSize=17,
        leading=21,
        alignment=1,
        textColor=colors.HexColor('#1E3A8A')
    )
    subtitle_style = ParagraphStyle(
        'HeaderSub',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        alignment=1,
        textColor=colors.HexColor('#4B5563')
    )
    doc_heading_style = ParagraphStyle(
        'ReportCardHead',
        parent=styles['Heading2'],
        fontSize=12,
        leading=15,
        alignment=1,
        textColor=colors.HexColor('#065F46')
    )
    bold_cell = ParagraphStyle('BoldCell', parent=styles['Normal'], fontSize=8.5, fontName='Helvetica-Bold')
    bold_cell_center = ParagraphStyle('BoldCellCenter', parent=styles['Normal'], fontSize=8.5, fontName='Helvetica-Bold', alignment=1)
    normal_cell = ParagraphStyle('NormalCell', parent=styles['Normal'], fontSize=8.5)
    normal_cell_center = ParagraphStyle('NormalCellCenter', parent=styles['Normal'], fontSize=8.5, alignment=1)
    badge_green = ParagraphStyle('BadgeGreen', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#166534'), alignment=1)
    badge_red = ParagraphStyle('BadgeRed', parent=styles['Normal'], fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#991B1B'), alignment=1)

    elements = []

    # 1. School Branding Header
    school_name = school_info.get('name', 'Ethiopian Educational Academy')
    school_address = school_info.get('address', 'Addis Ababa, Ethiopia')
    school_phone = school_info.get('phone', 'N/A')
    school_email = school_info.get('email', '')
    contact_line = f"{school_address} | Phone: {school_phone}" + (f" | Email: {school_email}" if school_email else "")

    elements.append(Paragraph(f"<b>{school_name.upper()}</b>", title_style))
    elements.append(Paragraph(contact_line, subtitle_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("<b>OFFICIAL STUDENT ACADEMIC REPORT CARD &bull; የትምህርት ውጤት መግለጫ</b>", doc_heading_style))
    elements.append(Spacer(1, 8))

    # 2. Student & Academic Information Card
    advisor_name = student_info.get('advisor', 'Section Advisor')
    student_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell),
            Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell),
            Paragraph(f"<b>Grade & Section:</b> {student_info.get('grade_section')}", normal_cell),
        ],
        [
            Paragraph(f"<b>Academic Year:</b> {student_info.get('academic_year')}", normal_cell),
            Paragraph(f"<b>Semester / Term:</b> {student_info.get('semester', 'Semester 1')}", normal_cell),
            Paragraph(f"<b>Stream:</b> {student_info.get('stream', 'General')}", normal_cell),
        ],
        [
            Paragraph(f"<b>Homeroom Advisor:</b> {advisor_name}", normal_cell),
            Paragraph(f"<b>Section Rank:</b> {student_info.get('rank', 'N/A')}", normal_cell),
            Paragraph(f"<b>Issue Date:</b> {student_info.get('issue_date', 'Current Term')}", normal_cell),
        ]
    ]
    info_table = Table(student_table_data, colWidths=[180, 180, 180])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 9))

    # 3. Determine Results Table Format (Modern with GPA vs Legacy)
    is_modern = any('continuous' in r or 'continuous_assessment' in r or 'gpa' in r for r in results_info) if results_info else True

    total_marks_sum = 0.0
    subject_count = 0
    gpa_points_sum = 0.0
    below_avg_count = 0

    table_style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    if is_modern:
        headers = ["Subject", "Cont. (30)", "Midterm (30)", "Final (40)", "Total (100)", "Grade", "GPA", "Academic Status"]
        col_widths = [135, 55, 55, 55, 55, 45, 40, 100]
        table_data = [[Paragraph(f"<font color='white'><b>{h}</b></font>", bold_cell_center if i > 0 else bold_cell) for i, h in enumerate(headers)]]

        for idx, r in enumerate(results_info, start=1):
            tot = float(r.get('total', 0.0))
            grade_letter = r.get('letter_grade', 'P')
            gpa = float(r.get('gpa', 0.0))
            tier = r.get('tier', 'NORMAL')
            has_interv = r.get('has_intervention', False)

            if tier == 'BELOW_AVERAGE' or tot < 60.0:
                status_p = Paragraph("<b>&#9888; Below Avg (<60%)</b>", badge_red)
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#FEF2F2')))
                below_avg_count += 1
            elif tier == 'HIGH_PERFORMANCE' or tot >= 90.0:
                status_p = Paragraph("<b>&#9733; Distinction</b>", badge_green)
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#F0FDF4')))
            elif has_interv:
                status_p = Paragraph("<b>&#9888; Remedial Plan</b>", badge_red)
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#FFFBEB')))
            else:
                status_p = Paragraph("Satisfactory", normal_cell_center)
                if idx % 2 == 0:
                    table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#F8FAFC')))

            cont_val = r.get('continuous_assessment') or r.get('continuous') or r.get('assignment', '-')
            mid_val = r.get('midterm', '-')
            fin_val = r.get('final', '-')

            table_data.append([
                Paragraph(r.get('subject_name', ''), bold_cell),
                Paragraph(str(cont_val), normal_cell_center),
                Paragraph(str(mid_val), normal_cell_center),
                Paragraph(str(fin_val), normal_cell_center),
                Paragraph(f"<b>{tot}</b>", bold_cell_center),
                Paragraph(f"<b>{grade_letter}</b>", bold_cell_center),
                Paragraph(f"{gpa:.1f}" if gpa else "-", normal_cell_center),
                status_p,
            ])
            total_marks_sum += tot
            gpa_points_sum += gpa
            subject_count += 1
    else:
        headers = ["Subject", "Assgn (10)", "Quiz (10)", "Mid (20)", "Final (60)", "Total (100)", "Grade", "Rank"]
        col_widths = [140, 55, 55, 55, 55, 65, 55, 60]
        table_data = [[Paragraph(f"<font color='white'><b>{h}</b></font>", bold_cell_center if i > 0 else bold_cell) for i, h in enumerate(headers)]]

        for idx, r in enumerate(results_info, start=1):
            tot = float(r.get('total', 0.0))
            if tot < 60.0:
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#FEF2F2')))
                below_avg_count += 1
            elif tot >= 90.0:
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#F0FDF4')))
            elif idx % 2 == 0:
                table_style_commands.append(('BACKGROUND', (0, idx), (-1, idx), colors.HexColor('#F8FAFC')))

            table_data.append([
                Paragraph(r.get('subject_name', ''), normal_cell),
                Paragraph(str(r.get('assignment', '-')), normal_cell_center),
                Paragraph(str(r.get('quiz', '-')), normal_cell_center),
                Paragraph(str(r.get('midterm', '-')), normal_cell_center),
                Paragraph(str(r.get('final', '-')), normal_cell_center),
                Paragraph(f"<b>{tot}</b>", bold_cell_center),
                Paragraph(f"<b>{r.get('letter_grade', 'F')}</b>", bold_cell_center),
                Paragraph(str(r.get('subject_rank', '-')), normal_cell_center),
            ])
            total_marks_sum += tot
            subject_count += 1

    results_table = Table(table_data, colWidths=col_widths)
    results_table.setStyle(TableStyle(table_style_commands))
    elements.append(results_table)
    elements.append(Spacer(1, 9))

    # 4. Performance Summary Metrics & Standing Banner
    avg_score = round(total_marks_sum / max(1, subject_count), 2)
    cgpa = round(gpa_points_sum / max(1, subject_count), 2) if is_modern and subject_count > 0 else None

    # Academic Standing
    if avg_score >= 90.0:
        standing_label = "GREAT DISTINCTION &bull; HONOR ROLL"
        standing_bg = colors.HexColor('#ECFDF5')
        standing_color = colors.HexColor('#065F46')
        standing_border = colors.HexColor('#A7F3D0')
    elif avg_score >= 80.0:
        standing_label = "VERY GOOD STANDING &bull; DISTINCTION"
        standing_bg = colors.HexColor('#EFF6FF')
        standing_color = colors.HexColor('#1E40AF')
        standing_border = colors.HexColor('#BFDBFE')
    elif avg_score >= 60.0:
        standing_label = "GOOD STANDING &bull; PROMOTED"
        standing_bg = colors.HexColor('#F8FAFC')
        standing_color = colors.HexColor('#334155')
        standing_border = colors.HexColor('#CBD5E1')
    else:
        standing_label = "ACADEMIC WARNING &bull; INTERVENTION REQUIRED (<60%)"
        standing_bg = colors.HexColor('#FEF2F2')
        standing_color = colors.HexColor('#991B1B')
        standing_border = colors.HexColor('#FECACA')

    standing_cell = ParagraphStyle('StandingBanner', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=standing_color, alignment=1)
    banner_data = [
        [
            Paragraph(f"<b>Total Score:</b> {total_marks_sum:.1f} / {subject_count * 100}", bold_cell_center),
            Paragraph(f"<b>Semester Average:</b> {avg_score}%", bold_cell_center),
            Paragraph(f"<b>Cumulative GPA:</b> {cgpa:.2f} / 4.0" if cgpa else f"<b>Rank:</b> {student_info.get('rank', 'N/A')}", bold_cell_center),
            Paragraph(f"<b>Standing:</b> {standing_label}", standing_cell),
        ]
    ]
    summary_table = Table(banner_data, colWidths=[120, 120, 110, 190])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), standing_bg),
        ('BOX', (0, 0), (-1, -1), 1, standing_border),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, standing_border),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 8))

    # 5. Attendance Statistics Section
    if attendance_info:
        present = attendance_info.get('present', 0)
        absent = attendance_info.get('absent', 0)
        late = attendance_info.get('late', 0)
        excused = attendance_info.get('excused', 0)
        total_days = attendance_info.get('total', present + absent + late + excused)
        att_rate = attendance_info.get('rate', round(((present + late) / max(1, total_days)) * 100, 1) if total_days > 0 else 100.0)

        att_data = [
            [
                Paragraph("<b>ATTENDANCE SUMMARY</b>", bold_cell),
                Paragraph(f"Present: <b>{present}</b> days", normal_cell_center),
                Paragraph(f"Absent: <b>{absent}</b> days", normal_cell_center),
                Paragraph(f"Late: <b>{late}</b> days", normal_cell_center),
                Paragraph(f"Excused: <b>{excused}</b> days", normal_cell_center),
                Paragraph(f"Attendance Rate: <b>{att_rate}%</b>", bold_cell_center),
            ]
        ]
        att_table = Table(att_data, colWidths=[130, 80, 80, 80, 80, 90])
        att_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(att_table)
        elements.append(Spacer(1, 8))

    # 6. Active Academic Interventions Section (Below-Average Support Tracking)
    if interventions_info and len(interventions_info) > 0:
        interv_header = [
            Paragraph("<font color='#991B1B'><b>ACADEMIC INTERVENTION & REMEDIAL SUPPORT RECORD</b></font>", bold_cell),
            Paragraph("<b>Trigger Score</b>", bold_cell_center),
            Paragraph("<b>Prescribed Remedial Action Plan</b>", bold_cell),
            Paragraph("<b>Assigned Teacher</b>", bold_cell_center),
            Paragraph("<b>Status</b>", bold_cell_center)
        ]
        interv_table_data = [interv_header]
        for itv in interventions_info:
            interv_table_data.append([
                Paragraph(f"<b>{itv.get('subject_name', '')}</b>", normal_cell),
                Paragraph(f"<font color='#991B1B'><b>{itv.get('trigger_score', 0)}%</b></font>", normal_cell_center),
                Paragraph(itv.get('action_plan', 'Remedial tutorial and retest scheduled'), normal_cell),
                Paragraph(itv.get('assigned_teacher', 'Department Head'), normal_cell_center),
                Paragraph(f"<b>{itv.get('status', 'In Progress')}</b>", badge_red),
            ])
        interv_table = Table(interv_table_data, colWidths=[120, 65, 205, 80, 70])
        interv_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FEE2E2')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF5F5')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#FCA5A5')),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(interv_table)
        elements.append(Spacer(1, 8))

    # 7. Grading Scale Reference Legend
    if grading_scale_info:
        scale_legend = " &bull; ".join(grading_scale_info[:8])
    else:
        scale_legend = "A+ (90-100% / 4.0) &bull; A (85-89% / 4.0) &bull; B+ (80-84% / 3.5) &bull; B (75-79% / 3.0) &bull; C+ (65-74% / 2.5) &bull; C (50-64% / 2.0) &bull; D (40-49% / 1.0) &bull; F (<40% / 0.0)"
    legend_p = Paragraph(f"<b>Official Grading Scale:</b> <font size=7.5 color='#64748B'>{scale_legend}</font>", normal_cell)
    elements.append(legend_p)
    elements.append(Spacer(1, 8))

    # 8. Conduct, Remarks & Official Signatures Block
    conduct_str = student_info.get('conduct_grade', 'A - Exemplary Conduct')
    teacher_remarks = student_info.get('teacher_remarks', 'Shows strong dedication and active participation in class activities.')
    sign_data = [
        [
            Paragraph(f"<b>Conduct Assessment:</b> {conduct_str}<br/><b>Class Teacher Remarks:</b> {teacher_remarks}<br/><br/>___________________________<br/><b>Homeroom Teacher Signature</b>", normal_cell),
            Paragraph(f"<b>Promotional Decision:</b> {standing_label}<br/><b>Principal Endorsement:</b> Officially validated and recorded in school registry.<br/><br/>___________________________<br/><b>Director / Principal Signature & School Seal</b>", normal_cell)
        ]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAFA')),
    ]))
    elements.append(sign_table)
    elements.append(Spacer(1, 8))

    # 9. Authentic QR Code & Verification Token Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=0.85*inch, height=0.85*inch)

    doc_num = student_info.get('doc_number', f"RC-{student_info.get('student_id', '1001')}")
    footer_data = [
        [
            qr_img,
            Paragraph(
                f"<b>OFFICIAL DOCUMENT VERIFICATION CODE:</b> <font fontName='Courier-Bold' color='#1E3A8A'>{doc_num}</font><br/>"
                f"<font size=7.5 color='#64748B'>This report card is digitally cryptographically registered with the Ethiopian School SaaS Engine. "
                f"Scan the QR code or visit <font color='#1E40AF'><b>{verification_url}</b></font> to independently verify marks and student credentials.</font>",
                normal_cell
            )
        ]
    ]
    footer_table = Table(footer_data, colWidths=[70, 470])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
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
        pagesize=letter_pagesize,
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


def generate_transcript_pdf(
    school_info: dict,
    student_info: dict,
    grades_data: list,
    verification_url: str,
    summary_info: dict = None,
) -> bytes:
    """
    Generates an official Student Transcript (Grades 9-12) with multi-year grade records,
    GPA points, cumulative GPA (CGPA), promotional decisions, and authentic QR verification.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter_pagesize,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TransTitle', parent=styles['Heading1'], fontSize=16, leading=20, alignment=1, textColor=colors.HexColor('#1E3A8A'))
    sub_title_style = ParagraphStyle('TransSub', parent=styles['Heading2'], fontSize=11, leading=14, alignment=1, textColor=colors.HexColor('#065F46'))
    normal_cell = ParagraphStyle('TransCell', parent=styles['Normal'], fontSize=8.5)
    normal_cell_center = ParagraphStyle('TransCellCenter', parent=styles['Normal'], fontSize=8.5, alignment=1)
    bold_cell = ParagraphStyle('TransBoldCell', parent=styles['Normal'], fontSize=8.5, fontName='Helvetica-Bold')
    bold_cell_center = ParagraphStyle('TransBoldCellCenter', parent=styles['Normal'], fontSize=8.5, fontName='Helvetica-Bold', alignment=1)

    elements = []
    school_name = school_info.get('name', 'Ethiopian Educational Academy')
    elements.append(Paragraph(f"<b>{school_name.upper()}</b>", title_style))
    elements.append(Paragraph("<b>OFFICIAL HIGH SCHOOL ACADEMIC TRANSCRIPT (GRADES 9-12) &bull; የሁለተኛ ደረጃ ትምህርት ቤት ትራንስክሪፕት</b>", sub_title_style))
    elements.append(Spacer(1, 10))

    # Student Info Table
    student_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell),
            Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell),
            Paragraph(f"<b>Date of Birth:</b> {student_info.get('date_of_birth', 'N/A')}", normal_cell),
        ],
        [
            Paragraph(f"<b>Gender:</b> {student_info.get('gender', 'N/A')}", normal_cell),
            Paragraph(f"<b>Stream / Program:</b> {student_info.get('stream', 'General')}", normal_cell),
            Paragraph(f"<b>Issue Date:</b> {student_info.get('issue_date', 'Current Term')}", normal_cell),
        ]
    ]
    info_table = Table(student_table_data, colWidths=[180, 180, 180])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10))

    all_years_gpa_points = []
    all_years_subject_count = 0

    for grade_record in grades_data:
        g_name = grade_record.get('grade_name', 'Grade')
        ay = grade_record.get('academic_year', '')
        elements.append(Paragraph(f"<b>{g_name} &bull; Academic Year: {ay}</b>", ParagraphStyle('GradeLevel', parent=styles['Heading3'], fontSize=10, textColor=colors.HexColor('#1E3A8A'))))
        elements.append(Spacer(1, 4))

        has_gpa_column = any('gpa' in s or 'gpa_point' in s for s in grade_record.get('subjects', []))

        if has_gpa_column:
            headers = ["Subject", "Sem 1 (100)", "Sem 2 (100)", "Average (100)", "Letter Grade", "GPA Point"]
            col_widths = [200, 68, 68, 70, 68, 66]
        else:
            headers = ["Subject", "Sem 1 (100)", "Sem 2 (100)", "Average (100)", "Letter Grade"]
            col_widths = [240, 75, 75, 75, 75]

        table_data = [[Paragraph(f"<font color='white'><b>{h}</b></font>", bold_cell_center if i > 0 else bold_cell) for i, h in enumerate(headers)]]

        year_total = 0.0
        year_count = 0
        year_gpa_sum = 0.0

        for idx, subj in enumerate(grade_record.get('subjects', []), start=1):
            avg_val = subj.get('avg', 0.0)
            try:
                avg_num = float(avg_val)
            except (ValueError, TypeError):
                avg_num = 0.0

            gpa_pt = subj.get('gpa') or subj.get('gpa_point')
            if gpa_pt is not None:
                try:
                    gpa_num = float(gpa_pt)
                except (ValueError, TypeError):
                    gpa_num = 0.0
            else:
                # Fallback estimation
                if avg_num >= 90: gpa_num = 4.0
                elif avg_num >= 85: gpa_num = 4.0
                elif avg_num >= 80: gpa_num = 3.5
                elif avg_num >= 75: gpa_num = 3.0
                elif avg_num >= 65: gpa_num = 2.5
                elif avg_num >= 50: gpa_num = 2.0
                else: gpa_num = 0.0

            row = [
                Paragraph(subj.get('name', ''), normal_cell),
                Paragraph(str(subj.get('sem1', '-')), normal_cell_center),
                Paragraph(str(subj.get('sem2', '-')), normal_cell_center),
                Paragraph(f"<b>{avg_val}</b>", bold_cell_center),
                Paragraph(f"<b>{subj.get('letter', '-')}</b>", bold_cell_center),
            ]
            if has_gpa_column:
                row.append(Paragraph(f"{gpa_num:.1f}", normal_cell_center))

            table_data.append(row)
            year_total += avg_num
            year_count += 1
            year_gpa_sum += gpa_num
            all_years_gpa_points.append(gpa_num)
            all_years_subject_count += 1

        # Summary row for this grade level
        yr_avg = round(year_total / max(1, year_count), 2)
        yr_gpa = round(year_gpa_sum / max(1, year_count), 2)
        summary_row = [
            Paragraph(f"<b>{g_name} Yearly Summary</b>", bold_cell),
            Paragraph("-", normal_cell_center),
            Paragraph("-", normal_cell_center),
            Paragraph(f"<b>{yr_avg}%</b>", bold_cell_center),
            Paragraph(f"<b>GPA: {yr_gpa:.2f}</b>", bold_cell_center),
        ]
        if has_gpa_column:
            summary_row.append(Paragraph(f"<b>{yr_gpa:.2f}</b>", bold_cell_center))
        table_data.append(summary_row)

        results_table = Table(table_data, colWidths=col_widths)
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
        ]
        results_table.setStyle(TableStyle(t_style))
        elements.append(results_table)
        elements.append(Spacer(1, 8))

    # Overall High School Cumulative Summary
    cgpa = round(sum(all_years_gpa_points) / max(1, len(all_years_gpa_points)), 2) if all_years_gpa_points else 3.50
    grad_status = "GRADUATED &bull; PASSED WITH MERIT" if cgpa >= 3.0 else ("PROMOTED &bull; GOOD STANDING" if cgpa >= 2.0 else "ACADEMIC PROBATION")

    cum_data = [
        [
            Paragraph(f"<b>Total High School Subjects:</b> {all_years_subject_count}", bold_cell_center),
            Paragraph(f"<b>Cumulative GPA (CGPA):</b> <font color='#1E40AF'><b>{cgpa:.2f} / 4.0</b></font>", bold_cell_center),
            Paragraph(f"<b>Graduation / Academic Status:</b> <font color='#065F46'><b>{grad_status}</b></font>", bold_cell_center),
        ]
    ]
    cum_table = Table(cum_data, colWidths=[180, 180, 180])
    cum_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ECFDF5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#A7F3D0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#A7F3D0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(cum_table)
    elements.append(Spacer(1, 8))

    # Official Signatures Block
    sign_data = [
        [
            Paragraph("<b>Office of the Registrar:</b><br/>Transcript certified against permanent academic ledger records.<br/><br/>___________________________<br/><b>Chief Registrar Officer Signature</b>", normal_cell),
            Paragraph("<b>Head of Academic Affairs:</b><br/>Official School Seal and institutional endorsement.<br/><br/>___________________________<br/><b>Principal / Director Signature & Seal</b>", normal_cell),
        ]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    sign_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAFA')),
    ]))
    elements.append(sign_table)
    elements.append(Spacer(1, 8))

    # QR Code & Verification Token Footer
    qr_buffer = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buffer, width=0.85*inch, height=0.85*inch)
    doc_num = student_info.get('doc_number', f"TRANS-{student_info.get('student_id', '1001')}")

    footer_data = [
        [
            qr_img,
            Paragraph(
                f"<b>OFFICIAL TRANSCRIPT VERIFICATION CODE:</b> <font fontName='Courier-Bold' color='#1E3A8A'>{doc_num}</font><br/>"
                f"<font size=7.5 color='#64748B'>This official academic transcript is cryptographically verified. "
                f"Universities, embassies, and admission offices can verify authenticity at: <font color='#1E40AF'><b>{verification_url}</b></font></font>",
                normal_cell
            )
        ]
    ]
    footer_table = Table(footer_data, colWidths=[70, 470])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
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
        pagesize=letter_pagesize,
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
        pagesize=letter_pagesize,
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
        pagesize=letter_pagesize,
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

