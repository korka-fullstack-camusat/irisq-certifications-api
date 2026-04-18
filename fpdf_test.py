from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("helvetica", "", 10)
pdf.multi_cell(190, 6, "Q1. Quelle est la capitale de la France ?")
pdf.multi_cell(190, 6, "Reponse choisie : Paris")
pdf.output("test.pdf")
