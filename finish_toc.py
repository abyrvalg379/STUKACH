# -*- coding: utf-8 -*-
r"""Финализация оглавления (двухпроходная) для документов на _docstyle.

Использование:  python finish_toc.py <имя-без-расширения>
Ожидает:        <имя>.docx (уже собран генератором) и <имя>.h1.json
                со списком H1: ["1. О программе", ...]
Делает:
  1) docx -> pdf, замер реальной страницы каждого H1;
  2) вставка записей оглавления (только уровень 1) с настоящими номерами;
  3) пере-конвертация pdf.
"""

import json
import os
import re
import subprocess
import sys

import pymupdf

SOFFICE = r'C:\Program Files\LibreOffice\program\soffice.exe'
PLACEHOLDER = (r'C:\Users\mkova\.zcode\cli\plugins\cache\zcode-plugins-official'
               r'\documents\0.1.7\skills\docx\scripts\add_toc_placeholders.py')


def convert(name):
    subprocess.run([SOFFICE, '--headless', '--convert-to', 'pdf', '--outdir', '.',
                    name + '.docx'], capture_output=True)


def main():
    name = sys.argv[1]
    h1_list = json.load(open(name + '.h1.json', encoding='utf-8'))

    convert(name)
    d = pymupdf.open(name + '.pdf')
    pages_text = [p.get_text() for p in d]
    total = len(d)
    entries = []
    for title in h1_list:
        m = re.match(r'^(\d+)\.\s*(.+)$', title)
        num = m.group(1) if m else ''
        major = (m.group(2) if m else title).split(' (')[0]
        needle = major.upper().replace(' ', '')
        found = None
        for pno in range(1, total):  # титул и оглавление пропускаем
            for line in pages_text[pno].splitlines():
                s = line.strip()
                if '..' in s:  # строки оглавления с лидерами не считаем
                    continue
                su = s.upper().replace(' ', '')
                if su.startswith(num + '.') and needle in su:
                    found = pno + 1
                    break
            if found:
                break
        entries.append({'level': 1, 'text': title, 'page': str(found or 2)})
    d.close()
    json.dump(entries, open(name + '.entries.json', 'w', encoding='utf-8'),
              ensure_ascii=False)

    subprocess.run([sys.executable, PLACEHOLDER, name + '.docx',
                    '--entries', json.dumps(entries, ensure_ascii=False)],
                   capture_output=True, text=True)
    convert(name)
    d = pymupdf.open(name + '.pdf')
    print('finish:', name, '- pages:', len(d))
    d.close()


if __name__ == '__main__':
    main()
