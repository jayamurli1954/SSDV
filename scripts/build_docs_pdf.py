import os
from xhtml2pdf import pisa

def convert_html_to_pdf(source_html_path, output_pdf_path):
    with open(source_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Simple clean CSS compatible with xhtml2pdf
    pdf_style = """
    <style>
      @page {
        size: a4 portrait;
        margin: 20mm 15mm 20mm 15mm;
      }
      body {
        font-family: Helvetica, Arial, sans-serif;
        font-size: 9.5pt;
        line-height: 1.45;
        color: #1e293b;
      }
      h1 { font-size: 18pt; color: #0f172a; margin-bottom: 8pt; border-bottom: 1.5pt solid #0284c7; padding-bottom: 4pt; }
      h2 { font-size: 13pt; color: #0f172a; margin-top: 14pt; margin-bottom: 6pt; border-bottom: 0.5pt solid #cbd5e1; padding-bottom: 2pt; }
      h3 { font-size: 11pt; color: #1e293b; margin-top: 10pt; margin-bottom: 4pt; }
      h4 { font-size: 10pt; color: #334155; margin-top: 8pt; margin-bottom: 3pt; }
      p { margin-bottom: 6pt; }
      img { max-width: 100%; margin: 8pt 0; text-align: center; }
      table { width: 100%; border-collapse: collapse; margin: 8pt 0; font-size: 8.5pt; }
      th, td { border: 0.5pt solid #cbd5e1; padding: 4pt 6pt; text-align: left; }
      th { background-color: #f1f5f9; color: #0f172a; font-weight: bold; }
      pre { background-color: #f8fafc; border: 0.5pt solid #cbd5e1; padding: 6pt; font-family: Courier; font-size: 8pt; margin: 6pt 0; }
      code { font-family: Courier; font-size: 8.5pt; background-color: #f1f5f9; color: #0f172a; }
      hr { border: 0.5pt solid #e2e8f0; margin: 10pt 0; }
      li { margin-bottom: 3pt; }
    </style>
    """
    
    # Replace head style with pdf_style
    # Extract body content
    body_start = html_content.find("<body>")
    body_end = html_content.find("</body>")
    if body_start != -1 and body_end != -1:
        body_inner = html_content[body_start + 6:body_end]
    else:
        body_inner = html_content
        
    full_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{pdf_style}</head><body>{body_inner}</body></html>"
    
    base_dir = os.path.dirname(os.path.abspath(source_html_path))
    
    with open(output_pdf_path, "wb") as output_file:
        pisa_status = pisa.CreatePDF(
            full_html,
            dest=output_file,
            path=base_dir
        )
        
    if pisa_status.err:
        print(f"Error creating PDF: {output_pdf_path}")
        return False
    else:
        print(f"Successfully generated: {output_pdf_path}")
        return True

docs = ['USER_MANUAL', 'CLIENT_MANUAL', 'CLIENT_INSTALL']
for doc in docs:
    html_in = os.path.join("d:\\SSDV\\docs", f"{doc}.html")
    pdf_out = os.path.join("d:\\SSDV\\docs", f"{doc}.pdf")
    if os.path.exists(html_in):
        convert_html_to_pdf(html_in, pdf_out)
