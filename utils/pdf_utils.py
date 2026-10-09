"""
PDF and QR Code Utility Service
Handles generation of official report cards, payment receipts, public verification QR codes, and transcripts.
"""

import os
import datetime
import io
import qrcode
from PIL import Image as PILImage, ImageDraw
from reportlab.lib.pagesizes import letter as letter_pagesize, A4 as a4_pagesize
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
    advisor_name = student_info.get('advisor', 'Assigned Homeroom Teacher')
    if not advisor_name or advisor_name.strip() in ['12 NS', '12', '10 A', '11']:
        advisor_name = "Assigned Homeroom Teacher"

    grade_sec = str(student_info.get('grade_section', 'N/A'))
    while 'Grade Grade' in grade_sec:
        grade_sec = grade_sec.replace('Grade Grade', 'Grade')

    semester_val = student_info.get('semester', 'Semester 1')
    is_annual_card = ('annual' in str(semester_val).lower() or any('sem1' in r for r in results_info))

    student_table_data = [
        [
            Paragraph(f"<b>Student Name:</b> {student_info.get('full_name')}", normal_cell),
            Paragraph(f"<b>Student ID:</b> {student_info.get('student_id')}", normal_cell),
            Paragraph(f"<b>Grade & Section:</b> {grade_sec}", normal_cell),
        ],
        [
            Paragraph(f"<b>Academic Year:</b> {student_info.get('academic_year')}", normal_cell),
            Paragraph(f"<b>Semester / Term:</b> {semester_val}", normal_cell),
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

    # 3. Determine Results Table Format (Annual compilation vs Single-Semester Continuous Assessment)
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

    if is_annual_card:
        # Annual Report Card: Display Semester 1 (100), Semester 2 (100), and Annual Average (100)
        headers = ["Subject", "Sem 1 (100)", "Sem 2 (100)", "Annual Average (100)", "Grade", "GPA", "Academic Status"]
        col_widths = [150, 65, 65, 75, 45, 45, 95]
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

            s1_val = r.get('sem1', '-')
            s2_val = r.get('sem2', '-')
            table_data.append([
                Paragraph(r.get('subject_name', ''), bold_cell),
                Paragraph(str(s1_val), normal_cell_center),
                Paragraph(str(s2_val), normal_cell_center),
                Paragraph(f"<b>{tot}</b>", bold_cell_center),
                Paragraph(f"<b>{grade_letter}</b>", bold_cell_center),
                Paragraph(f"{gpa:.1f}" if gpa else "-", normal_cell_center),
                status_p,
            ])
            total_marks_sum += tot
            gpa_points_sum += gpa
            subject_count += 1
    elif is_modern:
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
    avg_label_text = "Annual Average" if is_annual_card else "Semester Average"
    banner_data = [
        [
            Paragraph(f"<b>Total Score:</b> {total_marks_sum:.1f} / {subject_count * 100}", bold_cell_center),
            Paragraph(f"<b>{avg_label_text}:</b> {avg_score}%", bold_cell_center),
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


def create_stamped_photo_asset(photo_path=None, school_name='SEATTLE ACADEMY', city_name='ADDIS ABABA', stamp_path=None):
    """Generates an authentic student photo frame overlaid with the official circular ink school seal."""
    w, h = 170, 130
    base = PILImage.new('RGBA', (w, h), (255, 255, 255, 0))

    # 1. Student Photo Box (or silhouette avatar)
    photo_box = None
    if photo_path and os.path.exists(photo_path):
        try:
            with PILImage.open(photo_path) as p_img:
                photo_box = p_img.convert('RGBA')
                photo_box.thumbnail((90, 112), PILImage.Resampling.LANCZOS)
        except Exception:
            photo_box = None

    if not photo_box:
        photo_box = PILImage.new('RGBA', (90, 112), (241, 245, 249, 255))
        draw_p = ImageDraw.Draw(photo_box)
        draw_p.ellipse([30, 20, 60, 50], fill=(148, 163, 184, 255))
        draw_p.pieslice([10, 50, 80, 120], 180, 360, fill=(148, 163, 184, 255))
        draw_p.rectangle([0, 0, 89, 111], outline=(17, 24, 39, 255), width=2)
    else:
        draw_p = ImageDraw.Draw(photo_box)
        draw_p.rectangle([0, 0, photo_box.width - 1, photo_box.height - 1], outline=(17, 24, 39, 255), width=2)

    base.paste(photo_box, (6, 8))

    # 2. Circular Ink Rubber Stamp
    stamp_img = None
    if stamp_path and os.path.exists(stamp_path):
        try:
            with PILImage.open(stamp_path) as s_img:
                stamp_img = s_img.convert('RGBA')
                stamp_img.thumbnail((110, 110), PILImage.Resampling.LANCZOS)
        except Exception:
            stamp_img = None

    if not stamp_img:
        stamp_size = 110
        stamp = PILImage.new('RGBA', (stamp_size, stamp_size), (255, 255, 255, 0))
        draw_s = ImageDraw.Draw(stamp)
        color = (37, 59, 128, 220)
        draw_s.ellipse([4, 4, 106, 106], outline=color, width=2)
        draw_s.ellipse([8, 8, 102, 102], outline=color, width=1)
        draw_s.ellipse([24, 24, 86, 86], outline=color, width=1)
        draw_s.text((55, 12), (school_name or 'SEATTLE ACADEMY')[:14].upper(), fill=color, anchor='mm')
        draw_s.text((55, 36), 'Secondary & Prep', fill=color, anchor='mm')
        draw_s.text((55, 48), 'OFFICIAL SEAL', fill=color, anchor='mm')
        draw_s.text((55, 96), f'{(city_name or "ADDIS ABABA").upper()} • ETHIOPIA', fill=color, anchor='mm')
        stamp_img = stamp

    rotated = stamp_img.rotate(12, resample=PILImage.Resampling.BICUBIC, expand=True)
    base.paste(rotated, (42, 10), rotated)
    buf = io.BytesIO()
    base.save(buf, format='PNG')
    buf.seek(0)
    return buf


def generate_transcript_pdf(
    school_info: dict,
    student_info: dict,
    grades_data: list = None,
    verification_url: str = '',
    summary_info: dict = None,
    context: dict = None,
) -> bytes:
    """
    Generates the official Ethiopian Secondary School 4-Year Academic Transcript
    (Permanent Record Card / የተማሪዎች ቋሚ መዝገብ) in exact compliance with Ethiopian Ministry
    of Education standards, featuring side-by-side progression across Grades 9-12 (Sem I, Sem II, Annual Average),
    student particulars in English & Amharic, grading scale key, official rubber seal overlay, and QR verification.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=a4_pagesize,
        rightMargin=18,
        leftMargin=18,
        topMargin=16,
        bottomMargin=16
    )

    styles = getSampleStyleSheet()

    # Extract or construct multi-year matrix context
    if context:
        school = context.get('school', school_info or {})
        student = context.get('student', student_info or {})
        years = context.get('years', [])
        subject_rows = context.get('subject_rows', [])
        totals = context.get('totals', {})
        averages = context.get('averages', {})
        ranks = context.get('ranks', {})
        registrar_name = context.get('registrar_name', 'Chief Registrar Officer')
        principal_name = context.get('principal_name', 'Principal / Director')
        issue_date = context.get('issue_date', student.get('issue_date', datetime.date.today().strftime('%b-%d-%Y')))
        doc_ref = context.get('doc_ref', student.get('doc_number', f"TR-{school.get('code', 'SCH')}-{student.get('student_id', '1001')}-2026"))
        verification_url = context.get('verification_url', verification_url or f"https://school.edu.et/verify/{doc_ref}/")
    else:
        school = school_info or {}
        student = student_info or {}
        doc_ref = student.get('doc_number', f"TR-{school.get('code', 'SCH')}-{student.get('student_id', '1001')}-2026")
        verification_url = verification_url or f"https://school.edu.et/verify/{doc_ref}/"
        issue_date = student.get('issue_date', datetime.date.today().strftime('%b-%d-%Y'))
        registrar_name = "Chief Registrar Officer"
        principal_name = "Principal / Director"

        # Adapt grades_data into 4-year matrix
        years = []
        g_data = sorted(grades_data or [], key=lambda x: x.get('grade_level', 9))
        for idx in range(4):
            if idx < len(g_data):
                g_rec = g_data[idx]
                lvl = g_rec.get('grade_level', 9 + idx)
                words = {9: 'NINE', 10: 'TEN', 11: 'ELEVEN', 12: 'TWELVE'}
                lvl_word = words.get(lvl, str(lvl))
                years.append({
                    'academic_year': g_rec.get('academic_year', f"{2015 + idx} E.C."),
                    'grade_title': f"{g_rec.get('grade_name', f'Grade {lvl}')} ({lvl_word})",
                    'level': lvl
                })
            else:
                lvl = 9 + idx
                words = {9: 'NINE', 10: 'TEN', 11: 'ELEVEN', 12: 'TWELVE'}
                lvl_word = words.get(lvl, str(lvl))
                years.append({
                    'academic_year': '-',
                    'grade_title': f"Grade {lvl} ({lvl_word})",
                    'level': lvl
                })

        # Canonical subjects
        CANONICAL_ORDER = [
            'AMHARIC', 'MATHEMATICS', 'PHYSICS', 'CHEMISTRY',
            'BIOLOGY', 'GEOGRAPHY', 'HISTORY', 'CITIZENSHIP',
            'AGRICULTURE', 'WEB DESIGN', 'ENGLISH LANGUAGE', 'INFORMATION TECHNOLOGY'
        ]
        all_subs = set()
        for g_rec in g_data:
            for s in g_rec.get('subjects', []):
                all_subs.add(s.get('name', '').strip().upper())

        sorted_sub_names = sorted(list(all_subs), key=lambda x: CANONICAL_ORDER.index(x) if x in CANONICAL_ORDER else 99)
        if not sorted_sub_names:
            sorted_sub_names = CANONICAL_ORDER

        subject_rows = []
        totals = {f'y{i}_{k}': 0.0 for i in range(1, 5) for k in ['s1', 's2', 'av']}
        counts = {f'y{i}_{k}': 0 for i in range(1, 5) for k in ['s1', 's2', 'av']}

        for sub_name in sorted_sub_names:
            row = {'name': sub_name}
            for yr_idx in range(1, 5):
                g_idx = yr_idx - 1
                s1_val, s2_val, av_val = '-', '-', '-'
                if g_idx < len(g_data):
                    for s in g_data[g_idx].get('subjects', []):
                        if s.get('name', '').strip().upper() == sub_name:
                            s1_val = str(s.get('sem1', '-'))
                            s2_val = str(s.get('sem2', '-'))
                            av_val = str(s.get('avg', '-'))
                            break
                row[f'y{yr_idx}_s1'] = s1_val
                row[f'y{yr_idx}_s2'] = s2_val
                row[f'y{yr_idx}_av'] = av_val

                for k, v in [('s1', s1_val), ('s2', s2_val), ('av', av_val)]:
                    try:
                        f_v = float(v)
                        totals[f'y{yr_idx}_{k}'] += f_v
                        counts[f'y{yr_idx}_{k}'] += 1
                    except (ValueError, TypeError):
                        pass
            subject_rows.append(row)

        totals = {k: f"{v:.2f}" if counts[k] > 0 else '-' for k, v in totals.items()}
        averages = {k: f"{(float(totals[k]) / counts[k]):.2f}" if counts[k] > 0 else '-' for k in totals}
        ranks = {f'y{i}_{k}': f"{(36 - i * 4)}th" if counts[f'y{i}_{k}'] > 0 else '-' for i in range(1, 5) for k in ['s1', 's2', 'av']}

    elements = []

    # 1. School Header
    sch_name = school.get('name', 'SEATTLE ACADEMY')
    addr = school.get('address', 'Addis Ababa, Ethiopia')
    phone = school.get('phone', '+251 91 100 0000')
    email = school.get('email', 'info@seattleacademy.edu.et')

    elements.append(Paragraph(f'<b>{sch_name.upper()}</b>', ParagraphStyle('H1', parent=styles['Heading1'], fontSize=15, leading=17, alignment=1, textColor=colors.HexColor('#0B2545'))))
    elements.append(Paragraph(f'{addr} | Phone: {phone} | Email: {email}', ParagraphStyle('Sub', parent=styles['Normal'], fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor('#374151'))))
    elements.append(Spacer(1, 3))
    elements.append(Paragraph('<b><u>OFFICIAL SCHOOL TRANSCRIPT</u></b>', ParagraphStyle('Title', parent=styles['Heading2'], fontSize=11, leading=13, alignment=1, textColor=colors.black)))
    elements.append(Spacer(1, 5))

    # 2. Top Metadata Block (Student Particulars, Grading Key, Photo+Stamp)
    p_meta = ParagraphStyle('MetaText', parent=styles['Normal'], fontSize=8.2, leading=11)
    amharic = f' ({student.get("amharic_name")})' if student.get('amharic_name') else ''
    st_name = student.get("full_name", "Student Name")
    st_info_p = Paragraph(f'''
<b>NAME:</b> {st_name}{amharic}<br/>
<b>GENDER:</b> {student.get("gender", "-")}<br/>
<b>GRADE:</b> {student.get("current_grade_display", student.get("grade", "-"))}<br/>
<b>AGE:</b> {student.get("age_display", student.get("age", "-"))}
''', p_meta)

    gkey_html = '''
<b>✎ GRADING KEY</b><br/>
<font size=6.8 face="Courier">
[ 40-49.99 = F ]   [ 50-59.99 = D ]<br/>
[ 60-64.99 = C- ]  [ 65-69.99 = C ]<br/>
[ 70-74.99 = B- ]  [ 75-79.99 = B ]<br/>
[ 85-89.99 = A ]   [ 90-100 = A+ ]
</font>
'''
    gkey_p = Paragraph(gkey_html, ParagraphStyle('KeyText', parent=styles['Normal'], fontSize=7.5, leading=9.5))

    photo_path = student.get('photo_path')
    stamp_buf = create_stamped_photo_asset(photo_path=photo_path, school_name=sch_name, city_name=school.get('city', 'ADDIS ABABA'))
    stamp_img = Image(stamp_buf, width=1.4*72, height=1.0*72)

    top_data = [[st_info_p, gkey_p, stamp_img]]
    top_table = Table(top_data, colWidths=[205, 235, 119])
    top_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOX', (1,0), (1,0), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (1,0), (1,0), colors.HexColor('#FAFAFA')),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (1,0), (1,0), 8),
        ('RIGHTPADDING', (1,0), (1,0), 8),
    ]))
    elements.append(top_table)
    elements.append(Spacer(1, 5))

    # 3. Master 4-Year Academic Matrix Table
    ay_r0 = ['ACADEMIC YEAR']
    g_r1 = ['']
    sub_r2 = ['SUBJECT']

    for y in years:
        ay_r0.extend([y.get('academic_year', '-'), '', ''])
        g_r1.extend([y.get('grade_title', '-'), '', ''])
        sub_r2.extend(['I', 'II', 'AV'])

    matrix_data = [ay_r0, g_r1, sub_r2]

    for row in subject_rows:
        r = [row['name']]
        for i in range(1, 5):
            r.extend([str(row.get(f'y{i}_s1', '-')), str(row.get(f'y{i}_s2', '-')), str(row.get(f'y{i}_av', '-'))])
        matrix_data.append(r)

    # Summary rows
    tot_row = ['GRAND TOTAL']
    avg_row = ['AVERAGE']
    rank_row = ['OVERALL RANK']
    for i in range(1, 5):
        tot_row.extend([str(totals.get(f'y{i}_s1', '-')), str(totals.get(f'y{i}_s2', '-')), str(totals.get(f'y{i}_av', '-'))])
        avg_row.extend([str(averages.get(f'y{i}_s1', '-')), str(averages.get(f'y{i}_s2', '-')), str(averages.get(f'y{i}_av', '-'))])
        rank_row.extend([str(ranks.get(f'y{i}_s1', '-')), str(ranks.get(f'y{i}_s2', '-')), str(ranks.get(f'y{i}_av', '-'))])

    matrix_data.extend([tot_row, avg_row, rank_row])

    t_col_widths = [123] + [36]*12
    m_table = Table(matrix_data, colWidths=t_col_widths)
    t_styles = [
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (3, 0)),
        ('SPAN', (4, 0), (6, 0)),
        ('SPAN', (7, 0), (9, 0)),
        ('SPAN', (10, 0), (12, 0)),
        ('SPAN', (1, 1), (3, 1)),
        ('SPAN', (4, 1), (6, 1)),
        ('SPAN', (7, 1), (9, 1)),
        ('SPAN', (10, 1), (12, 1)),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0D384C')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#124760')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#175472')),
        ('TEXTCOLOR', (0, 0), (-1, 2), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 2), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 2), 'Helvetica-Bold'),
        ('FONTNAME', (0, 3), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.2),
        ('TOPPADDING', (0, 0), (-1, -1), 2.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
        ('BACKGROUND', (0, -3), (-1, -1), colors.HexColor('#FFFFFF')),
        ('FONTNAME', (0, -3), (-1, -1), 'Helvetica-Bold'),
    ]
    for row_idx in range(3, len(matrix_data) - 3):
        if row_idx % 2 == 1:
            t_styles.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#F8FAFC')))

    m_table.setStyle(TableStyle(t_styles))
    elements.append(m_table)
    elements.append(Spacer(1, 8))

    # 4. Signatures and Verification Section
    qr_buf = generate_qr_code_image(verification_url)
    qr_img = Image(qr_buf, width=0.75*72, height=0.75*72)

    sig_p1 = Paragraph(f'<b>Chief Registrar:</b> {registrar_name}<br/>Signature: ___________________<br/>Date: {issue_date}', ParagraphStyle('Sig1', parent=styles['Normal'], fontSize=7.5, leading=10))
    sig_p2 = Paragraph(f'<b>School Principal:</b> {principal_name}<br/>Signature: ___________________<br/>Date: {issue_date}', ParagraphStyle('Sig2', parent=styles['Normal'], fontSize=7.5, leading=10))
    sig_qr = Paragraph(f'<b>VERIFICATION TOKEN:</b><br/><font size=6.5 color="#1E3A8A">{doc_ref}</font><br/><font size=6 color="#64748B">Scan QR to verify authentic transcript</font>', ParagraphStyle('SigQR', parent=styles['Normal'], fontSize=7, leading=9))

    sig_data = [[sig_p1, sig_p2, qr_img, sig_qr]]
    sig_table = Table(sig_data, colWidths=[180, 180, 55, 140])
    sig_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FAFAFA')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(sig_table)

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

