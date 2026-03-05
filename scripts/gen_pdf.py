import sys
from pathlib import Path
from fpdf import FPDF

# Ensure project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEECH_MD = PROJECT_ROOT / "docs" / "ci_speech.md"
PDF_OUT = PROJECT_ROOT / "ci_integration_speech.pdf"

class SpeechPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 10)
        self.set_text_color(150)
        self.cell(0, 10, "RobotJudge-CI - System Integration Speech", align="R")
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_pdf():
    if not SPEECH_MD.exists():
        print(f"Error: {SPEECH_MD} not found.")
        return

    text = SPEECH_MD.read_text(encoding="utf-8")
    lines = text.split("\n")

    pdf = SpeechPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Set left margin manually to ensure space
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    
    # Title
    pdf.set_font("helvetica", "B", 24)
    pdf.set_text_color(50, 50, 150)
    pdf.multi_cell(180, 12, "RobotJudge CI Integration Speech")
    pdf.ln(10)

    def sanitize(t):
        # Replace common unicode chars that Helvetica/Latin-1 dislikes
        return t.replace("\u2014", "-").replace("\u2013", "-").replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace("\u2022", "*")

    for line_num, line in enumerate(lines):
        line = sanitize(line.strip())
        if not line:
            pdf.ln(5)
            continue

        try:
            # Headers
            if line.startswith("## "):
                pdf.ln(5)
                pdf.set_font("helvetica", "B", 16)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(180, 10, line[3:])
                pdf.ln(2)
            elif line.startswith("### "):
                pdf.ln(3)
                pdf.set_font("helvetica", "B", 13)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(180, 8, line[4:])
                pdf.ln(1)
            elif line.startswith("#### "):
                pdf.set_font("helvetica", "B", 11)
                pdf.set_text_color(0)
                pdf.multi_cell(180, 7, line[5:])
            elif line.startswith("- "):
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(0)
                pdf.multi_cell(180, 7, f" • {line[2:]}")
            else:
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(30, 30, 30)
                clean_line = line.replace("**", "")
                pdf.multi_cell(180, 6, clean_line)
        except Exception as e:
            print(f"Error on line {line_num}: {line}")
            raise e

    pdf.output(str(PDF_OUT))
    print(f"✅ PDF created: {PDF_OUT}")

if __name__ == "__main__":
    generate_pdf()
