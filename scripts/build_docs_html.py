import os
import re

def markdown_to_html(md_text):
    # Basic markdown parsing without external deps if needed
    lines = md_text.split('\n')
    html_lines = []
    in_code_block = False
    in_table = False
    
    for line in lines:
        if line.startswith('```'):
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            else:
                html_lines.append('<pre><code>')
                in_code_block = True
            continue
        
        if in_code_block:
            html_lines.append(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
            continue
            
        # Headers
        if line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
            continue
        if line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
            continue
        if line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
            continue
        if line.startswith('#### '):
            html_lines.append(f'<h4>{line[5:]}</h4>')
            continue
        if line.strip() == '---':
            html_lines.append('<hr>')
            continue
            
        # Images: ![alt](src)
        img_match = re.match(r'!\[(.*?)\]\((.*?)\)', line.strip())
        if img_match:
            alt, src = img_match.groups()
            html_lines.append(f'<p><img src="{src}" alt="{alt}"></p>')
            continue
            
        # Table rows
        if line.strip().startswith('|') and line.strip().endswith('|'):
            cells = [c.strip() for c in line.strip()[1:-1].split('|')]
            if all(set(c).issubset({'-', ':', ' '}) for c in cells):
                continue # delimiter row
            if not in_table:
                html_lines.append('<table>')
                in_table = True
                html_lines.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
            else:
                html_lines.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            continue
        else:
            if in_table:
                html_lines.append('</table>')
                in_table = False
                
        # Bullet list
        if line.strip().startswith('- '):
            html_lines.append(f'<li>{line.strip()[2:]}</li>')
            continue
            
        # Plain text
        if line.strip():
            # replace bold and links
            formatted = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            formatted = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', formatted)
            formatted = re.sub(r'`(.*?)`', r'<code>\1</code>', formatted)
            html_lines.append(f'<p>{formatted}</p>')
            
    if in_table:
        html_lines.append('</table>')
    if in_code_block:
        html_lines.append('</code></pre>')
        
    return '\n'.join(html_lines)

docs = ['USER_MANUAL', 'CLIENT_MANUAL', 'CLIENT_INSTALL']
for doc in docs:
    md_file = os.path.join('d:\\SSDV\\docs', f'{doc}.md')
    html_file = os.path.join('d:\\SSDV\\docs', f'{doc}.html')
    if os.path.exists(md_file):
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
        body = markdown_to_html(md_content)
        page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc} - OfficeMitra SSDV</title>
<style>
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  color: #1e293b;
  max-width: 960px;
  margin: 2rem auto;
  padding: 0 1.5rem;
  background: #f8fafc;
}}
.container {{
  background: #ffffff;
  padding: 2.5rem;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06);
}}
h1 {{ color: #0f172a; font-size: 2rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }}
h2 {{ color: #0f172a; font-size: 1.5rem; margin-top: 2rem; border-bottom: 1px solid #f1f5f9; padding-bottom: 0.3rem; }}
h3 {{ color: #1e293b; font-size: 1.25rem; margin-top: 1.5rem; }}
img {{
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1.5rem auto;
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.1);
  border: 1px solid #e2e8f0;
}}
table {{ width: 100%; border-collapse: collapse; margin: 1.5rem 0; font-size: 0.95rem; }}
th, td {{ border: 1px solid #e2e8f0; padding: 0.65rem 0.9rem; text-align: left; }}
th {{ background: #f1f5f9; font-weight: 600; color: #0f172a; }}
tr:nth-child(even) {{ background: #f8fafc; }}
code {{ background: #f1f5f9; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: Consolas, monospace; font-size: 0.9em; color: #0f172a; }}
pre {{ background: #0f172a; color: #f8fafc; padding: 1.2rem; border-radius: 8px; overflow-x: auto; }}
pre code {{ background: transparent; color: inherit; padding: 0; }}
hr {{ border: 0; height: 1px; background: #e2e8f0; margin: 2rem 0; }}
a {{ color: #0284c7; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
li {{ margin-bottom: 0.3rem; }}
</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>'''
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(page)
        print(f"Generated: {html_file}")
