#!/usr/bin/env python3
"""Generate a docx file from the operation manual content without python-docx dependency.
Uses only stdlib to create a minimal but valid docx (which is a zip of XML files)."""

import zipfile
import os
import re

# Read the markdown content
with open("/root/projects/PPTAgent/docs/操作手册.md", "r", encoding="utf-8") as f:
    md_content = f.read()

# Parse markdown into structured sections
sections = []
current_section = {"level": 0, "title": "", "content": []}
for line in md_content.split("\n"):
    if line.startswith("# "):
        if current_section["title"] or current_section["content"]:
            sections.append(current_section)
        current_section = {"level": 1, "title": line[2:].strip(), "content": []}
    elif line.startswith("## "):
        if current_section["title"] or current_section["content"]:
            sections.append(current_section)
        current_section = {"level": 2, "title": line[3:].strip(), "content": []}
    elif line.startswith("### "):
        if current_section["title"] or current_section["content"]:
            sections.append(current_section)
        current_section = {"level": 3, "title": line[4:].strip(), "content": []}
    else:
        current_section["content"].append(line)
if current_section["title"] or current_section["content"]:
    sections.append(current_section)

def escape_xml(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def md_to_xml_lines(text):
    """Convert simple markdown inline formatting to OpenXML runs."""
    parts = re.split(r'(\*\*.*?\*\*)', text)
    runs = []
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            inner = part[2:-2]
            runs.append(f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{escape_xml(inner)}</w:t></w:r>')
        else:
            if part:
                runs.append(f'<w:r><w:t xml:space="preserve">{escape_xml(part)}</w:t></w:r>')
    return "".join(runs)

def format_table_row(cells, is_header=False):
    """Create a table row in OpenXML format."""
    row_cells = []
    for cell in cells:
        cell_content = md_to_xml_lines(cell.strip())
        if is_header:
            cell_xml = f'''<w:tc>
                <w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="4472C4"/><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>
                <w:p><w:pPr><w:jc w:val="center"/></w:pPr>
                <w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">{escape_xml(cell.strip())}</w:t></w:r>
                </w:p></w:tc>'''
        else:
            cell_xml = f'''<w:tc>
                <w:tcPr><w:tcW w:w="2500" w:type="dxa"/></w:tcPr>
                <w:p><w:r><w:t xml:space="preserve">{escape_xml(cell.strip())}</w:t></w:r></w:p></w:tc>'''
        row_cells.append(cell_xml)
    return f'<w:tr>{"".join(row_cells)}</w:tr>'

# Build document body content
body_parts = []

# Title page
body_parts.append('''<w:p>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="2400" w:after="400"/></w:pPr>
    <w:r><w:rPr><w:sz w:val="56"/><w:b/><w:color w:val="2C3E50"/></w:rPr><w:t xml:space="preserve">PPT生成平台</w:t></w:r>
</w:p>
<w:p>
    <w:pPr><w:jc w:val="center"/><w:spacing w:after="800"/></w:pPr>
    <w:r><w:rPr><w:sz w:val="36"/><w:color w:val="409EFF"/></w:rPr><w:t xml:space="preserve">用户操作手册</w:t></w:r>
</w:p>
<w:p>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="1200"/></w:pPr>
    <w:r><w:rPr><w:sz w:val="22"/><w:color w:val="666666"/></w:rPr><w:t xml:space="preserve">DeepPresenter</w:t></w:r>
</w:p>''')

# Page break
body_parts.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

for section in sections:
    level = section["level"]
    title = section["title"]
    content = section["content"]
    
    if not title and not any(l.strip() for l in content):
        continue
    
    # Add heading
    if level == 1 and title:
        body_parts.append(f'''<w:p>
            <w:pPr><w:spacing w:before="360" w:after="200"/></w:pPr>
            <w:r><w:rPr><w:sz w:val="40"/><w:b/><w:color w:val="2C3E50"/></w:rPr><w:t xml:space="preserve">{escape_xml(title)}</w:t></w:r>
        </w:p>''')
    elif level == 2 and title:
        body_parts.append(f'''<w:p>
            <w:pPr><w:spacing w:before="300" w:after="160"/></w:pPr>
            <w:r><w:rPr><w:sz w:val="32"/><w:b/><w:color w:val="34495E"/></w:rPr><w:t xml:space="preserve">{escape_xml(title)}</w:t></w:r>
        </w:p>''')
    elif level == 3 and title:
        body_parts.append(f'''<w:p>
            <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
            <w:r><w:rPr><w:sz w:val="28"/><w:b/><w:color w:val="409EFF"/></w:rPr><w:t xml:space="preserve">{escape_xml(title)}</w:t></w:r>
        </w:p>''')
    
    # Process content lines
    in_code_block = False
    in_table = False
    table_rows = []
    blockquote_lines = []
    
    i = 0
    while i < len(content):
        line = content[i]
        stripped = line.strip()
        
        # Code block
        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
            else:
                in_code_block = True
                # Flush any pending blockquote
                if blockquote_lines:
                    for bq_line in blockquote_lines:
                        body_parts.append(f'''<w:p>
                            <w:pPr><w:ind w:left="360"/><w:spacing w:after="40"/></w:pPr>
                            <w:r><w:rPr><w:color w:val="666666"/><w:i/><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">{escape_xml(bq_line.strip())}</w:t></w:r>
                        </w:p>''')
                    blockquote_lines = []
            i += 1
            continue
        
        if in_code_block:
            body_parts.append(f'''<w:p>
                <w:pPr><w:ind w:left="360"/><w:spacing w:after="20"/></w:pPr>
                <w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">{escape_xml(line)}</w:t></w:r>
            </w:p>''')
            i += 1
            continue
        
        # Table
        if "|" in stripped and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            # Skip separator rows
            if cells and all(set(c) <= set("-: ") for c in cells):
                i += 1
                continue
            table_rows.append(cells)
            # Check if next line is also a table row
            if i + 1 < len(content) and content[i+1].strip().startswith("|"):
                i += 1
                continue
            else:
                # End of table, render it
                if table_rows:
                    num_cols = max(len(r) for r in table_rows)
                    tbl_rows = []
                    for ri, row in enumerate(table_rows):
                        while len(row) < num_cols:
                            row.append("")
                        tbl_rows.append(format_table_row(row, is_header=(ri == 0)))
                    
                    table_xml = f'''<w:tbl>
                        <w:tblPr>
                            <w:tblW w:w="9000" w:type="dxa"/>
                            <w:tblBorders>
                                <w:top w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                                <w:left w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                                <w:bottom w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                                <w:right w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                                <w:insideH w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                                <w:insideV w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/>
                            </w:tblBorders>
                        </w:tblPr>
                        {"".join(tbl_rows)}
                    </w:tbl>'''
                    body_parts.append(table_xml)
                    body_parts.append('<w:p><w:spacing w:after="120"/></w:p>')
                table_rows = []
                i += 1
                continue
        
        # Blockquote
        if stripped.startswith(">"):
            blockquote_lines.append(stripped.lstrip("> "))
            i += 1
            continue
        elif blockquote_lines:
            for bq_line in blockquote_lines:
                body_parts.append(f'''<w:p>
                    <w:pPr><w:ind w:left="360"/><w:spacing w:after="40"/></w:pPr>
                    <w:r><w:rPr><w:color w:val="666666"/><w:i/><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">{escape_xml(bq_line.strip())}</w:t></w:r>
                </w:p>''')
            blockquote_lines = []
        
        # Empty line
        if not stripped:
            body_parts.append('<w:p><w:spacing w:after="60"/></w:p>')
            i += 1
            continue
        
        # Ordered list
        ol_match = re.match(r'^(\d+)\.\s+(.+)', stripped)
        if ol_match:
            num = ol_match.group(1)
            text = ol_match.group(2)
            body_parts.append(f'''<w:p>
                <w:pPr><w:ind w:left="360" w:hanging="360"/><w:spacing w:after="40"/></w:pPr>
                <w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{num}. </w:t></w:r>
                <w:r><w:t xml:space="preserve">{escape_xml(text)}</w:t></w:r>
            </w:p>''')
            i += 1
            continue
        
        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            body_parts.append(f'''<w:p>
                <w:pPr><w:ind w:left="360" w:hanging="360"/><w:spacing w:after="40"/></w:pPr>
                <w:r><w:t xml:space="preserve">  {escape_xml(text)}</w:t></w:r>
            </w:p>''')
            i += 1
            continue
        
        # Regular paragraph with inline formatting
        body_parts.append(f'''<w:p>
            <w:pPr><w:spacing w:after="80"/></w:pPr>
            {md_to_xml_lines(stripped)}
        </w:p>''')
        i += 1
    
    # Flush remaining blockquote
    if blockquote_lines:
        for bq_line in blockquote_lines:
            body_parts.append(f'''<w:p>
                <w:pPr><w:ind w:left="360"/><w:spacing w:after="40"/></w:pPr>
                <w:r><w:rPr><w:color w:val="666666"/><w:i/><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">{escape_xml(bq_line.strip())}</w:t></w:r>
            </w:p>''')

# Construct the full docx (ZIP archive)
content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
    <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''

rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''

word_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:docDefaults>
        <w:rPrDefault>
            <w:rPr>
                <w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/>
                <w:sz w:val="22"/>
            </w:rPr>
        </w:rPrDefault>
        <w:pPrDefault>
            <w:pPr>
                <w:spacing w:after="160" w:line="360" w:lineRule="auto"/>
            </w:pPr>
        </w:pPrDefault>
    </w:docDefaults>
</w:styles>'''

document = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
    <w:body>
        {"".join(body_parts)}
        <w:sectPr>
            <w:pgSz w:w="11906" w:h="16838"/>
            <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
        </w:sectPr>
    </w:body>
</w:document>'''

output_path = "/root/projects/PPTAgent/docs/操作手册.docx"

with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    zf.writestr('[Content_Types].xml', content_types)
    zf.writestr('_rels/.rels', rels)
    zf.writestr('word/_rels/document.xml.rels', word_rels)
    zf.writestr('word/document.xml', document)
    zf.writestr('word/styles.xml', styles)

print(f"Docx file created: {output_path}")
print(f"File size: {os.path.getsize(output_path)} bytes")
