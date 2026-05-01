import xml.etree.ElementTree as ET
import zipfile
import re
import os

class FB2Parser:
    def __init__(self, filename, unknown_title="Неизвестно", unknown_author="Неизвестный автор"):
        self.paragraphs = []
        self.notes = {}
        self.toc = []  # Список кортежей: (Название главы, индекс в paragraphs)
        self.meta = {
            'title': unknown_title, 
            'author': unknown_author, 
            'series': '', 
            'annotation': '', 
            'publish': ''
        }
        self.encoding = 'utf-8'
        self._load_and_parse(filename, unknown_author)

    def _load_and_parse(self, filename, unknown_author):
        raw_data = None
        try:
            if filename.lower().endswith('.zip'):
                with zipfile.ZipFile(filename, 'r') as z:
                    fbs = [n for n in z.namelist() if n.lower().endswith('.fb2')]
                    if fbs:
                        with z.open(fbs[0]) as f: raw_data = f.read()
            else:
                with open(filename, 'rb') as f: raw_data = f.read()
        except: return

        if not raw_data: return

        match = re.search(rb'encoding=["\'](.*?)["\']', raw_data[:500])
        encs = [match.group(1).decode('ascii').lower()] if match else ['utf-8', 'cp1251', 'koi8-r']
        
        root = None
        for enc in encs:
            try:
                text_data = raw_data.decode(enc)
                text_data = re.sub(r'^<\?xml.*?\?>', '', text_data, flags=re.DOTALL | re.MULTILINE)
                root = ET.fromstring(text_data.strip())
                self.encoding = enc
                break
            except: continue

        if root is not None:
            self._extract_all(root, unknown_author)

    def _extract_all(self, root, unknown_author):
        for el in root.iter():
            el.tag = el.tag.split('}')[-1]

        # Метаданные
        ti = root.find(".//title-info")
        if ti is not None:
            t_el = ti.find("book-title")
            if t_el is not None: self.meta['title'] = t_el.text
            auth = ti.find("author")
            if auth is not None:
                fn = (auth.findtext("first-name") or "").strip()
                mn = (auth.findtext("middle-name") or "").strip()
                ln = (auth.findtext("last-name") or "").strip()
                self.meta['author'] = f"{fn} {mn} {ln}".replace("  ", " ").strip() or unknown_author
            
            seq = ti.find("sequence")
            if seq is not None:
                s_name = seq.get("name", "")
                s_num = seq.get("number")
                self.meta['series'] = f"{s_name} #{s_num}" if s_num else s_name
            
            ann = ti.find("annotation")
            if ann is not None:
                self.meta['annotation'] = " ".join(ann.itertext()).strip()

        pub = root.find(".//publish-info")
        if pub is not None:
            p_name = pub.findtext("publisher")
            p_year = pub.findtext("year")
            self.meta['publish'] = f"{p_name or ''} {p_year or ''}".strip()

        for body in root.findall("body"):
            if body.get('name') == 'notes':
                for sec in body.findall("section"):
                    n_id = sec.get('id')
                    if n_id: self.notes[n_id] = " ".join(sec.itertext()).strip()

        for body in root.findall("body"):
            if body.get('name') != 'notes':
                self._walk(body)
    def _walk(self, element, mode='body', is_section=False):
        for child in element:
            tag = child.tag
            new_mode = mode
            
            if tag == 'section':
                self._walk(child, mode='body', is_section=True)
                continue

            if tag == 'title':
                text = self._get_text_with_notes(child)
                if text:
                    if is_section: self.toc.append((text, len(self.paragraphs)))
                    self.paragraphs.append(('title', text))
                continue

            if tag == 'epigraph': new_mode = 'epigraph'
            elif tag == 'cite': new_mode = 'cite'
            elif tag == 'stanza': new_mode = 'poem'
            elif tag == 'subtitle': new_mode = 'subtitle'

            # Если внутри блока (epigraph, cite) есть вложенные <p>, 
            # мы можем решить: склеивать их или нет.
            
            if tag in ('p', 'v', 'text-author', 'subtitle'):
                text = self._get_text_with_notes(child)
                if text:
                    emp = child.find('emphasis')
                    is_full_emphasis = (emp is not None and (child.text is None or not child.text.strip()))

                    if new_mode == 'poem': 
                        text = "    " + text
                    
                    # Если это блок курсива и предыдущий был таким же — клеим
                    if is_full_emphasis and self.paragraphs and self.paragraphs[-1][0] == 'emphasis_block':
                        prev_mode, prev_text = self.paragraphs[-1]
                        self.paragraphs[-1] = ('emphasis_block', prev_text + " " + text)
                    elif is_full_emphasis:
                        self.paragraphs.append(('emphasis_block', text))
                    else:
                        # УБРАЛИ символ ">" для цитат и эпиграфов
                        # Если это автор, помечаем специальным типом
                        p_type = 'author' if tag == 'text-author' else new_mode
                        self.paragraphs.append((p_type, text))
                        
                        # Если это был автор, добавляем пустую строку сразу за ним
                        if tag == 'text-author':
                            self.paragraphs.append(('body', ''))
            
            elif tag == 'empty-line':
                self.paragraphs.append(('body', ''))
            elif tag == 'table':
                self._process_table(child)
            else:
                self._walk(child, new_mode, is_section)

    def _get_text_with_notes(self, el):
        full_text = el.text or ""
        for child in el:
            if child.tag == 'a':
                note_id = ""
                for attr, val in child.attrib.items():
                    if attr.endswith('href'):
                        note_id = val.replace('#', '')
                        break
                note_text = "".join(child.itertext()).strip().strip('[]')
                full_text += f" [{note_text or note_id}]"
            else:
                full_text += "".join(child.itertext())
            if child.tail: full_text += child.tail
        return " ".join(full_text.split()).strip()

    def _process_table(self, table_el):
        for tr in table_el.findall(".//tr"):
            cells = [" ".join(td.itertext()).strip() for td in (tr.findall("./td") or tr.findall("./th"))]
            if cells:
                self.paragraphs.append(('body', "\t".join(cells)))

def fb2parse(filename, unknown_title="Unknown", unknown_author="Unknown Author"): 
    return FB2Parser(filename, unknown_title, unknown_author)
def get_fast_title(filename):
    try:
        raw = b""
        if filename.lower().endswith('.zip'):
            with zipfile.ZipFile(filename, 'r') as z:
                fbs = [n for n in z.namelist() if n.lower().endswith('.fb2')]
                if fbs:
                    with z.open(fbs[0]) as f: raw = f.read(150000)
        else:
            with open(filename, 'rb') as f: raw = f.read(150000)
            
        match = re.search(b'<(?:.*:)?book-title>(.*?)</(?:.*:)?book-title>', raw, re.DOTALL)
        if match:
            res = match.group(1).decode('utf-8', errors='ignore')
            return re.sub('<[^>]*>', '', res).strip()
    except:
        pass
    return os.path.basename(filename)
