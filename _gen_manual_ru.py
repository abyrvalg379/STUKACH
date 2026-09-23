# -*- coding: utf-8 -*-
r"""STUKACH - Руководство пользователя (RU). Генератор DOCX.

Стиль наследует _gen_docx.py (Arial, синие заголовки, фирменные таблицы).
Запуск:  python _gen_manual_ru.py
Выход:   D:\AI\ZCode\Project\STUKACH\out\blender\STUKACH_Manual_RU.docx
"""

from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT = r'D:\AI\ZCode\Project\STUKACH\out\blender\STUKACH_Manual_RU.docx'

doc = Document()

for section in doc.sections:
    section.top_margin    = Inches(0.9)
    section.bottom_margin = Inches(0.9)
    section.left_margin   = Inches(1)
    section.right_margin  = Inches(1)

# ── базовые стили ──────────────────────────────────────────────────────────

normal = doc.styles['Normal']
normal.font.name = 'Arial'
normal.font.size = Pt(10)
normal.paragraph_format.line_spacing = 1.3
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.space_before = Pt(0)
# кириллица в Arial - нужен явный w:cs-шрифт
rpr = normal.element.get_or_add_rPr()
rfonts = rpr.find(qn('w:rFonts'))
rfonts.set(qn('w:cs'), 'Arial')

for lvl, size in (('Heading 1', 15), ('Heading 2', 12.5), ('Heading 3', 11)):
    st = doc.styles[lvl]
    st.font.name = 'Arial'
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D) if lvl == 'Heading 1' else RGBColor(0x2E, 0x74, 0xB5)
    st.paragraph_format.space_before = Pt(14 if lvl == 'Heading 1' else 10)
    st.paragraph_format.space_after = Pt(5)
    st.paragraph_format.line_spacing = 1.15
    st.paragraph_format.keep_with_next = True

# ── хелперы ────────────────────────────────────────────────────────────────

SEV_STYLE = {
    'BLOCKER': ('FDE9E9', (0xC0, 0x00, 0x00)),
    'ERROR':   ('FDE9E9', (0xC0, 0x00, 0x00)),
    'WARNING': ('FFF3CD', (0x7F, 0x60, 0x00)),
    'INFO':    ('E8F4FD', (0x1F, 0x49, 0x7D)),
}
HDR_BG  = '2E75B5'
ALT_ROW = 'F5F8FB'
BLUE_H1 = RGBColor(0x1F, 0x49, 0x7D)
GREY    = RGBColor(0x55, 0x55, 0x55)


def set_cell_bg(cell, hex_color):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def set_cell_borders(cell, color='CCCCCC'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcB = OxmlElement('w:tcBorders')
    for side in ('top', 'left', 'bottom', 'right'):
        b = OxmlElement(f'w:{side}')
        b.set(qn('w:val'), 'single')
        b.set(qn('w:sz'), '4')
        b.set(qn('w:space'), '0')
        b.set(qn('w:color'), color)
        tcB.append(b)
    tcPr.append(tcB)


def cell_para(cell, text, bold=False, size=9, color=None, italic=False):
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.1
    run = p.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*color)


def table_margins(table, top=40, bottom=40, left=80, right=80):
    tblPr = table._tbl.tblPr
    mar = OxmlElement('w:tblCellMar')
    for side, val in (('top', top), ('left', left), ('bottom', bottom), ('right', right)):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:w'), str(val))
        el.set(qn('w:type'), 'dxa')
        mar.append(el)
    tblPr.append(mar)


def add_table(doc, rows, col_widths_cm, sev_col=None):
    """rows[0] = заголовок. sev_col - индекс колонки с severity-чипом (окраска)."""
    n_cols = len(col_widths_cm)
    table = doc.add_table(rows=0, cols=n_cols)
    table.style = 'Table Grid'
    table.autofit = False
    table_margins(table)

    for r_idx, row_data in enumerate(rows):
        row = table.add_row()
        # Разрыв строки посреди ячейки запрещён всегда (cantSplit). tblHeader
        # (повтор шапки) - только большим таблицам: пара cantSplit+tblHeader
        # у маленьких таблиц роняет строку при конвертации в PDF (LibreOffice).
        # Маленькие таблицы (<=2 рядов) дополнительно клеятся в один блок
        # через keepNext - шапка-сирота недопустима.
        big = len(rows) > 2
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement('w:cantSplit')
        trPr.append(cant)
        if big and r_idx == 0:
            th = OxmlElement('w:tblHeader')
            trPr.append(th)

        glue = not big and r_idx < len(rows) - 1
        for c_idx, (text, w) in enumerate(zip(row_data, col_widths_cm)):
            cell = row.cells[c_idx]
            cell.width = Cm(w)
            set_cell_borders(cell)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

            if r_idx == 0:
                set_cell_bg(cell, HDR_BG)
                cell_para(cell, text, bold=True, size=9, color=(0xFF, 0xFF, 0xFF))
            else:
                if r_idx % 2 == 0:
                    set_cell_bg(cell, ALT_ROW)
                if sev_col is not None and c_idx == sev_col:
                    key = text.strip()
                    bg, fg = SEV_STYLE.get(key, ('FFFFFF', (0, 0, 0)))
                    set_cell_bg(cell, bg)
                    cell_para(cell, key, bold=True, size=9, color=fg)
                elif c_idx == 0:
                    cell_para(cell, text, bold=True, size=9)
                else:
                    cell_para(cell, text, size=9)

            if glue:
                for par in cell.paragraphs:
                    par.paragraph_format.keep_with_next = True

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)
    sp.paragraph_format.space_before = Pt(0)
    sp.paragraph_format.line_spacing = 1.0
    return table


def h1(doc, text):
    doc.add_heading(text, level=1)


def h2(doc, text):
    doc.add_heading(text, level=2)


def p(doc, text, italic=False, grey=False, bullet=False):
    par = doc.add_paragraph(style='List Bullet' if bullet else None)
    run = par.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(9.5)
    run.font.italic = italic
    if grey:
        run.font.color.rgb = GREY
    return par


def kv_note(doc, text):
    """Серый курсив-хинт."""
    par = doc.add_paragraph()
    run = par.add_run(text)
    run.font.name = 'Arial'
    run.font.size = Pt(9)
    run.font.italic = True
    run.font.color.rgb = GREY


def mono(doc, text):
    """Строка с интерфейсным элементом (кнопка/надпись)."""
    par = doc.add_paragraph()
    run = par.add_run(text)
    run.font.name = 'Consolas'
    run.font.size = Pt(9.5)
    run.font.bold = True
    par.paragraph_format.space_after = Pt(3)
    return par


def add_toc_field(doc):
    """Поле оглавления + хинт обновления (правило скилла)."""
    par = doc.add_paragraph()
    run = par.add_run()
    fld_begin = OxmlElement('w:fldChar')
    fld_begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = r'TOC \o "1-2" \h \z \u'
    fld_sep = OxmlElement('w:fldChar')
    fld_sep.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t')
    t.text = 'Оглавление: откройте документ в Word/LibreOffice и обновите поле (F9), чтобы заполнить номера страниц.'
    fld_sep.append(t)
    fld_end = OxmlElement('w:fldChar')
    fld_end.set(qn('w:fldCharType'), 'end')
    r = run._r
    r.append(fld_begin)
    r.append(instr)
    r.append(fld_sep)
    r.append(fld_end)

    br = doc.add_paragraph()
    run_br = br.add_run()
    pb = OxmlElement('w:br')
    pb.set(qn('w:type'), 'page')
    run_br._r.append(pb)


def add_footer_pagenum(doc):
    footer = doc.sections[0].footer
    par = footer.paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = par.add_run()
    fld_begin = OxmlElement('w:fldChar')
    fld_begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = r'PAGE \* arabic \* MERGEFORMAT'
    fld_end = OxmlElement('w:fldChar')
    fld_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    run.font.name = 'Arial'
    run.font.size = Pt(9)
    run.font.color.rgb = GREY


# ════════════════════════════════════════════════════════════════════════════
# ТИТУЛ
# ════════════════════════════════════════════════════════════════════════════

title_p = doc.add_paragraph()
title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
title_p.paragraph_format.space_before = Pt(30)
title_p.paragraph_format.space_after = Pt(4)
r = title_p.add_run('STUKACH')
r.font.name = 'Arial'; r.font.size = Pt(30); r.font.bold = True
r.font.color.rgb = BLUE_H1

title2 = doc.add_paragraph()
title2.alignment = WD_ALIGN_PARAGRAPH.CENTER
title2.paragraph_format.space_after = Pt(10)
r = title2.add_run('Руководство пользователя')
r.font.name = 'Arial'; r.font.size = Pt(18); r.font.bold = True
r.font.color.rgb = BLUE_H1

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub.paragraph_format.space_after = Pt(4)
r = sub.add_run('Пайплайн-валидатор ассетов для кино- и game-производства')
r.font.name = 'Arial'; r.font.size = Pt(11); r.font.color.rgb = GREY

sub2 = doc.add_paragraph()
sub2.alignment = WD_ALIGN_PARAGRAPH.CENTER
sub2.paragraph_format.space_after = Pt(20)
r = sub2.add_run('Версия для Blender 5.2 - v1.7.5  ·  Версия для Maya 2025 - v1.3.0')
r.font.name = 'Arial'; r.font.size = Pt(10.5); r.font.color.rgb = GREY

p(doc, 'STUKACH проверяет сцену на типовые ошибки пайплайна: топологию, трансформы, '
       'UV, нейминг, материалы и структуру иерархии. Артист видит брак прямо во вьюпорте '
       'и чинит его до сдачи, координатор получает формальный вердикт одним нажатием. '
       'Документ описывает работу с обеими версиями: основная часть - про Blender-версию, '
       'раздел 11 - про Maya.', grey=False)

kv_note(doc, 'Автор: Maksim Kovalev. Лицензия GPL-3.0. '
             'Blender: github.com/abyrvalg379/STUKACH  ·  Maya: github.com/abyrvalg379/STUKACH_Maya')

# ════════════════════════════════════════════════════════════════════════════
# ОГЛАВЛЕНИЕ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, 'Содержание')
add_toc_field(doc)

# ════════════════════════════════════════════════════════════════════════════
# 1. О ПРОГРАММЕ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '1. О программе')

h2(doc, '1.1 Что делает STUKACH')
p(doc, 'STUKACH - это чекер качества ассетов, встроенный в панель DCC-пакета. Он заменяет '
       '«ручной осмотр» ассета перед сдачей формализованной валидацией: один прогон проверяет '
       'объекты сцены по десяткам правил, подсвечивает брак прямо на геометрии во вьюпорте, '
       'умеет чинить типовые проблемы одной кнопкой и выдаёт отчёт, понятный и артисту, и супервайзеру.')
p(doc, 'Ключевые возможности:', bullet=False)
for b in [
    '42 чека в 7 категориях + проверка единиц сцены (Blender); 43 чека + два сцен-чека (Maya);',
    'валидатор иерархии ассета - 13 правил структуры (корни, слои, группы, нейминг веток);',
    'GPU-оверлеи: брак рисуется цветом прямо на геометрии - граней, рёбер, вершин;',
    'Live-режим: валидация сама пересчитывается при правках, без повторного RUN;',
    'исправления одной кнопкой (Fix): трансформы, иерархия, нейминг меш-данных, чистка мусора;',
    'режим координатора (Coordinator Mode): только блокеры и предупреждения, формальный вердикт;',
    'отчёты: копия в буфер, JSON/CSV/HTML, pre-flight перед экспортом FBX/USD;',
    'пресеты наборов проверок с шарингом файлом между членами команды.',
]:
    p(doc, b, bullet=True)

h2(doc, '1.2 Философия: три уровня критичности')
p(doc, 'Каждая находка STUKACH имеет уровень критичности. Это не «важность для галочки» - '
       'уровень напрямую определяет влияние на статус ассета и то, кто принимает решение.')
add_table(doc, [
    ['Уровень', 'Значение', 'Влияние на статус'],
    ['BLOCKER', 'Ассет нельзя сдавать. Проблема гарантированно сломает рендер, экспорт, симуляцию или '
                'даунстрим-пайплайн. Требует исправления до передачи.',
                'Тянет статус ассета в CRITICAL'],
    ['WARNING', 'Проблема реальная, но не всегда катастрофическая. Артист должен осознанно решить - '
                'исправить или обосновать исключение.',
                'Тянет статус в REVIEW'],
    ['INFO', 'Информация для ревью. Не ошибка - подсвечивает места, требующие осознанного решения '
             '(треугольники, полюса, открытые рёбра).',
             'На статус не влияет'],
], [3, 11.5, 4.5], sev_col=None)

h2(doc, '1.3 Два режима: Artist и Coordinator')
p(doc, 'Панель работает в одном из двух режимов. Artist Mode - рабочий режим артиста: полный набор '
       'чеков, оверлеи во вьюпорте и кнопки Fix. Coordinator Mode - режим приёмки: показываются только '
       'BLOCKER и WARNING, выводится сводный вердикт ассета и кнопка Copy Report. Галка Coordinator '
       'Lock (Preferences) дополнительно прячет в Coordinator Mode все кнопки Fix - координатор '
       'только валидирует. Как работать в каждом режиме - раздел 10.')

h2(doc, '1.4 Две версии')
add_table(doc, [
    ['', 'Blender-версия', 'Maya-версия'],
    ['Версия', 'v1.7.5', 'v1.3.0'],
    ['Пакет', 'Blender 5.1+ extension (zip)', 'Maya 2025 Win x64 (python + C++ плагин оверлея)'],
    ['Панель', 'N-панель View3D → вкладка STUKACH', 'Док-панель слева от Attribute Editor'],
    ['Чеки', '42 + Scene Units', '43 + Scene Units + Empty Groups'],
    ['Иерархия', 'Валидатор 13 правил + фиксы', 'Рождается локаторами; проверяется в Blender'],
    ['Репозиторий', 'github.com/abyrvalg379/STUKACH', 'github.com/abyrvalg379/STUKACH_Maya'],
], [3.2, 7.9, 7.9])
kv_note(doc, 'Нумерация версий Blender и Maya независима. Maya-версия закрывает валидацию на этапе '
             'моделинга, Blender-версия - на приёмке готового ассета.')

# ════════════════════════════════════════════════════════════════════════════
# 2. УСТАНОВКА
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '2. Установка')

h2(doc, '2.1 Blender 5.1+')
for b in [
    'Скачайте zip последнего релиза: github.com/abyrvalg379/STUKACH → Releases → ассет STUKACH.zip.',
    'Blender → Edit → Preferences → Get Extensions → стрелка-меню в правом верхнем углу → Install from Disk → выберите zip.',
    'Убедитесь, что расширение STUKACH включено (галочка).',
    'Панель появится в N-панели 3D-вьюпорта (клавиша N) → вкладка STUKACH.',
    'Обновление: скачайте новый zip и установите его тем же способом - поверх старой версии. Настройки и пресеты сохраняются.',
]:
    p(doc, b, bullet=True)
kv_note(doc, 'После первого запуска рекомендуется открыть Preferences → Add-ons → STUKACH и нажать '
             'Save Preferences, чтобы состояние расширения зафиксировалось.')

h2(doc, '2.2 Maya 2025 (Windows x64)')
for b in [
    'Скачайте kit последнего релиза: github.com/abyrvalg379/STUKACH_Maya → Releases → STUKACH_Maya_vX.Y.Z.zip.',
    'Распакуйте. Перетащите файл install_stukach.py мышью прямо во вьюпорт открытой Maya - это штатный drag-and-drop инсталлятор.',
    'Инсталлятор скопирует пакет в Documents/maya/2025/scripts, плагин оверлея - в Documents/maya/2025/plug-ins и создаст кнопку STUKACH на полке (вкладка Custom).',
    'Перезапустите Maya (или загрузите плагин вручную: Windows → Settings/Preferences → Plug-in Manager → stukachDrawOverride.mll).',
    'Панель открывается кнопкой STUKACH на полке. По умолчанию панель докается слева от Attribute Editor.',
]:
    p(doc, b, bullet=True)
kv_note(doc, 'Зависимости: numpy и scipy (ставятся в user site-packages Maya). Бинарный оверлей '
             '(stukachDrawOverride.mll) собран под Maya 2025 Windows x64 - на других ОС/версиях панель '
             'работает, оверлей переключается на запасной режим display layers.')

# ════════════════════════════════════════════════════════════════════════════
# 3. БЫСТРЫЙ СТАРТ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '3. Быстрый старт (Blender)')
p(doc, 'Пять шагов, чтобы получить первый отчёт по ассету:')
for i, b in enumerate([
    'Откройте N-панель (N) → вкладка STUKACH → нажмите RUN STUKACH. По умолчанию валидируется '
    'выделение (Selected scope); для всей сцены нажмите Scene.',
    'Дождитесь прогресса (тяжёлые сцены считаются пачками, панель показывает «Validating N/M»). '
    'Список Objects показывает только объекты с проблемами, худшие - сверху.',
    'Кликните по объекту в списке - раскроются его находки по чекам. Кнопка Sel выделяет бракованную '
    'геометрию и приближает камеру; Show - только подсвечивает во вьюпорте.',
    'Чините: у части чеков есть кнопка Fix (неприменённые трансформы, нейминг меш-данных, чистка '
    'мусора, фиксы иерархии). Остальное правится руками - оверлей показывает, где именно брак.',
    'Сдайте: кнопка Copy Summary кладёт в буфер отчёт; в Coordinator Mode - Copy Report с формальным '
    'вердиктом READY / REVIEW / BLOCKED.',
], 1):
    par = p(doc, b, bullet=True)

kv_note(doc, 'Дальше можно включить Live - валидация будет пересчитываться сама при правках геометрии, '
             'UV и трансформов.')

# ════════════════════════════════════════════════════════════════════════════
# 4. ИНТЕРФЕЙС BLENDER
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '4. Интерфейс Blender-версии')
p(doc, 'Панель N-панели идёт сверху вниз: запуск и режимы → счёт и навигация → область проверки → '
       'чеки → иерархия → объекты → статус и экспорт. Ниже - каждый блок.')

h2(doc, '4.1 Запуск и режимы')
add_table(doc, [
    ['Элемент', 'Что делает'],
    ['RUN STUKACH / STUKACH ACTIVE', 'Запуск и остановка валидации. Первый RUN валидирует выделение '
     '(Selected); расширить область - кнопки Scene / Collection ниже.'],
    ['Coordinator Mode ⇄ Artist Mode', 'Переключение режима координатора/артиста. В Coordinator Mode '
     'скрыты INFO-чеки, показывается вердикт и Copy Report. При включённом Coordinator Lock (см. §9) '
     'все кнопки Fix спрятаны.'],
    ['Live', 'Автопересчёт чеков при правках: топология, UV, трансформы, переименования. Новые '
     'объекты сцены подхватываются автоматически; иерархия пересканируется при изменениях.'],
], [5.2, 13.8])

h2(doc, '4.2 Счёт и навигация')
add_table(doc, [
    ['Элемент', 'Что делает'],
    ['Score-блок', 'Счёт валидации и health-strip - цветные точки по категориям (зелёная/жёлтая/красная '
     '- по порогам количества).'],
    ['Next Issue', 'Циклическая навигация по браку: выделяет следующий проблемный объект, приближает '
     'камеру, включает худший его чек. Работает и по объектам, найденным только иерархией.'],
    ['Copy Summary', 'Отчёт в буфер обмена. В Artist Mode - компактная сводка; подписывается именем '
     'валидатора (см. §9) и датой.'],
    ['Подсказки под счётом', '«Validating N/M» - прогресс очереди; «Scene changed - re-run» - сцена '
     'менялась после прогона; «Settings restored - press Run» - настройки восстановлены из сцены, '
     'нужен новый прогон.'],
], [5.2, 13.8])

h2(doc, '4.3 Область проверки')
add_table(doc, [
    ['Кнопка', 'Область'],
    ['Scene', 'Все меш-объекты сцены'],
    ['Collection', 'Все меш-объекты активной коллекции (включая вложенные)'],
    ['Clear', 'Сброс результатов валидации'],
    ['(RUN)', 'Первый запуск всегда берёт Selected - выделение. Это защита от случайного прогона по '
     'всей сцене.'],
], [3.5, 15.5])

h2(doc, '4.4 Блок Pipeline Checks')
p(doc, 'Здесь включаются чеки и настраивается вид оверлея. Категории сворачиваются; у каждой категории '
       '- общая галка включения. Рядом с именем чека - цветной свотч (цвет оверлея) и счётчик находок '
       'после прогона.')
add_table(doc, [
    ['Элемент', 'Что делает'],
    ['Face Orientation | Scene Units', 'Face Orientation - дублирует встроенный оверлей нормалей '
     'Blender (заменяет старые счётчики flipped/invalid normals, которые убраны из чекеров). '
     'Scene Units - отдельный сцен-чек единиц измерения.'],
    ['X-Ray', 'Режим прозрачности оверлея. Включён (по умолчанию) - метки рисуются сквозь стенки, '
     'всё видно «рентгеном». Выключен - непрозрачные стенки меша скрывают метки на дальней стороне. '
     'Штатный xray вьюпорта (Alt+Z) всегда включает просвет.'],
    ['Face Offset / Point Offset', 'Отступ заливки граней и маркеров точек от поверхности (борьба с '
     'z-fighting оверлея).'],
    ['Presets', 'Нативный дропдаун именованных наборов чеков + правила нейминга. Значки: + сохранить, '
     '− удалить, ⬇ экспорт в файл, ⬆ импорт из файла (шаринг с командой).'],
], [5.2, 13.8])

h2(doc, '4.5 Блок иерархии')
p(doc, 'Расположен сразу после категории NAMING. Кнопка Scan запускает проверку структуры сцены против '
       'пайплайн-конвенций (см. раздел 6): asset-корни, функциональные слои, партиции, суффиксы групп. '
       'Находки агрегируются по правилам - одна строка на правило с примерами объектов, разворот по '
       'клику. Режим Issues only прячет чистые ветки. В Live-режиме скан перезапускается сам, когда '
       'структура сцены меняется (главный сценарий - приёмка ассета после импорта FBX).')

h2(doc, '4.6 Список Objects')
add_table(doc, [
    ['Элемент', 'Что делает'],
    ['Поиск', 'Фильтр объектов по имени; счётчик в заголовке показывает «N / M».'],
    ['Issues', 'Переключатель «только проблемные». Включён по умолчанию: чистые объекты не показываются, '
     'заголовок пишет «All objects clean», когда брака нет.'],
    ['Карточка объекта', 'V/E/F/T - счётчики вершин, рёбер, граней, треугольников; строки находок по '
     'включённым чекам с количеством.'],
    ['Sel', 'Выделяет бракованные компоненты в Edit mode и приближает камеру к ним (viewFit).'],
    ['Show', 'Подсвечивает находки во вьюпорте без выделения.'],
    ['Fix', 'Кнопки исправления у чеков, которые умеют чинить сами (см. §8.4 и §6.4).'],
    ['Ign', 'Игнорирование чека на этом объекте: находка исчезает из счётов и статусов, чек помечается '
     'серым. Список игноров - блок «Ignored Issues» под Objects.'],
], [4.5, 14.5])

h2(doc, '4.7 Asset Status и экспорт')
add_table(doc, [
    ['Элемент', 'Что делает'],
    ['ASSET STATUS', 'READY (зелёный) / REVIEW (жёлтый) / CRITICAL (красный, английские подписи '
     '«production-ready», «needs more work», «publish blocked») - сводный вердикт по всем находкам '
     'включённых чеков. В Coordinator Mode сюда же эскалируются находки иерархии.'],
    ['Export: JSON / CSV / HTML', 'Полный отчёт в файл. HTML содержит секцию «Fix first» - блокеры по '
     'убыванию количества с именами объектов.'],
    ['Pre-flight FBX / USD', 'Валидация перед экспортом: при активных BLOCKER экспорт блокируется '
     'с отчётом, WARNING проходит с предупреждением.'],
    ['Checkpoint', 'Save / Load - снимок и восстановление состояния валидации (включённые чеки + '
     'результаты). Удобно перед экспериментами: Load вернёт картинку, Run пересчитает.'],
    ['Debug Info', 'Кнопка в самом низу: копирует в буфер диагностику - версии Blender/аддона/ОС, '
     'режим, активные чеки, последние 40 строк лога. Прикладывайте к баг-репортам.'],
], [5.2, 13.8])

h2(doc, '4.8 Coordinator-панель')
p(doc, 'При включённом Coordinator Mode панель показывает: плашку вердикта (ASSET STATUS с пояснением - '
       '«Blockers must be resolved before publish» / «Warnings require artist decision»), кнопку '
       'Copy Report, блок Critical & Warning Checks (только BLOCKER и WARNING) и те же Export/Pre-flight/'
       'Checkpoint. Возврат в артистский вид - кнопка Artist Mode в тулбаре.')

# ════════════════════════════════════════════════════════════════════════════
# 5. ЧЕКЕРЫ BLENDER
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '5. Чекеры (Blender)')
p(doc, '42 чека в 7 категориях + Scene Units. Состав и критичность соответствуют коду v1.7.5; '
       'пороги части чеков настраиваются в Preferences (вкладка UV).')

h2(doc, '5.1 Scene Units (сцена)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Scene Units', 'BLOCKER', 'System ≠ Metric, Unit ≠ Meters, Scale ≠ 1.0',
     'Неверные единицы ломают texel density, физику, экспорт FBX (масштаб ×100) и любые '
     'инструменты, завязанные на реальные размеры'],
], [3.5, 2.5, 5.5, 7])

h2(doc, '5.2 TOPOLOGY - топология (14)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Non Manifold', 'BLOCKER', 'Рёбра с ≠ 2 смежными гранями (T-стыки, рёбра без граней)',
     'Ломает булевы операции, симуляции, расчёт нормалей и экспорт, требующий замкнутого объёма'],
    ['Duplicate Verts', 'BLOCKER', 'Совпадающие вершины в пределах одной связной шели (порог 0,01 мм). '
     'Совпадения вершин разных шелей (болты на броне) - намеренная практика и не флагуются',
     'Нарушают нормали и шейдинг, ломают симуляции. Возникают после boolean, knife, случайного Ctrl+D'],
    ['Zero Area', 'BLOCKER', 'Грани с площадью ≈ 0',
     'Вырожденные грани дают NaN в нормалях, ломают UV. Побочный продукт boolean и Merge'],
    ['Z-Fighting', 'BLOCKER', 'Копланарные грани, перекрывающие друг друга',
     'Мерцание в рендере и real-time. Классический артефакт задвоенной геометрии'],
    ['Lamina', 'BLOCKER', '«Ламинарные» грани - контур грани проходит по одним рёбрам дважды '
     '(напр., после вытягивания и складывания на себя)',
     'Нулевая толщина ломает булевы операции и экспорт'],
    ['Zero Length Edges', 'BLOCKER', 'Рёбра нулевой длины (включая сшитые контуры граней)',
     'Дегенеративная геометрия ломает subdivide и экспорт'],
    ['Ngons', 'WARNING', 'Грани с 5+ рёбрами',
     'Непредсказуемо триангулируются рендером; артефакты нормалей на хардсёрфе'],
    ['Isolated Verts', 'WARNING', 'Вершины, не связанные ни с одним ребром',
     'Мусорная геометрия: засоряет vertex groups и UV, не видна в рендере'],
    ['Starlike', 'WARNING', 'Грани, невидимые из собственного центроида: самопересечения контура, '
     'вогнутость с центроидом снаружи, сшитые нулевые рёбра',
     'Такая грань неверно триангулируется - артефакты шейдинга и запекания'],
    ['Sharp Edges Not Hard', 'WARNING', 'Острые рёбра (диэдральный угол ≥ 30°), не помеченные Sharp',
     'Гладкое затенение на остром угле даёт артефакт шейдинга'],
    ['Triangles', 'INFO', 'Треугольные грани',
     'Мидполи-воркфлоу допускает триангуляцию - ревью артистом. Критично только в деформ-зонах'],
    ['Boundary Edges', 'INFO', 'Открытые рёбра - ровно одна смежная грань',
     'Могут быть намеренными (вырезы, скрытые грани). Подсветка для ревью'],
    ['Face Aspect Ratio', 'INFO', 'Квады с соотношением сторон выше порога (по умолчанию 6:1)',
     'Вытянутые квады дают артефакты при subdivide и скиннинге'],
    ['Poles', 'INFO', 'Вершины с нестандартным числом рёбер (3, 5, >5, 0)',
     'Полюса влияют на subdivide и скиннинг, но часто намеренны'],
], [3.4, 2.4, 6.1, 6.6], sev_col=1)

h2(doc, '5.3 TRANSFORMS - трансформы (6)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Non Applied Transform', 'BLOCKER', 'Ненулевой поворот объекта',
     'Неприменённый поворот меняет направления нормалей при экспорте, ломает физику и ориентацию костей'],
    ['Scale', 'BLOCKER', 'Scale ≠ 1.0 по любой оси (допуск 0,001)',
     'Ненормализованный scale искажает симуляции, деформации скелета и расчёт TD'],
    ['Modifier Stack', 'WARNING', 'Неприменённые модификаторы (кроме Armature)',
     'Случайный Subdivision, Bevel или Mirror меняет финальную геометрию при экспорте'],
    ['Parent Geometry', 'WARNING', 'Меш, запарентченный на другой меш',
     'Ломает иерархию ассета и попытки скриптовой сборки сцены'],
    ['Origin At Zero', 'INFO', 'Пивот объекта не в мировом нуле',
     'Может быть намеренным (петля, шарнир). Подсветка для ревью'],
    ['Uncentered Pivots', 'INFO', 'Пивот сильно смещён от центра собственного bbox (>5% диагонали)',
     'Конвенционный чек: у «зданий» и локаторов пивот в стороне - легитимно, решает артист'],
], [3.8, 2.4, 5.6, 6.7], sev_col=1)

h2(doc, '5.4 SYMMETRY - симметрия (3)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Symmetry X / Y / Z', 'INFO', 'Вершины без зеркальной пары по оси (KD-tree)',
     'Нарушенная симметрия ломает mirror-риг, blend shapes. Включать осознанно для симметричных '
     'объектов - персонажи, транспорт'],
], [3.8, 2.4, 5.6, 6.7], sev_col=1)

h2(doc, '5.5 UV - развёртка (9)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['UV Overlap', 'BLOCKER', 'Перекрывающиеся UV-острова разных материальных групп',
     'Оверлап = одинаковые текселы для разных полигонов: невозможно запечь уникальные текстуры'],
    ['UV UDIM Bounds', 'BLOCKER', 'UV-острова, выходящие за границы UDIM-тайла',
     'Остров в двух тайлах = невозможно назначить правильную UDIM-текстуру'],
    ['Uv Material Udim', 'BLOCKER', 'Несколько материальных групп на одном UDIM-тайле',
     'Ломает UDIM-адресацию рендерера и автоматизацию текстурирования'],
    ['UV Single Set', 'WARNING', 'Количество UV-сетов ≠ 1',
     'Несколько сетов - признак незавершённой работы или конфликта пайплайна'],
    ['UV Micro Shell', 'WARNING', 'UV-острова с площадью ниже порога (≈ 6×6 px при 2048)',
     'Острова слишком мелкие для текстурирования, зря занимают атлас'],
    ['UV Stretch', 'WARNING', 'Грани, где UV-угол сильно отличается от 3D-угла',
     'Стрейч = искажение текстуры: заметно на паттернах и normal map'],
    ['UV Texel Density', 'INFO', 'Отклонение TD от целевого значения (px/cm)',
     'Без заданного Target TD - просто показывает реальное значение'],
    ['UV Padding', 'INFO', 'Расстояние между шеллами < порога, до границы тайла < порога',
     'Недостаточный padding даёт bleeding при mip-мипинге; может варьироваться намеренно'],
    ['Missing UVs', 'WARNING', 'Грани без UV-координат',
     'Невозможно запечь/натянуть текстуру на такие грани'],
], [3.4, 2.4, 5.9, 6.8], sev_col=1)

h2(doc, '5.6 NAMING - нейминг (6)')
p(doc, 'Правила нейминга настраиваются в Preferences → Naming (префиксы/суффиксы объектов, групп, '
       'меш-данных; см. §9). Чеки сверяют имена с этой политикой.')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Object Name', 'WARNING', 'Дефолтные имена (Cube, pCube1), нумерация .001, спецсимволы, '
     'заглавные буквы, несоответствие префиксам/суффиксам',
     'Некорректные имена ломают скрипты ассет-менеджера и точное сопоставление имён'],
    ['Group Name', 'WARNING', 'Те же правила для коллекций + префикс/суффикс групп',
     'Нарушенный нейминг ломает иерархию, LOD-системы и сборку шотов'],
    ['Mesh Data Name', 'WARNING', 'Имя блока данных меша (Mesh.101), не совпадающее с именем объекта',
     'Замусоренные дата-блоки всплывают в скриптах и при линковке'],
    ['Mat Numbering', 'WARNING', 'Имена материалов с нумерацией (.001, .002)',
     'Нумерованный материал - копия вместо оригинала; ломает материальную библиотеку'],
    ['Duplicated Names', 'BLOCKER', 'Совпадающие имена объектов в сцене',
     'Коллизии имён ломают линковку библиотек и экспорт - в отличие от Blender-нумерации это '
     'содержательный конфликт, а не косметика'],
    ['Trailing Numbers', 'WARNING', 'Хвостовые числа в именах (bolt01, wheel2)',
     'Конвенционный чек: правильная нумерация партиций - строго двузначная через подчёркивание'],
], [3.2, 2.4, 6.2, 6.7], sev_col=1)

h2(doc, '5.7 MATERIALS - материалы (3)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Mat Assignment', 'BLOCKER', 'Пустые слоты материалов',
     'Объект с пустым слотом рендерится чёрным/дефолтным - брак в продакшн-рендере'],
    ['Missing Textures', 'BLOCKER', 'Image Texture ноды с отсутствующим файлом',
     'Пропавший файл = розовый/чёрный рендер'],
    ['Mat Suffix', 'WARNING', 'Имена материалов без суффикса _mat',
     'Единый суффикс отличает материалы от мешей и групп в скриптах'],
], [3.4, 2.4, 5.9, 6.8], sev_col=1)

h2(doc, '5.8 CLEANUP - чистка (1)')
add_table(doc, [
    ['Чек', 'Критичность', 'Что ищет', 'Зачем нужен'],
    ['Unused Data', 'WARNING', 'Пустые vertex groups, shape keys без правок, кастомные атрибуты-мусор '
     '(встроенные атрибуты Blender не трогаются; GN-атрибуты защищены при живом модификаторе)',
     'Мусорные данные раздувают файл и мешают авто-риггерам. Fix удаляет зафлагованное через диалог'],
], [3.4, 2.4, 6.2, 6.5], sev_col=1)

# ════════════════════════════════════════════════════════════════════════════
# 6. ИЕРАРХИЯ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '6. Валидатор иерархии')

h2(doc, '6.1 Конвенции структуры ассета')
p(doc, 'Иерархия ассета собирается из групп-пустышек (в Maya для этого используются локаторы). '
       'Валидатор проверяет структуру против конвенций:')
for b in [
    'корень ассета - пустышка-группа с суффиксом _grp (например, truck_a_grp);',
    'внутри - функциональные слои (geo, proxy, rig, wip и т.п.): набор свободный, есть встроенный '
    'whitelist из 24 распространённых имён, расширяется в Preferences;',
    'партиции повторяющихся элементов - строго двузначная нумерация через подчёркивание: bolt_01, '
    'bolt_02 (bolt_1 и bolt_002 - нарушения);',
    'все группы с групповой ролью - с суффиксом _grp;',
    'имена - строчные, без .001, без запрещённых символов, без дефолтных DCC-имён;',
    'свет и камеры в структуру ассета не входят и не валидируются; статичный ассет допускается '
    'группировать прямо в корне.',
]:
    p(doc, b, bullet=True)

h2(doc, '6.2 Правила (13)')
add_table(doc, [
    ['Правило', 'Критичность', 'Что ловит'],
    ['Blender numbering (.001)', 'ERROR', 'Копии с автонумерацией .001 - признак дублирования вместо переименования'],
    ['Missing group suffix', 'ERROR', 'Группа с групповой ролью без суффикса _grp'],
    ['Forbidden characters', 'ERROR', 'Запрещённые символы в именах узлов'],
    ['Default DCC name', 'ERROR', 'Дефолтные имена пакета (Cube, Empty, pCube1…)'],
    ['Empty group', 'ERROR', 'Пустышка с групповой ролью без детей - незаполненный локатор после импорта'],
    ['Uppercase in name', 'WARNING', 'Заглавные буквы в имени'],
    ['Unknown functional layer', 'WARNING', 'Слой не из whitelist (дополняется в Preferences)'],
    ['Orphan empty', 'WARNING', 'Пустышка, недостижимая ни от одного asset-корня'],
    ['Orphan mesh', 'WARNING', 'Меш, недостижимый ни от одного asset-корня'],
    ['Name mismatch in group', 'WARNING', 'Имя узла не соответствует паттерну <base> / <base>_NN своей группы'],
    ['Mesh under mesh', 'WARNING', 'Меш, запарентченный на меш (дубль чека Parent Geometry)'],
    ['No asset root', 'WARNING', 'В сцене нет ни одного asset-корня'],
    ['Multiple asset roots', 'WARNING', 'Несколько корней - проверьте, что это намеренно'],
], [5.2, 2.8, 10.5], sev_col=1)

h2(doc, '6.3 Сканирование')
for b in [
    'Scan - ручной запуск скана; результат - сворачиваемые секции по asset-корням со своими '
    'счётчиками ERROR/WARNING, плюс секции «Not connected to any root» и сцены-левел находки.',
    'Issues only - показывать только проблемные ветки.',
    'Live-автоскан: при включённом Live скан перезапускается сам после изменений структуры '
    '(импорт FBX, репарентинг, переименования). Бейдж «Stale» - результат устарел, запустите Scan.',
    'X у находки - игнор правила на этом узле; счётчик «N ignored - clear» сбрасывает игноры.',
]:
    p(doc, b, bullet=True)

h2(doc, '6.4 Исправления')
add_table(doc, [
    ['Fix', 'Что делает'],
    ['Add _grp', 'Добавляет суффикс _grp группе; коллизии имён пропускаются с репортом'],
    ['Renumber', 'Приводит нумерацию партиций к двузначной сетке base_01… (легальные имена не '
     'трогаются; переименование двухпроходное через временные имена - без коллизий)'],
    ['Adopt Orphans', 'Подключает осиротевшие узлы к корню: один корень - автоматически, несколько - '
     'с диалогом'],
    ['Create Root', 'Создаёт asset-корень; опция сразу подключить сирот'],
    ['Create Asset Skeleton', 'Генератор скелета статичного ассета: имя берётся из файла .blend, '
     'галочками выбираются слои из whitelist. Ассет рождается легальным, валидатор - приёмка'],
], [4.5, 14])
kv_note(doc, 'Все фиксы иерархии пересканируют структуру сразу после применения.')

h2(doc, '6.5 Гейт координатора')
p(doc, 'В Artist Mode находки иерархии не влияют на Asset Status - WIP-ассет имеет право на '
       'несобранную структуру. В Coordinator Mode ошибки иерархии эскалируют вердикт: ERROR → CRITICAL, '
       'WARNING → REVIEW. Скан даёт вердикт даже для сцен без трекнутых чекерами объектов. Настройки '
       'whitelist и суффикса - Preferences → Naming → Hierarchy.')

# ════════════════════════════════════════════════════════════════════════════
# 7. ОВЕРЛЕИ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '7. Оверлеи во вьюпорте')
p(doc, 'Брак рисуется поверх геометрии цветом чека (свотч в строке чека, палитра - Preferences → '
       'Colors):')
add_table(doc, [
    ['Тип', 'Как рисуется', 'Примеры'],
    ['Грани', 'Полупрозрачная заливка граней (Faces Alpha)', 'ngons, triangles, starlike, lamina, '
     'zero area, uv stretch, missing uvs'],
    ['Рёбра', 'Линии по рёбрам (Edges Width / Edges Alpha); у трансформ-чеков - жирная обводка силуэта',
     'non manifold, boundary edges, sharp edges, z-fighting, non applied transform, scale'],
    ['Точки', 'Маркеры вершин/центроидов (Vertex Size / Point Offset)',
     'isolated verts, duplicate verts, poles, symmetry'],
], [2.8, 9.4, 6.8])
for b in [
    'X-Ray (кнопка в Pipeline Checks): выкл - стенки меша окклюдируют метки дальней стороны; вкл '
    '(дефолт) - метки видны сквозь всё. Штатный xray вьюпорта принудительно включает просвет.',
    'Face Offset / Point Offset - отступ меток от поверхности, если оверлей мерцает с геометрией.',
    'Sel в карточке объекта выделяет брак в Edit mode; Show - подсвечивает без выделения.',
    'Face Orientation - штатный оверлей нормалей Blender, вызывается из панели (синий/красный = '
    'направление нормали).',
]:
    p(doc, b, bullet=True)

# ════════════════════════════════════════════════════════════════════════════
# 8. РЕЖИМЫ И ИНСТРУМЕНТЫ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '8. Режимы и инструменты')

h2(doc, '8.1 Live')
p(doc, 'Live следит за типами изменений и пересчитывает только затронутое: топология (правка меша, '
       'boolean, join), UV-координаты, трансформы, переименования объектов и меш-данных. Новые объекты '
       'добавляются в валидацию автоматически, бейдж «Scene changed» напоминает о расширении области. '
       'В Live также пересканируется иерархия. Для тяжёлых сцен пересчёт идёт пачками с прогрессом в панели.')

h2(doc, '8.2 Пресеты')
p(doc, 'Пресет = набор включённых чеков + правила нейминга. Сохранение - значок + рядом с дропдауном, '
       'удаление - −. Экспорт/импорт файлом: готовый пресет (например «midpoly» или «hero subdiv») '
       'можно раздать файлом другим пользователям. Пресет хранится в префах Blender и переживает '
       'обновления аддона.')

h2(doc, '8.3 Отчёты')
add_table(doc, [
    ['Формат', 'Что внутри', 'Куда'],
    ['Copy Summary (артист)', 'Компактная сводка по категориям + подпись валидатора и дата', 'Буфер обмена'],
    ['Copy Report (координатор)', 'Вердикт VALIDATION: READY/REVIEW/BLOCKED + секции BLOCKERS '
     '(fix first) и WARNINGS - формальный вердикт приёмки', 'Буфер обмена'],
    ['JSON / CSV / HTML', 'Полные данные: объекты, чеки, находки, иерархия; HTML - с секцией '
     '«Fix first»', 'Файл'],
], [4.6, 10.4, 4])
kv_note(doc, 'Подпись валидатора: Preferences → Interface → Validator (по умолчанию - логин ОС). '
             'Попадает во все отчёты и Debug Info.')

h2(doc, '8.4 Исправления (Fix)')
p(doc, 'Чеки с автоматическим исправлением: Non Applied Transform, Scale (Apply Transform), Modifier '
       'Stack (Apply), Object/Group/Mesh Data Name (переименование по политике), Mat Numbering, Unused '
       'Data (диалог очистки), фиксы иерархии (§6.4). Кнопка Fix стоит в строке чека карточки объекта. '
       'В Coordinator Mode с включённым Coordinator Lock все Fix скрыты - координатор смотрит, но не чинит.')

h2(doc, '8.5 Checkpoint')
p(doc, 'Checkpoint Save фиксирует состояние валидации в сцене (включённые чеки + результаты), '
       'Checkpoint Load восстанавливает. Полезно перед risky-правками: снял чекпоинт → поэкспериментировал → '
       'загрузил обратно. Restore-подсказка напомнит нажать Run для пересчёта.')

h2(doc, '8.6 Pre-flight')
p(doc, 'Pre-flight FBX / USD = гейт перед экспортом: если есть активные BLOCKER, экспорт блокируется '
       'с отчётом; только WARNING - проходит с пометкой. Так битый ассет не доезжает до пайплайна.')

h2(doc, '8.7 Логи и диагностика')
for b in [
    'Сессия-лог пишется в %TEMP%/stukach.log (ротация ~256 КБ в .old).',
    'Debug Info в буфер: версии, режим, активные чеки, хвост лога - вставьте в баг-репорт.',
    'При краше Blender лог в %TEMP% - первая вещь, которую просит автор.',
]:
    p(doc, b, bullet=True)

# ════════════════════════════════════════════════════════════════════════════
# 9. НАСТРОЙКИ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '9. Настройки (Preferences)')
p(doc, 'Preferences → Add-ons → STUKACH. Вкладки: Interface, Overlay, UV, Naming, Colors.')

add_table(doc, [
    ['Вкладка', 'Параметры'],
    ['Interface', 'Start in Coordinator Mode - панель открывается сразу в режиме приёмки; '
     'Coordinator Lock - прятать все кнопки Fix в Coordinator Mode (координатор только валидирует); '
     'Validator - имя в подписи отчётов.'],
    ['Overlay', 'X-Ray Overlay - прозрачность меток (§7); Edges Width, Edges/Faces Alpha; '
     'Faces/Points Offset; Vertex Size.'],
    ['UV', 'Texel Density: размер текстуры, целевая TD (px/cm), допуск (Target = 0 → только показ '
     'значения); UV Padding: пороги шелла и границы тайла; пороги stretch и aspect ratio.'],
    ['Naming', 'Objects и Groups: списки префиксов/суффиксов (+/−); Mesh Data: суффикс дата-блока '
     '(по умолчанию _mesh); Hierarchy: суффикс групп (_grp) и функциональный whitelist (дополняет '
     '24 встроенных слоя).'],
    ['Colors', 'Цвет оверлея каждого чека, сетка в две колонки; применяется к вьюпорту сразу.'],
], [3, 16])

# ════════════════════════════════════════════════════════════════════════════
# 10. СЦЕНАРИИ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '10. Как пользоваться')

h2(doc, '10.1 Артисту')
for b in [
    'Загрузите готовый пресет набора чеков (Presets → импорт) или работайте с дефолтным набором; '
    'включите Live.',
    'RUN по выделению; расширьте до Scene/Collection, если нужно покрыть всю сцену.',
    'Работайте по списку Objects: Sel выделяет брак и приближает камеру, оверлей показывает его '
    'цветом чека, Live пересчитывает после правок автоматически.',
    'BLOCKER чините обязательно (где возможно - кнопкой Fix), WARNING - осознанно принять или '
    'исправить, INFO - по вкусу. Next Issue циклично проводит по оставшемуся браку.',
    'После импорта ассета из FBX новые объекты подхватываются Live сами, иерархия пересканируется '
    'автоматически - структуру приводите в порядок фиксами из §6.4.',
    'Перед сдачей переключитесь в Coordinator Mode и убедитесь, что вердикт не BLOCKED; перед '
    'экспериментами полезен Checkpoint Save (§8.5).',
]:
    p(doc, b, bullet=True)

h2(doc, '10.2 Координатору')
for b in [
    'Включите Coordinator Mode: INFO скрыты, остаются только BLOCKER и WARNING.',
    'Прогоните валидацию по Scene (или по коллекции ассета).',
    'Смотрите вердикт ASSET STATUS: CRITICAL - есть блокеры, REVIEW - есть предупреждения, требующие '
    'решения, READY - ассет чист.',
    'Copy Report кладёт в буфер формальный вердикт с секциями BLOCKERS (fix first) и WARNINGS.',
    'Если нужно только валидировать, включите Coordinator Lock (Preferences → Interface): кнопки Fix '
    'будут скрыты; флаг Start in Coordinator Mode открывает панель сразу в этом режиме.',
]:
    p(doc, b, bullet=True)

# ════════════════════════════════════════════════════════════════════════════
# 11. MAYA
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '11. Maya-версия')

h2(doc, '11.1 Панель')
p(doc, 'Кнопка STUKACH на полке открывает панель с той же логикой, что и в Blender: Run, тулбар '
       'режимов (Coordinator / Live / меню «…» с флагами координатора), score-блок, Next Issue, Copy '
       'Summary, Objects, ASSET STATUS, Delivery (Export / Pre-flight / Checkpoint), Debug Info. '
       'Панель по умолчанию докается слева от Attribute Editor; закрытие - крестиком, повторное '
       'открытие - кнопкой полки (hot-reload встроен).')

h2(doc, '11.2 Чеки: 43 + два сцен-чека')
add_table(doc, [
    ['Категория', 'Чеки', 'Отличия от Blender'],
    ['TOPOLOGY (14)', 'non manifold, boundary edges, isolated verts, duplicate verts, face aspect '
     'ratio, triangles, ngons, poles, zero area, z-fighting, hard edges, lamina, zero length edges, '
     'starlike', 'Hard Edges вместо Sharp Edges Not Hard: флагуются гладкие рёбра с углом ≥ 30°'],
    ['TRANSFORMS (6)', 'non applied transform, scale, construction history, origin at zero, '
     'uncentered pivots, parent geometry', 'Construction History (бинарный + разбор типов узлов) '
     'вместо Modifier Stack'],
    ['SYMMETRY (3)', 'symmetry X / Y / Z', 'как в Blender'],
    ['UV (10)', 'single set, udim ready, udim bounds, material udim, overlap, micro shell, stretch, '
     'texel density, padding, missing uvs', 'Есть UDIM Ready - готовность сетки к UDIM-тайлам'],
    ['NAMING (6)', 'object name, group name, mat numbering, duplicated names, shape names, '
     'trailing numbers', 'Shape Names - имя шейп-узла против трансформы; нет Mesh Data Name '
     '(это концепция Blender)'],
    ['MATERIALS (3)', 'mat suffix, mat assignment, missing textures', 'как в Blender'],
    ['CLEANUP (1)', 'unused data (пустые группы деформаторов, кастомные атрибуты)', 'как в Blender'],
    ['Сцена', 'Scene Units + Empty Groups', 'Empty Groups - трансформы без детей: классические '
     'пустые группы после пересборок; удаляются только вручную'],
], [3.2, 9.3, 6.5])

h2(doc, '11.3 Скорость: снапшот и прогрессивная валидация')
p(doc, 'Геометрия снимается в снапшот за два прохода итераторов OpenMaya; 14 геометрических чеков '
       'считаются по одной traversal (без повторных запросов к сцене). Валидация идёт очередью '
       'небольшими пачками - интерфейс Maya остаётся живым даже на тяжёлых сценах, прогресс виден в '
       'панели. Объекты дольше секунды логируются.')
kv_note(doc, 'Для массовых чеков (сотни тысяч компонентов) действует порог: в отчёт идёт честное '
             'количество, а для оверлея/выделения берётся равномерный сэмпл до 5000 - строка чека '
             'помечается «5000 sampled», кнопка Sel отключается.')

h2(doc, '11.4 Оверлей')
p(doc, 'Цветная подсветка брака рисуется нативным плагином Viewport 2.0 (stukachDrawOverride): '
       'залитые грани, линии рёбер, маркеры вершин, плюс wireframe-бокс для трансформ-чеков. Если '
       'плагин недоступен (другая ОС/версия Maya), оверлей автоматически переключается на запасной '
       'режим через display layers. Цвета настраиваются свотчами в панели.')

h2(doc, '11.5 Иерархия локаторов')
for b in [
    'Структура ассета собирается в Maya локаторами-группами по конвенциям §6.1 (_grp, base_01, '
    'строчные имена).',
    'После экспорта/импорта FBX структура проверяется валидатором иерархии Blender-версии: группы, '
    'созданные из локаторов, приходят с суффиксом _grp и проходят правила нейминга.',
    'Валидации иерархии в Maya-версии нет - приёмка структуры делается в Blender.',
]:
    p(doc, b, bullet=True)

h2(doc, '11.6 Нюансы Maya-версии')
for b in [
    'Hard Edges молчит в зонах с кастомными нормалями (Weighted Normal и аналоги): Maya читает '
    'смежные рёбра как hard - это особенность пакета, не бага чекера.',
    'UV UDIM Bounds может флагать чистые объекты с UV на границе тайла (uv = 1.0) - известное '
    'ограничение, решается лёгким сдвигом шва.',
    'После обновления файлов STUKACH обязательно hot-reload кнопкой полки - Maya не перечитывает '
    'модули сама.',
    'Лог: %TEMP%/stukach_maya.log; Debug Info копирует диагностику в буфер.',
    'Кнопки Sel у массовых находок (>5000) отключаются - это защита от фризов, счётчик остаётся честным.',
]:
    p(doc, b, bullet=True)

# ════════════════════════════════════════════════════════════════════════════
# 12. FAQ
# ════════════════════════════════════════════════════════════════════════════

h1(doc, '12. Решение проблем')

add_table(doc, [
    ['Симптом', 'Что это и что делать'],
    ['«Settings restored - press Run to revalidate»', 'Штатное сообщение STUKACH: настройки восстановлены '
     'из сцены при открытии файла. Нажмите Run - это не чужой аддон и не ошибка.'],
    ['Бейдж/подсказка «Scene changed» или Stale', 'Сцена изменилась после прогона/скана. Перезапустите '
     'Run или Scan; в Live большая часть подхватится сама.'],
    ['Объект не появляется в Objects', 'Он вне области проверки: первый RUN берёт Selected. Расширьте '
     'до Scene/Collection. Включён фильтр поиска или Issues-only - проверьте заголовок «N / M».'],
    ['Оверлей просвечивает сквозь меш', 'Это кнопка X-Ray в Pipeline Checks (v1.7.5): выключите - '
     'стенки скроют метки дальней стороны. Также включённый Alt+Z (xray вьюпорта) принудительно '
     'делает оверлей прозрачным.'],
    ['Метки оверлея мерцают с геометрией', 'Увеличьте Face/Point Offset в Pipeline Checks.'],
    ['Находка кажется ложной', 'Проверьте порог чека в Preferences; игнорируйте точечно (Ign на '
     'объекте, X у правила иерархии). Если ложная системно - приложите Debug Info и напишите автору.'],
    ['Кнопка Fix недоступна / отсутствует', 'У чека нет авторематизации - правится руками; либо '
     'вы в Coordinator Mode с Coordinator Lock (фиксы спрятаны намеренно).'],
    ['Счётчик большой, Sel выключена («5000 sampled»)', 'Порог защиты от фризов Maya-версии: количество '
     'честное, выделение/оверлей работают по сэмплу. Чините областями.'],
    ['Maya: панель не появилась после обновления', 'Сделайте hot-reload повторным кликом кнопки полки; '
     'проверьте Plug-in Manager (stukachDrawOverride.mll). Перезапуск Maya решает остаточные случаи.'],
    ['Краш Blender / подвисание', 'Не закрывайте Blender до снятия лога: %TEMP%/stukach.log + кнопка '
     'Debug Info до краша. Краш-дампы Blender (.crash) лежат в %TEMP%.'],
], [5.4, 13.6])

p(doc, ' ')
kv_note(doc, 'Баг-репорты и пожелания: github.com/abyrvalg379/STUKACH/issues (Blender), '
             'github.com/abyrvalg379/STUKACH_Maya/issues (Maya). Прикладывайте Debug Info и сценарий '
             'воспроизведения.  © Maksim Kovalev, 2026. Лицензия GPL-3.0.')

add_footer_pagenum(doc)
doc.save(OUT)
print(f'Saved: {OUT}')
