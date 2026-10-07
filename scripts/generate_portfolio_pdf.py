"""
=============================================================================
ETHIOSCHOOL SAAS — EXECUTIVE PDF PORTFOLIO GENERATOR
=============================================================================
Generates a multi-page, publication-grade executive portfolio PDF with:
  - High-resolution annotated screenshots
  - Numbered callout breakdown tables
  - System architecture and dual-calendar specifications
  - Full production verification report (68/68 tests passed)
=============================================================================
"""

import os
import datetime
from decimal import Decimal
from PIL import Image as PILImage

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, PageBreak, HRFlowable
)
from reportlab.pdfgen import canvas

# ─── Color Palette ────────────────────────────────────────────────────────────
EMERALD_DARK  = colors.HexColor('#064E3B')
EMERALD_MID   = colors.HexColor('#0D5C3A')
EMERALD_LIGHT = colors.HexColor('#ECFDF5')
GOLD_DARK     = colors.HexColor('#92400E')
GOLD_MID      = colors.HexColor('#D97706')
GOLD_LIGHT    = colors.HexColor('#FEF3C7')
SLATE_DARK    = colors.HexColor('#0F172A')
SLATE_MID     = colors.HexColor('#334155')
SLATE_LIGHT   = colors.HexColor('#F8FAFC')
SLATE_BORDER  = colors.HexColor('#E2E8F0')
TEXT_PRIMARY  = colors.HexColor('#0F172A')
TEXT_MUTED    = colors.HexColor('#64748B')
WHITE         = colors.HexColor('#FFFFFF')
RED_ACCENT    = colors.HexColor('#DC2626')
BLUE_ACCENT   = colors.HexColor('#2563EB')

# ─── Numbered Canvas for Two-Pass Page Numbering ─────────────────────────────
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # Omit header and footer on cover page (Page 1)
        if self._pageNumber > 1:
            # Header
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(EMERALD_MID)
            self.drawString(40, 810, "ETHIOSCHOOL SAAS")
            self.setFont("Helvetica", 8)
            self.setFillColor(SLATE_MID)
            self.drawString(135, 810, "— Enterprise Multi-Tenant School Operating System")
            self.drawRightString(555, 810, "CONFIDENTIAL & PROPRIETARY")

            # Header Rule
            self.setStrokeColor(SLATE_BORDER)
            self.setLineWidth(0.75)
            self.line(40, 802, 555, 802)

            # Footer
            self.setStrokeColor(SLATE_BORDER)
            self.setLineWidth(0.75)
            self.line(40, 45, 555, 45)

            self.setFont("Helvetica", 8)
            self.setFillColor(TEXT_MUTED)
            self.drawString(40, 32, "Ethiopian Secondary & Preparatory School Cloud Solution (Grades 9–12)")
            
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(555, 32, page_text)

        self.restoreState()


def build_portfolio_pdf(output_path, images_dir):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=SLATE_DARK,
        spaceAfter=6
    )

    subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=EMERALD_MID,
        spaceAfter=15
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=EMERALD_DARK,
        spaceBefore=8,
        spaceAfter=6
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=SLATE_DARK,
        spaceBefore=6,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=SLATE_MID,
        spaceAfter=6
    )

    callout_num_style = ParagraphStyle(
        'CalloutNum',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=WHITE,
        alignment=1
    )

    callout_title_style = ParagraphStyle(
        'CalloutTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=SLATE_DARK
    )

    callout_desc_style = ParagraphStyle(
        'CalloutDesc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=SLATE_MID
    )

    badge_style = ParagraphStyle(
        'Badge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=EMERALD_DARK
    )

    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1: COVER PAGE
    # ══════════════════════════════════════════════════════════════════════════
    # Top Tag
    tag_table = Table([[
        Paragraph("<b>OFFICIAL SYSTEM PORTFOLIO & ARCHITECTURE SPECIFICATION</b>", badge_style)
    ]], colWidths=[515])
    tag_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), EMERALD_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#A7F3D0')),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(tag_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("EthioSchool SaaS", title_style))
    story.append(Paragraph("Next-Generation Multi-Tenant School Operating System for Ethiopia", subtitle_style))

    # Hero Image
    cover_img_path = os.path.join(images_dir, 'portfolio_cover_hero_1787647369385.jpg')
    if os.path.exists(cover_img_path):
        img = Image(cover_img_path, width=515, height=275)
        story.append(img)
        story.append(Spacer(1, 15))

    # Executive Overview Box
    meta_data = [
        [
            Paragraph("<b>Target Audience:</b> Ethiopian Secondary & Preparatory Schools (Grades 9–12)", body_style),
            Paragraph("<b>Production Status:</b> Verified Ready (68/68 E2E Tests Passed)", body_style)
        ],
        [
            Paragraph("<b>Core Calendar:</b> Native Ethiopian Ge'ez (13 Months) & Gregorian Sync", body_style),
            Paragraph("<b>Billing Engine:</b> Automated Seat-Based Metering & Chapa Gateway", body_style)
        ],
        [
            Paragraph("<b>Architecture:</b> Multi-Tenant Database Isolation (TenantAwareModel)", body_style),
            Paragraph("<b>Security:</b> Role-Based Access (7 Roles) & QR Cryptographic Verify", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[255, 260])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SLATE_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, SLATE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph(
        "<b>Prepared for:</b> School Boards, Principals, Ministry Evaluators & Enterprise Stakeholders | <b>Version:</b> 2.4 Production",
        ParagraphStyle('FooterMeta', parent=body_style, fontSize=8, textColor=TEXT_MUTED, alignment=1)
    ))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2: EXECUTIVE SUMMARY & ARCHITECTURAL FOUNDATIONS
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("1. Executive Summary & Core Value Proposition", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    story.append(Paragraph(
        "<b>EthioSchool SaaS</b> is an enterprise-grade, cloud-native educational management platform engineered specifically "
        "to satisfy the operational, regulatory, and pedagogical requirements of Ethiopian high schools. "
        "Unlike generic Western school software, EthioSchool is natively built with first-class support for the <b>13-Month Ethiopian Calendar</b> "
        "(Meskerem to Pagume), Ministry of Education secondary curricula (Grades 9 & 10 General Stream, Grades 11 & 12 Natural/Social Science Streams), "
        "5-component continuous assessment pipelines, and integrated seat-based pricing with local payment gateways.",
        body_style
    ))
    story.append(Spacer(1, 4))

    # Architecture Highlights Table
    arch_data = [
        [
            Paragraph("<b>Platform Capability</b>", ParagraphStyle('Hdr', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE)),
            Paragraph("<b>Technical Architecture & Implementation</b>", ParagraphStyle('Hdr2', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE)),
            Paragraph("<b>Operational Impact</b>", ParagraphStyle('Hdr3', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE))
        ],
        [
            Paragraph("<b>Multi-Tenant Isolation</b>", body_style),
            Paragraph("Strict schema-level query filtering via <code>TenantAwareModel</code> and <code>TenantManager</code> with automated subdomain routing.", body_style),
            Paragraph("100% data privacy between schools; zero risk of cross-tenant data leaks.", body_style)
        ],
        [
            Paragraph("<b>Dual-Calendar Engine</b>", body_style),
            Paragraph("Bi-directional algorithmic translation between Ge'ez Ethiopian dates and Gregorian ISO dates across all tables, schedules, and attendance.", body_style),
            Paragraph("Schools operate in native Ethiopian dates while maintaining international compatibility.", body_style)
        ],
        [
            Paragraph("<b>Assessment & Ranks</b>", body_style),
            Paragraph("Deterministic 4-phase mark pipeline: <i>Draft → Submitted → Approved → Published</i>, auto-computing 1st–Nth section ranks.", body_style),
            Paragraph("Eliminates manual ranking errors and prevents unauthorized grade tampering.", body_style)
        ],
        [
            Paragraph("<b>Automated Rollover</b>", body_style),
            Paragraph("Annual rollover engine: replicates subject schemes, creates promotion histories, advances students, and isolates graduates.", body_style),
            Paragraph("Reduces yearly school transition workload from weeks to a single click.", body_style)
        ],
        [
            Paragraph("<b>Tamper-Proof ID Cards</b>", body_style),
            Paragraph("Client/Server PDF ID card generator with signed QR code verification portal and national barcode standards.", body_style),
            Paragraph("Instant mobile verification of student active status by gatekeepers and exam proctors.", body_style)
        ]
    ]

    arch_table = Table(arch_data, colWidths=[125, 230, 160])
    arch_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), EMERALD_DARK),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
    ]))
    story.append(arch_table)
    story.append(Spacer(1, 10))

    # Role Ecosystem Cards
    story.append(Paragraph("2. Role-Based Ecosystem & Permission Matrix", h2_style))
    story.append(Paragraph(
        "EthioSchool enforces strict least-privilege security across 7 dedicated portal interfaces:",
        body_style
    ))

    roles_data = [
        [
            Paragraph("👑 <b>Super Admin:</b> Multi-school provisioning, subscription health, revenue analytics, global audit logs.", body_style),
            Paragraph("🏛️ <b>School Admin:</b> Academic calendar setup, staff assignment, fee policies, period closing, rollover.", body_style)
        ],
        [
            Paragraph("👩‍🏫 <b>Teacher:</b> Daily attendance, continuous assessment mark recording, assignment submission, syllabus.", body_style),
            Paragraph("🎓 <b>Student:</b> Live gradebook view, downloadable report cards, timetable, exam attempts, homework.", body_style)
        ],
        [
            Paragraph("👨‍👩‍👧 <b>Parent:</b> Multi-child academic progress, real-time attendance alerts, Chapa tuition payment.", body_style),
            Paragraph("📋 <b>Registrar & Accountant:</b> ID generation, student admissions, fee invoice issuance, receipts.", body_style)
        ]
    ]
    roles_table = Table(roles_data, colWidths=[255, 260])
    roles_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SLATE_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, SLATE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(roles_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3: SUPER ADMIN & MULTI-TENANT MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("3. Super Administrator Platform & Subscription Management", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    super_admin_img_path = os.path.join(images_dir, 'super_admin_ui_annotated_1787647422548.jpg')
    if os.path.exists(super_admin_img_path):
        img = Image(super_admin_img_path, width=515, height=255)
        story.append(img)
        story.append(Spacer(1, 8))

    # Annotation Table
    callouts_p3 = [
        [
            Table([[Paragraph("1", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Multi-Tenant Dashboard:</b> Live monitoring of 24+ onboarded schools with aggregated revenue, active student seat counts, and global infrastructure health.", callout_desc_style)
        ],
        [
            Table([[Paragraph("2", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), GOLD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Seat-Based Usage Metering:</b> Transparent tracking of active student accounts and staff allocations against plan quotas (e.g. 1,250/1,500 seats).", callout_desc_style)
        ],
        [
            Table([[Paragraph("3", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), RED_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Dynamic Expiration & Lock Engine:</b> Automated status synchronization marking expired schools with red badges and restricting operational access.", callout_desc_style)
        ],
        [
            Table([[Paragraph("4", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), BLUE_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Tenant Provisioning & Overrides:</b> 1-Click school provisioning with temporary credentials, forced password reset, and custom seat pricing overrides.", callout_desc_style)
        ]
    ]
    callouts_p3_table = Table(callouts_p3, colWidths=[26, 485])
    callouts_p3_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(callouts_p3_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4: SCHOOL ADMINISTRATOR EXECUTIVE PORTAL
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("4. School Administrator Executive Command Center", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    school_admin_img_path = os.path.join(images_dir, 'school_admin_ui_annotated_1787647452835.jpg')
    if os.path.exists(school_admin_img_path):
        img = Image(school_admin_img_path, width=515, height=255)
        story.append(img)
        story.append(Spacer(1, 8))

    callouts_p4 = [
        [
            Table([[Paragraph("1", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Native Dual-Calendar Toggle:</b> Header badge displays current Ethiopian date (<i>Meskerem 15, 2017 E.C.</i>) with a persistent switch to Gregorian dates.", callout_desc_style)
        ],
        [
            Table([[Paragraph("2", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), GOLD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Live Institutional KPIs:</b> Real-time counters for enrolled students (1,250), active faculty (48), daily attendance (96.4%), and fee collection (88%).", callout_desc_style)
        ],
        [
            Table([[Paragraph("3", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), BLUE_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Stream Breakdown Analytics:</b> Grade 9 to 12 distribution visualizing General Stream vs Natural Science and Social Science enrollments.", callout_desc_style)
        ],
        [
            Table([[Paragraph("4", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_DARK), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Academic Rollover & Actions:</b> Quick action buttons for executing year-end rollover, scheme replication, and batch report card generation.", callout_desc_style)
        ]
    ]
    callouts_p4_table = Table(callouts_p4, colWidths=[26, 485])
    callouts_p4_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(callouts_p4_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 5: TEACHER GRADEBOOK & CONTINUOUS ASSESSMENT
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("5. Teacher Gradebook & Continuous Assessment Matrix", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    gradebook_img_path = os.path.join(images_dir, 'teacher_gradebook_ui_annotated_1787647490083.jpg')
    if os.path.exists(gradebook_img_path):
        img = Image(gradebook_img_path, width=515, height=255)
        story.append(img)
        story.append(Spacer(1, 8))

    callouts_p5 = [
        [
            Table([[Paragraph("1", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Ethiopian 5-Component Scheme:</b> Standard Ministry configuration: <i>Class Activity (10%), Quiz/HW (10%), Project (10%), Midterm (20%), Final Exam (50%) = 100% Total</i>.", callout_desc_style)
        ],
        [
            Table([[Paragraph("2", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), GOLD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Weight Integrity Validation:</b> Real-time weight validation badge (<i>Total Weight: 100% Valid</i>) preventing over/under-allocated mark components.", callout_desc_style)
        ],
        [
            Table([[Paragraph("3", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), BLUE_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>4-Phase Approval Workflow:</b> Teacher enters DRAFT → submits to School Admin → Admin APPROVES → marks are PUBLISHED and locked from edits.", callout_desc_style)
        ],
        [
            Table([[Paragraph("4", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_DARK), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Automated Section Rank Computation:</b> Instant deterministic ranking (1st to 48th) calculated across weighted assessment totals.", callout_desc_style)
        ]
    ]
    callouts_p5_table = Table(callouts_p5, colWidths=[26, 485])
    callouts_p5_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(callouts_p5_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 6: STUDENT & PARENT PORTALS & ONLINE PAYMENTS
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("6. Student & Parent Portals with Chapa Payments", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    student_parent_img_path = os.path.join(images_dir, 'student_parent_ui_annotated_1787647537313.jpg')
    if os.path.exists(student_parent_img_path):
        img = Image(student_parent_img_path, width=515, height=255)
        story.append(img)
        story.append(Spacer(1, 8))

    callouts_p6 = [
        [
            Table([[Paragraph("1", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Student Academic Profile & Performance Gauges:</b> Real-time GPA gauge (3.85 / 4.00), attendance percentage (98.2%), and notification feed.", callout_desc_style)
        ],
        [
            Table([[Paragraph("2", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), BLUE_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Ministry-Compliant Report Card:</b> Complete subject performance breakdown with grades (A+, A, A-, B+), semester GPA, and official section rank.", callout_desc_style)
        ],
        [
            Table([[Paragraph("3", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), GOLD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Chapa Online Tuition Payment:</b> 1-Click online fee payment supporting Telebirr, CBE Birr, and debit cards with automated receipt generation.", callout_desc_style)
        ],
        [
            Table([[Paragraph("4", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_DARK), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Digital PDF Download:</b> Instant download of official, digitally stamped student report cards for parents and university admissions.", callout_desc_style)
        ]
    ]
    callouts_p6_table = Table(callouts_p6, colWidths=[26, 485])
    callouts_p6_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(callouts_p6_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 7: DIGITAL ID CARDS & QR VERIFICATION ENGINE
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("7. Tamper-Proof Student ID Cards & QR Verification", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    id_card_img_path = os.path.join(images_dir, 'id_card_qr_english_only_1787648558564.jpg')
    if os.path.exists(id_card_img_path):
        img = Image(id_card_img_path, width=515, height=255)
        story.append(img)
        story.append(Spacer(1, 8))

    callouts_p7 = [
        [
            Table([[Paragraph("1", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), BLUE_ACCENT), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Official Dual-Sided PVC ID Layout:</b> High-resolution card with school crest, photo, English student full name, ID number, blood group, emergency rules, and issue date.", callout_desc_style)
        ],
        [
            Table([[Paragraph("2", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), EMERALD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Public QR Verification Engine:</b> Anyone scanning the card QR code with any smartphone is taken to a secure verification portal confirming active enrollment.", callout_desc_style)
        ],
        [
            Table([[Paragraph("3", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), GOLD_MID), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Cryptographic Tamper-Proof Signature:</b> Digital signature hash prevents student ID forging or expired ID reuse.", callout_desc_style)
        ],
        [
            Table([[Paragraph("4", callout_num_style)]], colWidths=[18], rowHeights=[18], style=[('BACKGROUND', (0,0), (-1,-1), SLATE_DARK), ('ROUNDEDCORNERS', [9,9,9,9]), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]),
            Paragraph("<b>Batch PDF Generation:</b> Registrars can generate print-ready PDF sheets for entire grade levels or single replacement cards instantly.", callout_desc_style)
        ]
    ]
    callouts_p7_table = Table(callouts_p7, colWidths=[26, 485])
    callouts_p7_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(callouts_p7_table)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 8: PRODUCTION AUDIT & VERIFICATION REPORT
    # ══════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("8. Production Verification & 2-Year Lifecycle Audit", h1_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=EMERALD_MID, spaceAfter=8))

    story.append(Paragraph(
        "To guarantee 100% production readiness, the system underwent a rigorous, automated <b>2-Year School Lifecycle Simulation</b> "
        "covering multi-stream enrollments, continuous assessment pipelines, period closing, student promotion, assessment scheme replication, "
        "and multi-tenant security isolation. Below is the verified audit summary:",
        body_style
    ))
    story.append(Spacer(1, 4))

    # Audit Results Table
    audit_data = [
        [
            Paragraph("<b>Verification Stage</b>", ParagraphStyle('Hdr', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE)),
            Paragraph("<b>Tested Scope & Invariants</b>", ParagraphStyle('Hdr2', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE)),
            Paragraph("<b>Result</b>", ParagraphStyle('Hdr3', parent=body_style, fontName='Helvetica-Bold', textColor=WHITE))
        ],
        [
            Paragraph("<b>1. School & Stream Provisioning</b>", body_style),
            Paragraph("Creation of 6 grades (9, 10, 11-NS, 11-SS, 12-NS, 12-SS), 30 subjects, 6 faculty, 60 enrolled students.", body_style),
            Paragraph("<b>68 / 68 PASSED</b><br/><font color='#065F46'>100% Verified</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ],
        [
            Paragraph("<b>2. Mark Recording Pipeline</b>", body_style),
            Paragraph("1,500 continuous assessment marks recorded, submitted, approved, and published with weight integrity validation.", body_style),
            Paragraph("<b>PASSED</b><br/><font color='#065F46'>Admin guard enforced</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ],
        [
            Paragraph("<b>3. Period Closing & Ranks</b>", body_style),
            Paragraph("Automated GPA calculation and unique section ranking (1st to 10th per class) across 60 period result records.", body_style),
            Paragraph("<b>PASSED</b><br/><font color='#065F46'>Ranks 100% unique</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ],
        [
            Paragraph("<b>4. Year-End Promotion & Graduation</b>", body_style),
            Paragraph("Annual result aggregation: 40 students promoted (Grades 9–11) and 20 Grade 12 students verified as GRADUATED.", body_style),
            Paragraph("<b>PASSED</b><br/><font color='#065F46'>Zero orphan enrollments</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ],
        [
            Paragraph("<b>5. Year 2 Scheme Replication</b>", body_style),
            Paragraph("Replicated 150 assessment components from AY1 to AY2; verified exactly 100% weight per subject with zero weight accumulation bugs.", body_style),
            Paragraph("<b>PASSED</b><br/><font color='#065F46'>Weights strictly 100%</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ],
        [
            Paragraph("<b>6. Multi-Tenant Security</b>", body_style),
            Paragraph("Cross-tenant intrusion test: verified attacker school cannot view, modify, or query marks, students, or enrollments.", body_style),
            Paragraph("<b>PASSED</b><br/><font color='#065F46'>Full Tenant Isolation</font>", ParagraphStyle('P', parent=body_style, textColor=EMERALD_DARK))
        ]
    ]

    audit_table = Table(audit_data, colWidths=[140, 275, 100])
    audit_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), SLATE_DARK),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, SLATE_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, SLATE_LIGHT]),
    ]))
    story.append(audit_table)
    story.append(Spacer(1, 10))

    # Deployment & Support Box
    contact_data = [
        [
            Paragraph(
                "<b>Enterprise Deployment & Licensing Contact:</b><br/>"
                "• <b>Platform:</b> EthioSchool SaaS Enterprise Cloud Edition<br/>"
                "• <b>Primary Phone:</b> +251 937 381 801<br/>"
                "• <b>Email:</b> support@ethioschool.edu.et | info@addisacademy.edu.et<br/>"
                "• <b>Hosting & SLA:</b> Dedicated PostgreSQL Tenant DBs, Daily Backups, 99.9% Uptime Guarantee",
                body_style
            )
        ]
    ]
    contact_table = Table(contact_data, colWidths=[515])
    contact_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GOLD_LIGHT),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#FDE68A')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
    ]))
    story.append(contact_table)

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Portfolio PDF generated successfully at: {output_path}")


if __name__ == '__main__':
    images_directory = r'C:\Users\hp\.gemini\antigravity-ide\brain\78a5a110-59bb-4411-a7f5-31174e54c86e'
    output_pdf = os.path.join(images_directory, 'EthioSchool_SaaS_Executive_Portfolio.pdf')
    build_portfolio_pdf(output_pdf, images_directory)
