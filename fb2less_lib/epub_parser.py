import zipfile
import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote

class EPUBParser:
    # Добавляем аргумент unknown_author
    def __init__(self, filename, unknown_author="Unknown"):
        self.paragraphs = []
        self.notes = {}
        self.meta = {
            'title': os.path.basename(filename), 
            'author': unknown_author, # Используем переменную
            'series': '',
            'annotation': ''
        }
        self.encoding = 'utf-8'
        # Передаем ее дальше в метод _parse, если нужно, 
        # но тут она используется только в заглушке __init__
        self._parse(filename)

    def _parse(self, filename):
        try:
            with zipfile.ZipFile(filename, "r") as z:
                # 1. Поиск структуры (OPF)
                container = ET.fromstring(z.read("META-INF/container.xml"))
                opf_path = container.find(".//{*}rootfile").get("full-path")
                opf_dir = os.path.dirname(opf_path)
                opf_xml = ET.fromstring(z.read(opf_path))
                
                # 2. МЕТАДАННЫЕ
                for el in opf_xml.iter():
                    tag = el.tag.split('}')[-1].lower()
                    if tag == 'title':
                        self.meta['title'] = " ".join("".join(el.itertext()).split()).strip()
                    elif tag == 'creator':
                        self.meta['author'] = " ".join("".join(el.itertext()).split()).strip()

                manifest = {it.get("id"): it.get("href") for it in opf_xml.findall(".//{*}item")}
                spine = [it.get("idref") for it in opf_xml.findall(".//{*}itemref")]

                # 3. ОГЛАВЛЕНИЕ NCX
                toc_titles = set()
                try:
                    ncx_item = opf_xml.find(".//{*}item[@media-type='application/x-dtbncx+xml']")
                    if ncx_item is not None:
                        ncx_p = os.path.join(opf_dir, unquote(ncx_item.get('href'))).replace('\\', '/')
                        ncx_xml = ET.fromstring(z.read(ncx_p))
                        for t_node in ncx_xml.findall(".//{*}text"):
                            if t_node.text:
                                toc_titles.add(t_node.text.strip().lower())
                except: pass

                # 4. СБОР ВСЕХ СНОСОК (ID) - Умный фильтр
                for h in manifest.values():
                    if not (h.lower().endswith('.html') or h.lower().endswith('.xhtml')): continue
                    try:
                        f_p = os.path.join(opf_dir, unquote(h)).replace('\\', '/')
                        h_root = ET.fromstring(z.read(f_p))
                        for el in h_root.iter():
                            nid = el.get('id')
                            if nid:
                                note_txt = "".join(el.itertext()).strip()
                                tag = el.tag.split('}')[-1].lower()
                                if 0 < len(note_txt) < 2000 and tag not in ['body', 'html', 'section']:
                                    self.notes[nid] = " ".join(note_txt.split())
                    except: continue
# 5. СБОР ТЕКСТА
                for item_id in spine:
                    if item_id not in manifest: continue
                    f_path = os.path.join(opf_dir, unquote(manifest[item_id])).replace('\\', '/')
                    
                    try:
                        raw_data = z.read(f_path).decode('utf-8', 'ignore')
                        raw_data = raw_data.replace('<br/>', '\n').replace('<br>', '\n').replace('</p>', '\n</p>')
                        
                        root = ET.fromstring(raw_data)
                        current_container_type = 'body'

                        for el in root.iter():
                            tag = el.tag.split('}')[-1].lower()
                            cls = (el.get('class') or '').lower()
                            
                            if tag == 'div':
                                current_container_type = 'epigraph' if 'epigraph' in cls else 'body'
                                if el.find('.//{*}p') is not None: continue

                            if tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div']:
                                if tag == 'div' and el.find('.//{*}p') is not None: continue
                                
                                # СБОР ТЕКСТА С ПОМЕТКОЙ ССЫЛОК
                                pieces = []
                                if el.text: pieces.append(el.text)
                                for child in el:
                                    c_tag = child.tag.split('}')[-1].lower()
                                    if c_tag == 'a':
                                        lbl = "".join(child.itertext()).strip()
                                        href = child.get('href', '')
                                        tid = href.split('#')[-1] if '#' in href else ""
                                        # Используем ID как метку для reader.py
                                        pieces.append(f" [{tid if tid else lbl}]")
                                    else:
                                        pieces.append("".join(child.itertext()))
                                    if child.tail: pieces.append(child.tail)
                                
                                text_block = "".join(pieces).strip()
                                
                                if text_block:
                                    sub_parts = text_block.split('\n')
                                    for part in sub_parts:
                                        clean_part = " ".join(part.split()).strip()
                                        if clean_part:
                                            is_in_toc = clean_part.lower() in toc_titles
                                            if tag.startswith('h') or is_in_toc:
                                                p_type = 'title'
                                            elif 'epigraph' in cls or current_container_type == 'epigraph':
                                                p_type = 'epigraph'
                                            else:
                                                p_type = 'body'
                                            
                                            self.paragraphs.append((p_type, clean_part))
                        
                        self.paragraphs.append(('body', ""))
                    except: continue
        except Exception as e:
            # error_label мы добавим в __init__ или передадим в метод
            err_prefix = getattr(self, 'error_label', 'Error')
            self.paragraphs = [('body', f"{err_prefix}: {e}")]

def epub_parse(filename, unknown_author="Unknown", error_label="Error"):
    parser = EPUBParser(filename, unknown_author)
    parser.error_label = error_label
    return parser

