import sys
import argparse
from pathlib import Path

try:
    from fpdf import FPDF
except ImportError:
    print("fpdf not found. Please install it with: pip install fpdf")
    sys.exit(1)

class ReportPDF(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 10)
        self.set_text_color(150)
        self.cell(0, 10, "RobotJudge-CI - Detailed Project Description", align="R")
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_pdf(input_path, output_path):
    in_file = Path(input_path)
    if not in_file.exists():
        print(f"Error: {in_file} not found.")
        sys.exit(1)

    text = in_file.read_text(encoding="utf-8")
    lines = text.split("\n")

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Set left margin manually to ensure space
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    
    # Title
    pdf.set_font("helvetica", "B", 20)
    pdf.set_text_color(50, 50, 150)
    pdf.multi_cell(180, 12, "RobotJudge-CI: Detailed Project Description & Architecture")
    pdf.ln(10)

    def sanitize(t):
        return t.replace("\u2014", "-").replace("\u2013", "-").replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'").replace("\u2022", "*").replace("`", "")

    for line_num, line in enumerate(lines):
        line = sanitize(line.strip())
        if not line:
            pdf.ln(4)
            continue
            
        if line.startswith("# RobotJudge-CI: Detailed Project Description"):
            continue

        try:
            # Headers
            if line.startswith("## "):
                pdf.ln(6)
                pdf.set_font("helvetica", "B", 14)
                pdf.set_text_color(70, 70, 70)
                pdf.multi_cell(180, 10, line[3:])
                pdf.ln(2)
            elif line.startswith("### "):
                pdf.ln(4)
                pdf.set_font("helvetica", "B", 12)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(180, 8, line[4:])
                pdf.ln(1)
            elif line.startswith("- "):
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(0)
                clean_line = line.replace("**", "")
                pdf.multi_cell(180, 6, f" - {clean_line[2:]}")
            elif line.startswith("**"):
                pdf.set_font("helvetica", "B", 11)
                pdf.set_text_color(0)
                # Just strip the ** and print bold for the whole line for simplicity in this script
                pdf.multi_cell(180, 6, line.replace("**", ""))
            else:
                pdf.set_font("helvetica", "", 11)
                pdf.set_text_color(30, 30, 30)
                clean_line = line.replace("**", "")
                pdf.multi_cell(180, 6, clean_line)
        except Exception as e:
            print(f"Error on line {line_num}: {line}")
            raise e

    pdf.output(str(output_path))
    print(f"[SUCCESS] PDF created: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate PDF from Markdown')
    parser.add_argument('input', help='Input Markdown file')
    parser.add_argument('output', help='Output PDF file')
    args = parser.parse_args()
    
    generate_pdf(args.input, args.output)
