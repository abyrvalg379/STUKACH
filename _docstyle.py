# -*- coding: utf-8 -*-
r"""_docstyle.py - семейственный шаблон документов «Вариант C» (2026-09-25, утверждён).

Язык обложек продукта: чёрный #000000 / белый #FFFFFF / красный #C82823,
Century Gothic капс с трекингом; внутри - белые страницы, заголовки разделов
с красной вертикальной чертой, таблицы без заливок с красной линией под шапкой.

Публичный API:
    doc  = new_doc(name, subtitle, version, gh='GITHUB.COM/ABYRVALG379')
    h1(doc, '1. О программе')      # номер станет красным, текст - чёрными капсами
    h2(doc, '1.1 Что делает')
    p(doc, 'текст', bullet=False, italic=False, grey=False)
    kv(doc, 'серо-курсивный хинт')
    add_table(doc, rows, widths_cm, sev_col=None)   # rows[0] = шапка
    footer(doc.sections[1], 'FLOMASTER')
    strip_tail(doc); doc.save(path)

Модуль копируется в каждый репозиторий рядом с генератором; стиль меняется
только здесь. Параметры утверждены пользователем 2026-09-25 (вариант C).
"""

from docx import Document
from docx.shared import Pt, RGBColor, Cm, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

RED_HEX   = 'C82823'
BLACK     = RGBColor(0x00, 0x00, 0x00)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
RED       = RGBColor(0xC8, 0x28, 0x23)
INK       = RGBColor(0x1A, 0x1A, 0x1A)
GREY      = RGBColor(0x6E, 0x6E, 0x6E)
DIM       = RGBColor(0x9E, 0x9E, 0x9E)
HEAD_FONT = 'Century Gothic'
BODY_FONT = 'Arial'

# семантические чипы критичности (STUKACH): фон + цвет текста
SEV_STYLE = {
    'BLOCKER': ('FDE9E9', (0xC0, 0x00, 0x00)),
    'ERROR':   ('FDE9E9', (0xC0, 0x00, 0x00)),
    'WARNING': ('FFF3CD', (0x7F, 0x60, 0x00)),
    'INFO':    ('EFEFEF', (0x55, 0x55, 0x55)),
}

H1_REGISTRY = []  # [(номер, текст)] - заполняется при вызове h1()


def _shade(pr, hex_color):
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    pr.append(shd)


def _borders_tc(tcPr, spec):
    tb = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        if side in spec:
            val, sz, color = spec[side]
            b = OxmlElement(f'w:{side}')
            b.set(qn('w:val'), val); b.set(qn('w:sz'), str(sz))
            b.set(qn('w:space'), '4'); b.set(qn('w:color'), color)
            tb.append(b)
    tcPr.append(tb)


def _run(par, text, font=BODY_FONT, size=9.5, color=INK, bold=False,
         caps=False, tracking=None):
    r = par.add_run(text.upper() if caps else text)
    r.font.name = font
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    rpr = r._r.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts')); rf.set(qn('w:cs'), font)
    if tracking:
        sp = OxmlElement('w:spacing'); sp.set(qn('w:val'), str(tracking))
        rpr.append(sp)
    return r


def new_doc(name, subtitle, version, gh='GITHUB.COM/ABYRVALG379'):
    """Обложка (чёрное полотно, белые капсы, красная линия) + секция контента."""
    doc = Document()
    for s in doc.sections:
        s.page_width = Twips(11906); s.page_height = Twips(16838)
    c = doc.sections[0]
    c.top_margin = c.bottom_margin = c.left_margin = c.right_margin = 0
    c.header_distance = c.footer_distance = 0
    c.footer.is_linked_to_previous = False

    tbl = doc.add_table(rows=1, cols=1)
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        b = OxmlElement(f'w:{side}'); b.set(qn('w:val'), 'none'); borders.append(b)
    tblPr.append(borders)
    tbl.columns[0].width = Twips(11906)
    trPr = tbl.rows[0]._tr.get_or_add_trPr()
    h = OxmlElement('w:trHeight')
    h.set(qn('w:val'), '16838'); h.set(qn('w:hRule'), 'exact')
    trPr.append(h)
    cell = tbl.rows[0].cells[0]
    cell.width = Twips(11906)
    _shade(cell._tc.get_or_add_tcPr(), '000000')
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    lead = cell.add_paragraph(); lead.paragraph_format.space_after = Pt(0)
    lead.add_run(' ').font.size = Pt(2)
    name_p = cell.add_paragraph()
    name_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_p.paragraph_format.space_after = Pt(16)
    _run(name_p, name, font=HEAD_FONT, size=48, color=WHITE, bold=True, tracking=60)
    line_p = cell.add_paragraph()
    line_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    line_p.paragraph_format.left_indent = Cm(5.2)
    line_p.paragraph_format.right_indent = Cm(5.2)
    line_p.paragraph_format.space_after = Pt(16)
    ppr = line_p._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'), 'single'); bottom.set(qn('w:sz'), '18')
    bottom.set(qn('w:space'), '1'); bottom.set(qn('w:color'), RED_HEX)
    pbdr.append(bottom); ppr.append(pbdr)
    _run(line_p, ' ')
    sub = cell.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(4)
    _run(sub, subtitle, font=HEAD_FONT, size=12, color=DIM, caps=True, tracking=80)
    ver = cell.add_paragraph()
    ver.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(ver, version, font=HEAD_FONT, size=9, color=DIM, caps=True, tracking=60)
    gap = cell.add_paragraph(); gap.paragraph_format.space_before = Pt(110)
    gap.add_run(' ')
    gh_p = cell.add_paragraph()
    gh_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(gh_p, gh, font=HEAD_FONT, size=7.5, color=DIM, caps=True, tracking=60)

    inner = doc.add_section(WD_SECTION.NEW_PAGE)
    inner.top_margin = inner.bottom_margin = Cm(2)
    inner.left_margin = inner.right_margin = Cm(2.2)
    normal = doc.styles['Normal']
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10)
    normal.font.color.rgb = INK
    normal.paragraph_format.line_spacing = 1.3
    normal.paragraph_format.space_after = Pt(4)
    st = doc.styles['Heading 2']
    st.font.name = HEAD_FONT
    st.font.size = Pt(11.5)
    st.font.bold = True
    st.font.color.rgb = BLACK
    st.paragraph_format.space_before = Pt(10)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True
    return doc


def h1(doc, text):
    """'1. О программе' -> красный номер + чёрные капсы с красной чертой слева."""
    num, _, title = text.partition('. ')
    if not title:
        num, title = '', text
    par = doc.add_paragraph()
    par.style = doc.styles['Heading 1']
    st = doc.styles['Heading 1']
    st.font.name = HEAD_FONT; st.font.size = Pt(15); st.font.bold = True
    st.font.color.rgb = BLACK
    st.paragraph_format.space_before = Pt(16)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True
    if num:
        r = par.add_run(num + '. ')
        r.font.name = HEAD_FONT; r.font.size = Pt(15); r.font.bold = True
        r.font.color.rgb = BLACK
    r2 = par.add_run(title.upper())
    r2.font.name = HEAD_FONT; r2.font.size = Pt(15); r2.font.bold = True
    r2.font.color.rgb = BLACK
    rpr = r2._r.get_or_add_rPr()
    sp = OxmlElement('w:spacing'); sp.set(qn('w:val'), '20'); rpr.append(sp)
    ppr = par._p.get_or_add_pPr()
    pbdr = OxmlElement('w:pBdr')
    left = OxmlElement('w:left')
    left.set(qn('w:val'), 'single'); left.set(qn('w:sz'), '24')
    left.set(qn('w:space'), '8'); left.set(qn('w:color'), RED_HEX)
    pbdr.append(left); ppr.append(pbdr)
    H1_REGISTRY.append(text)
    return par


def h2(doc, text):
    return doc.add_heading(text, level=2)


def p(doc, text, bullet=False, italic=False, grey=False):
    par = doc.add_paragraph(style='List Bullet' if bullet else None)
    r = par.add_run(text)
    r.font.name = BODY_FONT; r.font.size = Pt(9.5)
    r.font.italic = italic
    r.font.color.rgb = GREY if grey else INK
    return par


def kv(doc, text):
    par = doc.add_paragraph()
    r = par.add_run(text)
    r.font.name = BODY_FONT; r.font.size = Pt(9)
    r.font.italic = True; r.font.color.rgb = GREY
    return par


def mono(doc, text):
    """Строка с интерфейсным элементом (кнопка/надпись)."""
    par = doc.add_paragraph()
    r = par.add_run(text)
    r.font.name = 'Consolas'; r.font.size = Pt(9.5); r.font.bold = True
    par.paragraph_format.space_after = Pt(3)
    return par


def add_table(doc, rows, widths, sev_col=None):
    """Шапка: чёрные капсы + красная линия снизу; тело: волосяные линейки,
    последняя строка прибита чёрной чертой. sev_col - колонка чипов критичности."""
    table = doc.add_table(rows=0, cols=len(widths))
    table.autofit = False
    tblPr = table._tbl.tblPr
    mar = OxmlElement('w:tblCellMar')
    for side, val in (('top', 40), ('left', 80), ('bottom', 40), ('right', 80)):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'), str(val)); el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tblPr.append(mar)
    n = len(rows)
    for r_idx, row_data in enumerate(rows):
        row = table.add_row()
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement('w:cantSplit'))
        if n > 10 and r_idx == 0:
            trPr.append(OxmlElement('w:tblHeader'))
        # шапка всегда клеится к первой строке данных; короткие таблицы
        # (<=10 рядов) клеятся целиком - разрыв с сиротой-шапкой недопустим
        glue = (r_idx == 0) or (n <= 10 and r_idx < n - 1)
        for c_idx, (text, w) in enumerate(zip(row_data, widths)):
            cell = row.cells[c_idx]
            cell.width = Cm(w)
            tcPr = cell._tc.get_or_add_tcPr()
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            par = cell.paragraphs[0]
            par.paragraph_format.space_before = Pt(2)
            par.paragraph_format.space_after = Pt(2)
            par.paragraph_format.line_spacing = 1.1
            if r_idx == 0:
                _borders_tc(tcPr, {'bottom': ('single', 12, RED_HEX)})
                r = par.add_run(text.upper())
                r.font.name = HEAD_FONT; r.font.size = Pt(8.5)
                r.font.bold = True; r.font.color.rgb = BLACK
                rpr = r._r.get_or_add_rPr()
                sp = OxmlElement('w:spacing'); sp.set(qn('w:val'), '20'); rpr.append(sp)
            else:
                spec = {'bottom': ('single', 4, 'E0E0E0')}
                if r_idx == n - 1:
                    spec['bottom'] = ('single', 8, '000000')
                _borders_tc(tcPr, spec)
                key = text.strip()
                if sev_col is not None and c_idx == sev_col and key in SEV_STYLE:
                    bg, fg = SEV_STYLE[key]
                    _shade(tcPr, bg)
                    r = par.add_run(key)
                    r.font.name = BODY_FONT; r.font.size = Pt(9); r.font.bold = True
                    r.font.color.rgb = RGBColor(*fg)
                else:
                    r = par.add_run(text)
                    r.font.name = BODY_FONT; r.font.size = Pt(9)
                    r.font.bold = (c_idx == 0)
                    r.font.color.rgb = INK
            if glue:
                for pp in cell.paragraphs:
                    pp.paragraph_format.keep_with_next = True
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)
    sp.paragraph_format.line_spacing = 1.0
    return table


def toc_field(doc, hint):
    """Поле оглавления 1-го уровня; записи вставляет finish-скрипт."""
    par = doc.add_paragraph()
    run = par.add_run()
    fb = OxmlElement('w:fldChar'); fb.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText'); instr.set(qn('xml:space'), 'preserve')
    instr.text = r'TOC \o "1-1" \h \z \u'
    fs = OxmlElement('w:fldChar'); fs.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t'); t.text = hint
    fs.append(t)
    fe = OxmlElement('w:fldChar'); fe.set(qn('w:fldCharType'), 'end')
    r = run._r
    r.append(fb); r.append(instr); r.append(fs); r.append(fe)
    br = doc.add_paragraph()
    rb = br.add_run()
    pb = OxmlElement('w:br'); pb.set(qn('w:type'), 'page')
    rb._r.append(pb)


def footer(section, product):
    footer = section.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(fp, product, font=HEAD_FONT, size=7.5, color=GREY, caps=True, tracking=40)
    rd = fp.add_run('.')
    rd.font.name = HEAD_FONT; rd.font.size = Pt(7.5); rd.font.bold = True
    rd.font.color.rgb = RED
    pad = fp.add_run('      '); pad.font.size = Pt(7.5)
    run = fp.add_run()
    fb = OxmlElement('w:fldChar'); fb.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText'); instr.set(qn('xml:space'), 'preserve')
    instr.text = r'PAGE \* arabic \* MERGEFORMAT'
    fe = OxmlElement('w:fldChar'); fe.set(qn('w:fldCharType'), 'end')
    run._r.append(fb); run._r.append(instr); run._r.append(fe)
    run.font.name = HEAD_FONT; run.font.size = Pt(7.5); run.font.color.rgb = GREY


def strip_tail(doc):
    body = doc.element.body
    for el in list(body)[::-1]:
        if el.tag == qn('w:sectPr'):
            continue
        if el.tag == qn('w:p') and not ''.join(el.itertext()).strip():
            body.remove(el)
        else:
            break
