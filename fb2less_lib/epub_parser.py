import zipfile
import os
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import re

class EPUBParser:
    def __init__(self, filename, unknown_author="Unknown"):
        self.paragraphs = []
        self.notes = {}
        self.meta = {
            'title': str(os.path.basename(filename)), 
            'author': str(unknown_author),
            'series': '',
            'annotation': ''
        }
        self.encoding = 'utf-8'
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
                        val = "".join(el.itertext()).strip()
                        if val: self.meta['title'] = str(val)
                    elif tag == 'creator':
                        val = "".join(el.itertext()).strip()
                        if val: self.meta['author'] = str(val)

                manifest = {it.get("id"): it.get("href") for it in opf_xml.findall(".//{*}item")}
                spine = [it.get("idref") for it in opf_xml.findall(".//{*}itemref")]

                # 3. Список названий глав из NCX
                toc_titles = set()
                try:
                    ncx_item = opf_xml.find(".//{*}item[@media-type='application/x-dtbncx+xml']")
                    if ncx_item is not None:
                        ncx_p = os.path.join(opf_dir, unquote(ncx_item.get('href'))).replace('\\', '/')
                        ncx_xml = ET.fromstring(z.read(ncx_p))
                        for t_node in ncx_xml.findall(".//{*}text"):
                            if t_node.text:
                                toc_titles.add(" ".join(t_node.text.split()).strip().lower())
                except: pass

                # --- 4. УМНЫЙ СБОР ТЕКСТОВ СНОСОК ---
                for h in manifest.values():
                    h_lower = h.lower()
                    if not (h_lower.endswith('.html') or h_lower.endswith('.xhtml')): continue
                    try:
                        f_p = os.path.join(opf_dir, unquote(h)).replace('\\', '/')
                        h_raw = z.read(f_p).decode('utf-8', 'ignore')
                        h_root = ET.fromstring(h_raw)
                        for el in h_root.iter():
                            nid = el.get('id')
                            if nid:
                                clean_id = nid.lstrip('#')
                                note_txt = "".join(el.itertext()).strip()
                                # Фильтруем: не берем слишком длинный текст и заголовки глав
                                if 1 < len(note_txt) < 1500:
                                    is_note_file = any(x in h_lower for x in ['note', 'reft', 'anc', 'nt'])
                                    is_note_id = any(x in clean_id.lower() for x in ['n', 'fn', 'ref'])
                                    if is_note_file or is_note_id or clean_id.isdigit():
                                        self.notes[clean_id] = " ".join(note_txt.split())
                    except: continue

                # --- 5. СБОР ТЕКСТА КНИГИ ---
                added_titles = []
                for item_id in spine:
                    if item_id not in manifest: continue
                    f_path = os.path.join(opf_dir, unquote(manifest[item_id])).replace('\\', '/')
                    
                    try:
                        raw_data = z.read(f_path).decode('utf-8', 'ignore')
                        raw_data = raw_data.replace('&nbsp;', ' ').replace('&shy;', '')
                        raw_data = re.sub(r'&(?!(amp|lt|gt|quot|apos);)', '&amp;', raw_data)
                        raw_data = raw_data.replace('<br/>', '\n').replace('<br>', '\n')
                        
                        root = ET.fromstring(raw_data)
                        body = root.find(".//{*}body") or root

                        for el in body.iter():
                            tag = el.tag.split('}')[-1].lower()
                            cls = (el.get('class') or '').lower()
                            
                            if tag in ['p', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote', 'div']:
                                if any(child.tag.split('}')[-1].lower() in ['p', 'div', 'h1', 'h2', 'li'] for child in el):
                                    continue

                                pieces = []
                                if el.text: pieces.append(el.text)
                                for child in el:
                                    c_tag = child.tag.split('}')[-1].lower()
                                    if c_tag == 'br': 
                                        pieces.append('\n')
                                    elif c_tag == 'a':
                                        lbl = "".join(child.itertext()).strip()
                                        href = child.get('href', '')
                                        tid = (href.split('#')[-1] if '#' in href else "").lstrip('#')
                                        
                                        if lbl and len(lbl) < 10:
                                            # Избегаем двойных скобок [[ ]]
                                            display_lbl = lbl if (lbl.startswith('[') and lbl.endswith(']')) else f"[{lbl}]"
                                            pieces.append(f" {display_lbl}")
                                            # Связываем текст ссылки с ID в словаре для кнопки 'f'
                                            clean_key = lbl.strip('[]')
                                            if tid in self.notes:
                                                self.notes[clean_key] = self.notes[tid]
                                        else:
                                            pieces.append(lbl if lbl else tid)
                                    else:
                                        pieces.append("".join(child.itertext()))
                                    if child.tail: pieces.append(child.tail)
                                
                                text_block = "".join(pieces).strip()
                                if not text_block: continue

                                clean_low = " ".join(text_block.split()).lower()
                                is_title = tag.startswith('h') or clean_low in toc_titles
                                is_poem = any(x in cls for x in ['poem', 'verse', 'stanza', 'v'])

                                if is_title:
                                    if clean_low not in added_titles:
                                        self.paragraphs.append(('title', " ".join(text_block.split())))
                                        added_titles.append(clean_low)
                                        if len(added_titles) > 20: added_titles.pop(0)
                                elif is_poem:
                                    for line in text_block.split('\n'):
                                        clean_line = line.strip()
                                        if clean_line:
                                            self.paragraphs.append(('poem', clean_line))
                                else:
                                    self.paragraphs.append(('body', " ".join(text_block.split())))
                        
                        self.paragraphs.append(('body', ""))
                    except: continue
        except Exception as e:
            self.paragraphs = [('body', f"Error: {e}")]

def epub_parse(filename, unknown_author="Unknown", error_label="Error"):
    parser = EPUBParser(filename, unknown_author)
    parser.error_label = error_label
    return parser
