import xml.etree.ElementTree as ET
import zipfile
import re
import os

class FB2Parser:
    # Добавляем аргументы для локализации меток по умолчанию
    def __init__(self, filename, unknown_title="Неизвестно", unknown_author="Неизвестный автор"):
        self.paragraphs = []
        self.notes = {}
        # Используем переданные переводы
        self.meta = {
            'title': unknown_title, 
            'author': unknown_author, 
            'series': '', 
            'annotation': ''
        }
        self.encoding = 'utf-8'
        self._parse(filename, unknown_author) # Передаем автора дальше для логики парсинга

    def _parse(self, filename, unknown_author):
        tree = None
        try:
            if filename.lower().endswith('.zip'):
                with zipfile.ZipFile(filename, 'r') as z:
                    fbs = [n for n in z.namelist() if n.lower().endswith('.fb2')]
                    if fbs:
                        with z.open(fbs[0]) as f: raw_data = f.read()
            else:
                with open(filename, 'rb') as f: raw_data = f.read()

            # 1. Сначала ищем кодировку прямо в байтах (через регулярку)
            # Это надежнее, чем просто перебор
            match = re.search(rb'encoding=["\'](.*?)["\']', raw_data[:500])
            if match:
                found_enc = match.group(1).decode('ascii').lower()
                encs = [found_enc, 'utf-8', 'cp1251', 'koi8-r']
            else:
                encs = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']

            for enc in encs:
                try:
                    # Декодируем
                    text_data = raw_data.decode(enc)
                    # КРИТИЧНО: Убираем XML-декларацию, она часто мешает ElementTree 
                    # если кодировка в ней не совпадает с тем, как мы декодировали вручную
                    text_data = re.sub(r'^<\?xml.*?\?>', '', text_data, flags=re.DOTALL | re.MULTILINE)
                    
                    root = ET.fromstring(text_data.strip())
                    tree = ET.ElementTree(root)
                    self.encoding = enc
                    break 
                except: continue
        except: return

        if tree is None: return
        root = tree.getroot()
        parent_map = {c: p for p in root.iter() for c in p}

        # 2. МЕТАДАННЫЕ
        title_info = root.find(".//{*}title-info")
        if title_info is not None:
            t = title_info.find("{*}book-title")
            if t is not None: self.meta['title'] = t.text
            a = title_info.find("{*}author")
            if a is not None:
                fn = a.find("{*}first-name")
                ln = a.find("{*}last-name")
                f_t = (fn.text or "").strip() if fn is not None else ""
                l_t = (ln.text or "").strip() if ln is not None else ""
                # Если автор пуст, используем локализованную заглушку
                self.meta['author'] = f"{f_t} {l_t}".strip() or unknown_author
            ann = title_info.find("{*}annotation")
            if ann is not None: self.meta['annotation'] = " ".join(ann.itertext()).strip()

        # 3. СНОСКИ (собираем в словарь)
        for body in root.findall(".//{*}body"):
            if body.get('name') == 'notes':
                for section in body.findall(".//{*}section"):
                    n_id = section.get('id')
                    if n_id: self.notes[n_id] = " ".join(section.itertext()).strip()

        # 4. ОСНОВНОЙ ПАРСИНГ
        for el in root.iter():
            tag = el.tag.split('}')[-1]
            if tag not in ('p', 'v', 'text-author', 'empty-line', 'subtitle', 'title'): continue

            # 1. Если это сам контейнер <title>, мы его СКИПАЕМ. 
            # Мы поймаем его содержимое (теги <p>) на следующем шаге итерации.
            if tag == 'title':
                continue

            p_type = 'body'
            is_history = is_ann_parent = is_in_notes = is_in_skip_section = False
            
            curr = el
            while curr in parent_map:
                curr = parent_map[curr]
                p_tag = curr.tag.split('}')[-1].lower()
                
                # Если любой из родителей — title, значит наш текущий элемент (например <p>)
                # должен иметь тип 'title'.
                if p_tag == 'title' and not is_ann_parent: 
                    p_type = 'title'
                
                if p_tag == 'history': is_history = True; break
                if p_tag == 'annotation': is_ann_parent = True
                if p_tag == 'body' and curr.get('name') == 'notes': is_in_notes = True
                if p_tag == 'epigraph': p_type = 'epigraph'
                if p_tag == 'cite': p_type = 'cite'
                if p_tag == 'stanza': p_type = 'poem'
                if p_tag == 'section':
                    s_id = (curr.get('id') or '').lower()
                    if 'note' in s_id or 'remark' in s_id: is_in_skip_section = True

            if is_in_notes or is_in_skip_section or is_history: continue
            if tag == 'text-author': p_type = 'author'
            
            # Тот самый ЯВНЫЙ empty-line (ставим просто пустую строку)
            if tag == 'empty-line':
                self.paragraphs.append(('body', ''))
                continue

            # СБОР ТЕКСТА (со сносками)
            full_text = el.text or ""
            for child in el:
                c_tag = child.tag.split('}')[-1]
                if c_tag == 'a':
                    note_id = ""
                    for attr_name, attr_val in child.attrib.items():
                        if attr_name.split('}')[-1] == 'href':
                            note_id = attr_val.replace('#', '')
                            break
                    note_text = "".join(child.itertext()).strip().strip('[]')
                    display_text = note_text or note_id
                    full_text += f" [{display_text}]"
                else:
                    full_text += "".join(child.itertext())
                if child.tail: full_text += child.tail

            text = " ".join(full_text.split()).strip()
            if text:
                self.paragraphs.append((p_type, text))

def fb2parse(filename, unknown_title="Unknown", unknown_author="Unknown Author"): 
    return FB2Parser(filename, unknown_title, unknown_author)

def get_fast_title(filename):
    try:
        if filename.lower().endswith('.zip'):
            with zipfile.ZipFile(filename, 'r') as z:
                fbs = [n for n in z.namelist() if n.lower().endswith('.fb2')]
                if fbs:
                    # Чиним индекс: берем fbs[0]
                    with z.open(fbs[0]) as f: raw = f.read(150000)
        else:
            with open(filename, 'rb') as f: raw = f.read(150000)
        match = re.search(b'<(?:.*:)?book-title>(.*?)</(?:.*:)?book-title>', raw, re.DOTALL)
        if match:
            res = match.group(1).decode('utf-8', errors='ignore')
            return re.sub('<[^>]*>', '', res).strip()
    except: pass
    return os.path.basename(filename)

