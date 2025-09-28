import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from django.conf import settings

def generate_report_pdf(processed_result, filename=None):
    """
    processed_result: ProcessedResult instance
    """
    data = processed_result.data

    # Output path
    reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    if not filename:
        filename = f"report_{processed_result.id}.pdf"
    output_path = os.path.join(reports_dir, filename)

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.darkblue)
    c.drawString(1 * inch, height - 1 * inch, "Medical Lab Report Analysis")

    # Patient Details
    patient = data.get("patient_details", {})
    y = height - 1.5 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "Patient Details:")
    y -= 0.3 * inch
    c.setFont("Helvetica", 10)
    for key, value in patient.items():
        c.drawString(1.2 * inch, y, f"{key.capitalize()}: {value}")
        y -= 0.2 * inch

    # Abnormal Findings
    abnormalities = data.get("abnormal_findings", [])
    if abnormalities:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.red)
        c.drawString(1 * inch, y - 0.3 * inch, "⚠ Abnormal Findings:")
        y -= 0.5 * inch
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.black)
        for ab in abnormalities:
            c.drawString(
                1.2 * inch, y,
                f"{ab['test_name']} = {ab['result']} [{ab['flag']}] → {ab['interpretation']}"
            )
            y -= 0.3 * inch

    # Clinical Summary
    summary = data.get("clinical_summary", {})
    if summary:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y - 0.3 * inch, "Clinical Summary:")
        y -= 0.4 * inch
        c.setFont("Helvetica", 10)
        c.drawString(1.2 * inch, y, f"Main Findings: {summary.get('main_findings')}")
        y -= 0.3 * inch
        c.drawString(1.2 * inch, y, f"Possible Causes: {summary.get('possible_causes')}")
        y -= 0.3 * inch
        c.drawString(1.2 * inch, y, f"Next Steps: {summary.get('next_steps')}")

    c.showPage()
    c.save()

    return output_path
