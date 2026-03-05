import sys
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf not found. Please install it with: pip install fpdf")
    sys.exit(1)

# Ensure project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_MD = PROJECT_ROOT / "docs" / "requirement_checklist.md"
PDF_OUT = PROJECT_ROOT / "requirement_checklist.pdf"

class ReportPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 10)
        self.set_text_color(150)
        self.cell(0, 10, "RobotJudge-CI - Requirements Verification", align="R")
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_pdf():
    if not INPUT_MD.exists():
        print(f"Error: {INPUT_MD} not found.")
        return

    text = INPUT_MD.read_text(encoding="utf-8")
    lines = text.split("\n")

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Set left margin manually to ensure space
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    
    # Title
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(50, 50, 150)
    pdf.multi_cell(180, 12, "Requirements Verification Checklist")
    pdf.ln(10)

    def sanitize(t):
        return t.replace("\u2014", "-").replace("\u2013", "-").replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace("\u2022", "*").replace("`", "")

    for line_num, line in enumerate(lines):
        line = sanitize(line.strip())
        if not line:
            pdf.ln(5)
            continue
            
        if line.startswith("# Requirements Verification Checklist"):
            continue

        try:
            # Headers
            if line.startswith("## "):
                pdf.ln(5)
                pdf.set_font("helvetica", "B", 14)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(180, 10, line[3:])
                pdf.ln(2)
            elif line.startswith("### "):
                pdf.ln(3)
                pdf.set_font("helvetica", "B", 12)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(180, 8, line[4:])
                pdf.ln(1)
            elif line.startswith("- "):
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(0)
                clean_line = line.replace("**", "")
                pdf.multi_cell(180, 7, f" - {clean_line[2:]}")
            elif line.startswith("**"):
                pdf.set_font("helvetica", "B", 11)
                pdf.set_text_color(0)
                pdf.multi_cell(180, 6, line.replace("**", ""))
            else:
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(30, 30, 30)
                clean_line = line.replace("**", "")
                pdf.multi_cell(180, 6, clean_line)
        except Exception as e:
            print(f"Error on line {line_num}: {line}")
            raise e

    pdf.output(str(PDF_OUT))
    print(f"[SUCCESS] PDF created: {PDF_OUT}")

if __name__ == "__main__":
    generate_pdf()
