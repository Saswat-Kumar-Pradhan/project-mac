import os
from xhtml2pdf import pisa
import markdown2

def convert_markdown_to_pdf(markdown_text: str, output_path: str, title: str = "MACADS Documentation"):
    """
    Converts a markdown string to a PDF file using xhtml2pdf.
    """
    try:
        html_content = markdown2.markdown(markdown_text, extras=["tables", "fenced-code-blocks", "code-friendly"])
        
        styled_html = f"""
        <html>
        <head>
            <style>
                @page {{
                    size: a4 portrait;
                    @frame content_frame {{
                        left: 50pt; width: 492pt; top: 50pt; height: 742pt;
                    }}
                }}
                body {{
                    font-family: Helvetica, Arial, sans-serif;
                    color: #333;
                    line-height: 1.6;
                }}
                h1 {{ color: #1a73e8; font-size: 24pt; border-bottom: 1pt solid #ccc; padding-bottom: 5pt; }}
                h2 {{ color: #202124; font-size: 18pt; margin-top: 20pt; }}
                h3 {{ color: #3c4043; font-size: 14pt; }}
                code {{
                    background-color: #f1f3f4;
                    padding: 2pt;
                    font-family: "Courier New", Courier, monospace;
                    font-size: 10pt;
                }}
                pre {{
                    background-color: #f1f3f4;
                    padding: 10pt;
                    border-radius: 4pt;
                    font-family: "Courier New", Courier, monospace;
                    font-size: 9pt;
                    display: block;
                }}
                table {{ width: 100%; border-collapse: collapse; margin: 10pt 0; }}
                th, td {{ border: 0.5pt solid #ddd; padding: 8pt; text-align: left; }}
                th {{ background-color: #f8f9fa; }}
            </style>
        </head>
        <body>
            <h1>{title}</h1>
            {html_content}
        </body>
        </html>
        """
        
        with open(output_path, "wb") as pdf_file:
            pisa_status = pisa.CreatePDF(styled_html, dest=pdf_file)
            
        return not pisa_status.err
    except Exception as e:
        print(f"PDF creation failed: {e}")
        return False
