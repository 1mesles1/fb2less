import curses, os, json, time, re, textwrap
from .fb2_parser import fb2parse, get_fast_title
from .layout import prepare_layout
from .txt_parser import txt_parse
from .epub_parser import epub_parse

class MainWindow:
    def __init__(self, stdscr, filename):
        self.screen = stdscr
        self.filename = os.path.abspath(filename)
        self.history_file = os.path.expanduser("~/.fb2less_history")
        self.auto_scroll = False
        self.scroll_speed = 2
        self.last_auto_time = time.time()
        
        # 1. Сначала загружаем историю
        hist = self.load_history()
        
        # 2. Берем данные
        self.par_index = hist.get("pos", 0)
        self.fg = hist.get("fg", 7)
        self.bg = hist.get("bg", 0)
        self.head_color = hist.get("hc", 6)
        self.width = hist.get("width", 100)
        self.scroll_speed = hist.get("speed", 3)
        self.bookmarks = hist.get("bookmarks", [])
        if not isinstance(self.bookmarks, list):
            self.bookmarks = [] # Если там старый словарь, сбрасываем в пустой список
        self.show_border = hist.get("border", 0)
        self.flip_mode = hist.get("flip", 0) 
        
        # 3. Загрузка языка
        # Определяем путь к папке с переводами относительно файла reader.py
        locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
        try:
            self.available_langs = sorted([
                f[:-5] for f in os.listdir(locales_dir) if f.endswith('.json')
            ])
        except:
            self.available_langs = ['en', 'ru']

        # Загружаем язык (из истории, или по умолчанию 'en')
        self.lang_code = hist.get("lang", "en")
        
        # Если сохраненный язык вдруг удалили из папки, берем первый доступный
        if self.lang_code not in self.available_langs:
            self.lang_code = self.available_langs[0] if self.available_langs else 'en'
            
        self.load_lang(self.lang_code)
        
        # --- ЗАГРУЗКА КОНТЕНТА (уже с учетом перевода) ---
        ext = filename.lower()
        if ext.endswith('.txt'):
            self.content = txt_parse(filename, unknown_author=self.tr('meta_unknown'))
        elif ext.endswith('.epub'):
            self.content = epub_parse(
                filename, 
                unknown_author=self.tr('meta_unknown'),
                error_label=self.tr('meta_error')
            )
        elif ext.endswith(('.fb2', '.zip')):
            self.content = fb2parse(
                filename, 
                unknown_title=self.tr('meta_unknown_title'), 
                unknown_author=self.tr('meta_unknown')
            )
        else:
            self.content = type('Empty', (), {
                'paragraphs': [], 
                'notes': {}, 
                'meta': {
                    'title': self.tr('meta_error'), 
                    'author': self.tr('meta_unknown'), 
                    'series': '', 
                    'annotation': ''
                },
                'encoding': '???'
            })

        if not self.content.paragraphs:
            self.content.paragraphs = [('body', self.tr('err_empty_file'))]

        self.notes = getattr(self.content, 'notes', {})
        self.lines = []
        
        self.search_query = ""
        curses.start_color()
        curses.use_default_colors()
        self.update_colors()
        self.prepare_lines()
        self.last_note_idx = -1
        self.last_note_pos = -1
        self.run()

    def update_colors(self): 
        curses.init_pair(1, self.fg, self.bg)
        curses.init_pair(2, self.head_color, self.bg)
        curses.init_pair(3, self.bg, self.bg)
        curses.init_pair(4, -1, -1)
        curses.init_pair(5, self.bg, self.fg)
    
    def load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r") as f: 
                    return json.load(f).get(self.filename, {})
        except: pass
        return {}

    def save_history(self):
        try:
            data = {}
            if os.path.exists(self.history_file):
                with open(self.history_file, "r") as f: 
                    data = json.load(f)
            
            data[self.filename] = {
                "pos": self.par_index, 
                "fg": self.fg, 
                "bg": self.bg, 
                "hc": self.head_color,
                "width": self.width, 
                "speed": self.scroll_speed,
                "bookmarks": self.bookmarks,
                "flip": self.flip_mode,
                "border": self.show_border,
                # Используем ключ для неизвестного названия
                "title": self.content.meta.get('title', self.tr('meta_unknown_title')),
                "time": time.time(),
                "lang": self.lang_code  # Сохраняем выбранный язык в историю
            }
            with open(self.history_file, "w") as f: 
                json.dump(data, f)
        except: 
            pass

    def load_lang(self, lang_code):
        import json
        self.lang_code = lang_code
        base_path = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_path, 'locales', f'{lang_code}.json')
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        except Exception:
            self.translations = {}

    def tr(self, key):
        return self.translations.get(key, key)
    def jump_to_pct(self):
        self.screen.nodelay(False)
        r, c = self.screen.getmaxyx()
        
        # Используем ключ для текста приглашения
        prompt = self.tr('ui_jump_to') # "Перейти на %: "
        
        self.screen.attron(curses.color_pair(5))
        self.screen.move(r - 1, 0)
        self.screen.clrtoeol()
        # ДОБАВЛЕН - 1: чтобы не печатать в последнюю ячейку (r-1, c-1)
        self.screen.addstr(r - 1, 0, prompt + " " * (c - len(prompt) - 1))
        
        curses.echo()
        self.screen.attron(curses.color_pair(5))
        try:
            # Читаем ввод сразу после длины подсказки
            raw = self.screen.getstr(r - 1, len(prompt))
            val = int(raw.decode('utf-8'))
            if 0 <= val <= 100:
                self.par_index = int((len(self.lines) - 1) * (val / 100.0))
        except: pass
        
        self.screen.attroff(curses.color_pair(5))
        curses.noecho()
        self.screen.nodelay(True)

    def do_search(self):
        self.screen.nodelay(False)
        r, c = self.screen.getmaxyx()
        
        prompt = "/ "
        
        self.screen.attron(curses.color_pair(5))
        self.screen.move(r - 1, 0)
        self.screen.clrtoeol()
        # ИЗМЕНЕНИЕ: печатаем на один символ меньше (c - len(prompt) - 1)
        self.screen.addstr(r - 1, 0, prompt + " " * (c - len(prompt) - 1))
        
        curses.echo()
        curses.curs_set(1)
        self.screen.attron(curses.color_pair(5))
        try:
            # Читаем ввод
            raw = self.screen.getstr(r - 1, len(prompt))
            res = raw.decode('utf-8', errors='replace').strip()
            if res: 
                self.search_query = res
                self.find_next()
        except: pass
        
        self.screen.attroff(curses.color_pair(5))
        curses.noecho()
        curses.curs_set(0)
        self.screen.nodelay(True)

    def find_next(self):
        if not self.search_query: return
        for i in range(self.par_index + 1, len(self.lines)):
            p_type, text = self.lines[i]
            if self.search_query.lower() in text.lower():
                self.par_index = i
                return

    def find_prev(self):
        if not self.search_query: return
        for i in range(self.par_index - 1, -1, -1):
            p_type, text = self.lines[i]
            if self.search_query.lower() in text.lower():
                self.par_index = i
                return

    def jump_chapter(self, direction):
        step = 1 if direction > 0 else -1
        idx = self.par_index + step
        while 0 <= idx < len(self.lines):
            p_type, text = self.lines[idx]
            if p_type == "title":
                self.par_index = idx
                return
            idx += step

    def open_footnote(self):
        r, c = self.screen.getmaxyx()
        d_h = r - 3 if self.show_border == 2 else (r - 2 if self.show_border == 1 else r - 1)
        
        visible_notes = []
        for i in range(d_h):
            idx = self.par_index + i
            if idx < len(self.lines):
                line_data = self.lines[idx]
                line_text = line_data[1] if isinstance(line_data, tuple) else line_data
                m = re.findall(r'\[(.*?)\]', line_text)
                for note_id in m:
                    if note_id in self.content.notes or any(note_id in k for k in self.content.notes):
                        if note_id not in visible_notes:
                            visible_notes.append(note_id)

        if not visible_notes:
            return

        if self.par_index == self.last_note_pos:
            self.last_note_idx = (self.last_note_idx + 1) % len(visible_notes)
        else:
            self.last_note_idx = 0
            self.last_note_pos = self.par_index

        self.show_note(visible_notes[self.last_note_idx])

    def show_note(self, note_label):
        note_text = self.content.notes.get(note_label)
        if not note_text:
            digits = "".join(filter(str.isdigit, note_label))
            if digits:
                for k, v in self.content.notes.items():
                    if "".join(filter(str.isdigit, k)) == digits:
                        note_text = v; break
        if not note_text: return

        if len(note_text) > 1000:
            note_text = note_text[:500] + "..."

        r, c = self.screen.getmaxyx()
        max_w = min(c - 6, 70)
        wrapped = textwrap.wrap(note_text, width=max_w - 4)
        h = min(r - 4, len(wrapped) + 2)
        w = max_w
        y, x = (r - h) // 2, (c - w) // 2
        
        try:
            nw = curses.newwin(h, w, y, x)
            nw.keypad(True)
            nw.bkgd(" ", curses.color_pair(1))
            nw.box()
            # Локализованный заголовок окна
            header = f" {self.tr('ui_note_title')} "
            nw.addstr(0, 2, header, curses.A_BOLD)
            for i, line in enumerate(wrapped[:h-2]):
                nw.addstr(i + 1, 2, line)
            nw.refresh()
            nw.getch()
        except: pass
        self.redraw_scr()

    def show_help(self):
        r, c = self.screen.getmaxyx()
        # Загружаем список команд из локализации
        h_commands = self.tr('help_commands')
        
        h_h = min(r - 2, 22)
        h_w = min(c - 4, 60)
        h_y, h_x = (r - h_h) // 2, (c - h_w) // 2
        
        try:
            hw = curses.newwin(h_h, h_w, h_y, h_x)
            hw.keypad(True)
            hw.bkgd(" ", curses.color_pair(1))
            
            cur_top = 0
            visible_rows = h_h - 6 
            
            while True:
                hw.erase()
                hw.box()
                
                # Заголовок и подсказка из перевода
                header = f" {self.tr('help_header')} "
                hint = f" {self.tr('help_scroll_hint')} "
                
                hw.addstr(1, (h_w - len(header)) // 2, header, curses.A_BOLD)
                hw.addstr(2, 1, "-" * (h_w - 2))
                
                for i in range(visible_rows):
                    idx = i + cur_top
                    if idx < len(h_commands):
                        hw.addstr(i + 3, 2, h_commands[idx][:h_w-4])
                
                hw.addstr(h_h - 3, 1, "-" * (h_w - 2))
                hw.addstr(h_h - 2, (h_w - len(hint)) // 2, hint, curses.A_BOLD)
                
                hw.refresh()
                ch = hw.getch()
                
                if ch in [ord('j'), curses.KEY_DOWN]:
                    if cur_top + visible_rows < len(h_commands):
                        cur_top += 1
                elif ch in [ord('k'), curses.KEY_UP]:
                    if cur_top > 0:
                        cur_top -= 1
                elif ch in [27, ord('q'), ord('h'), 10, 13]:
                    break
        except: pass
        self.redraw_scr()

    def prepare_lines(self):
        r, c = self.screen.getmaxyx()
        border_space = 2 if self.show_border > 0 else 0
        w = min(c - border_space - 4, self.width)
        
        self.lines, self.toc = prepare_layout(
            self.content.paragraphs, 
            w, 
            self.content.meta.get('author', ''),
            notes=self.notes,
            # Передаем локализованный заголовок сносок
            notes_label=self.tr('ui_notes_section') 
        )

    def show_toc(self):
        if not self.toc: return
        r, c = self.screen.getmaxyx()

        max_t_len = 0
        for i, (title, l_idx) in enumerate(self.toc):
            full_t = f"{i+1}. {title}"
            if len(full_t) > max_t_len:
                max_t_len = len(full_t)

        w_win = max(35, min(c - 4, max_t_len + 4, 60)) 
        h_win = min(r - 4, len(self.toc) + 2)
        y, x = (r - h_win) // 2, (c - w_win) // 2
        
        try:
            tw = curses.newwin(h_win, w_win, y, x)
            tw.keypad(True)
            tw.bkgd(" ", curses.color_pair(1))
            
            cur = 0
            for i, (title, l_idx) in enumerate(self.toc):
                if l_idx <= self.par_index: cur = i

            r_available = h_win - 2
            off = max(0, cur - r_available // 2)
            if off > len(self.toc) - r_available:
                off = max(0, len(self.toc) - r_available)

            while True:
                tw.erase()
                tw.box()
                # Локализованный заголовок оглавления
                header = f" {self.tr('ui_toc_title')} "
                if w_win > len(header) + 2:
                    tw.addstr(0, (w_win - len(header)) // 2, header, curses.A_BOLD)
                
                if cur < off:
                    off = cur
                elif cur >= off + r_available:
                    off = cur - r_available + 1
                if off > len(self.toc) - r_available:
                    off = max(0, len(self.toc) - r_available)
                
                for i in range(r_available):
                    idx = i + off
                    if idx < len(self.toc):
                        style = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                        chapter_name = self.toc[idx][0]
                        max_text_w = w_win - 8
                        if len(chapter_name) > max_text_w:
                            chapter_name = chapter_name[:max_text_w-3] + "..."
                        
                        line_txt = f"{idx+1:2}. {chapter_name}"
                        tw.addstr(i + 1, 2, line_txt.ljust(w_win-5), style)
                
                tw.refresh()
                key = tw.getch()

                if key in [ord('j'), curses.KEY_DOWN]: 
                    cur = min(len(self.toc)-1, cur + 1)
                elif key in [ord('k'), curses.KEY_UP]: 
                    cur = max(0, cur - 1)
                elif key == curses.KEY_NPAGE: 
                    cur = min(len(self.toc)-1, cur + r_available)
                elif key == curses.KEY_PPAGE: 
                    cur = max(0, cur - r_available)
                elif key == curses.KEY_HOME: 
                    cur = 0
                elif key == curses.KEY_END: 
                    cur = len(self.toc) - 1
                elif key in [10, 13, curses.KEY_ENTER]:
                    self.par_index = self.toc[cur][1]
                    break
                elif key in [ord('q'), ord('t'), 27]: 
                    break
        except: pass
        self.redraw_scr()

    def show_info(self):
        r, c = self.screen.getmaxyx()
        
        # 1. Готовим текст
        m = self.content.meta
        # Используем локализованные метки
        info_text = [
            f" {self.tr('info_title')}: {m['title']}",
            f" {self.tr('info_author')}: {m['author']}",
        ]
        if m['series']:
            info_text.append(f" {self.tr('info_series')}: {m['series']}")
            
        info_text.append("-" * 40)
        
        # Техданные
        f_size = os.path.getsize(self.filename) // 1024
        # Определяем тип файла для вывода
        ext = self.filename.lower()
        if ext.endswith('.zip'): f_type = "ZIP/FB2"
        elif ext.endswith('.epub'): f_type = "EPUB"
        elif ext.endswith('.txt'): f_type = "TXT"
        else: f_type = "FB2"

        total_pages = (len(self.lines) // 50) + 1
        
        # Локализуем технические параметры
        info_text.append(f" {self.tr('info_file')}:     {os.path.basename(self.filename)} ({f_type})")
        info_text.append(f" {self.tr('info_size')}:   {f_size} KB")
        info_text.append(f" {self.tr('info_volume')}:   {len(self.lines)} {self.tr('info_lines')} (~{total_pages} {self.tr('info_pages')})")
        info_text.append("-" * 40)
        
        if m['annotation']:
            info_text.append(f" {self.tr('info_annot')}:")
            wrapped_ann = textwrap.wrap(m['annotation'], width=min(c - 10, 50))
            info_text.extend(["   " + line for line in wrapped_ann[:15]])
            if len(wrapped_ann) > 15: info_text.append("   ...")

        # 2. Отрисовка окна
        h_h, h_w = len(info_text) + 2, min(c - 4, 60)
        h_y, h_x = (r - h_h) // 2, (c - w_win if 'w_win' in locals() else h_w) // 2 # поправил
        y, x = (r - h_h) // 2, (c - h_w) // 2
        
        try:
            iw = curses.newwin(h_h, h_w, max(0, y), max(0, x))
            iw.keypad(True)
            iw.bkgd(" ", curses.color_pair(1))
            iw.box()
            for i, line in enumerate(info_text):
                if i < h_h - 2:
                    iw.addstr(i + 1, 2, line[:h_w-4])
            iw.refresh()
            iw.getch()
        except: pass
        self.redraw_scr()

    def scan_directory(self):
        r, c = self.screen.getmaxyx()
        # 1. Рисуем окошко "Сканирую"
        sw = curses.newwin(3, 26, (r-3)//2, (c-26)//2)
        sw.bkgd(" ", curses.color_pair(5))
        sw.box()
        # Локализуем "Сканирую..."
        scan_msg = self.tr('msg_scanning')
        sw.addstr(1, (26-len(scan_msg))//2, scan_msg)
        sw.refresh()

        start_dir = os.getcwd()
        found_new = 0
        
        try:
            with open(self.history_file, "r") as f: hist_data = json.load(f)
        except: hist_data = {}

        existing_titles = [info.get('title', '') for info in hist_data.values()]

        for root_dir, dirs, files in os.walk(start_dir):
            for file in files:
                if file.lower().endswith(('.fb2', '.fb2.zip', '.zip', '.epub', '.txt')):
                    full_path = os.path.abspath(os.path.join(root_dir, file))
                    
                    if full_path not in hist_data:
                        # ВАЖНО: поправил путь импорта на актуальный
                        from .fb2_parser import get_fast_title
                        title = get_fast_title(full_path)
                        
                        if title in existing_titles:
                            title = "*" + title
                        
                        hist_data[full_path] = {
                            "pos": 0, "fg": self.fg, "bg": self.bg, 
                            "hc": self.head_color, "width": self.width,
                            "speed": self.scroll_speed, "flip": self.flip_mode,
                            "border": self.show_border, "title": title,
                            "lang": self.lang_code
                        }
                        existing_titles.append(title)
                        found_new += 1

        deleted_count = 0
        paths_in_history = list(hist_data.keys())
        for path in paths_in_history:
            if not os.path.exists(path):
                del hist_data[path]
                deleted_count += 1

        if found_new > 0 or deleted_count > 0:
            with open(self.history_file, "w") as f:
                json.dump(hist_data, f)
        
        sw.erase()
        sw.box()
        # Сообщаем об успехе (локализованная строка с переменными)
        res_msg = f"{self.tr('scan_new')}: {found_new} / {self.tr('scan_del')}: {deleted_count}"
        sw.addstr(1, max(1, (26-len(res_msg))//2), res_msg[:24])
        sw.refresh()
        time.sleep(1.5)
        self.redraw_scr()

    def show_library(self):
        if not os.path.exists(self.history_file): return
        try:
            with open(self.history_file, "r") as f:
                hist_data = json.load(f)
        except: return

        all_items = []
        for path, info in hist_data.items():
            title = info.get('title', os.path.basename(path))
            all_items.append((path, title))
        all_items.sort(key=lambda x: x[1].lower())

        filter_query = ""
        cur = 0
        target = os.path.abspath(self.filename)
        for i, (path, title) in enumerate(all_items):
            if os.path.abspath(path) == target:
                cur = i; break

        r, c = self.screen.getmaxyx()
        w_win = min(c - 4, 60)
        h_win = min(r - 4, 30)
        y, x = (r - h_win) // 2, (c - w_win) // 2
        
        try:
            lw = curses.newwin(h_win, w_win, y, x)
            lw.keypad(True)
            lw.bkgd(" ", curses.color_pair(1))
            
            while True:
                # Фильтрация: ищем и в пути, и в заголовке
                if filter_query:
                    items = [it for it in all_items if filter_query.lower() in it[0].lower() or filter_query.lower() in it[1].lower()]
                else:
                    items = all_items

                if cur >= len(items): cur = max(0, len(items) - 1)
                # Если поиск активен — забираем 2 строки у списка
                r_available = h_win - (7 if filter_query else 4)

                lw.erase(); lw.box()
                lib_h = f" {self.tr('ui_lib_title')} "
                lw.addstr(0, (w_win - len(lib_h)) // 2, lib_h, curses.A_BOLD)

                off = max(0, cur - r_available // 2)
                if off > len(items) - r_available: off = max(0, len(items) - r_available)

                for i in range(r_available):
                    idx = i + off
                    if idx < len(items):
                        path, title = items[idx]
                        style = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                        lw.move(i + 1, 1); lw.addstr(" " * (w_win - 2), style)
                        try:
                            max_t_w = w_win - 4
                            d_t = title if len(title) <= max_t_w else title[:max_t_w-3] + "..."
                            t_attr = curses.color_pair(2) if idx != cur else style
                            lw.addstr(i + 1, 2, d_t, t_attr | curses.A_BOLD)
                        except: pass
                # --- ДВОЙНОЙ ПОДВАЛ ---
                lw.attron(curses.color_pair(1))
                if filter_query:
                    lw.hline(h_win - 5, 1, curses.ACS_HLINE, w_win - 2)
                    # Очищаем строку перед выводом поиска
                    lw.move(h_win - 4, 1); lw.addstr(" " * (w_win - 2))
                    p_prompt = self.tr('lib_search')
                    lw.addstr(h_win - 4, 2, f"{p_prompt}{filter_query}"[:w_win-4], curses.color_pair(2) | curses.A_BOLD)
                
                lw.hline(h_win - 3, 1, curses.ACS_HLINE, w_win - 2)
                # Очищаем строку перед выводом пути
                lw.move(h_win - 2, 1); lw.addstr(" " * (w_win - 2))
                if items:
                    path, title = items[cur]
                    display_path = path if len(path) < w_win - 6 else "..." + path[-(w_win-7):]
                    lw.addstr(h_win - 2, 2, display_path)
                lw.attroff(curses.color_pair(1))

                lw.refresh()
                key = lw.getch()
                if key in [ord('.'), 1102]: key = ord('/')

                if key == ord('/'):
                    p_str = self.tr('lib_search')
                    max_in = w_win - len(p_str) - 4
                    # Принудительная зачистка зоны ввода
                    lw.move(h_win - 4, 1); lw.addstr(" " * (w_win - 2))
                    lw.attron(curses.color_pair(1)); lw.hline(h_win - 5, 1, curses.ACS_HLINE, w_win - 2)
                    lw.addstr(h_win - 4, 2, p_str, curses.color_pair(2) | curses.A_BOLD); lw.attroff(curses.color_pair(1))
                    curses.echo(); curses.curs_set(1)
                    try:
                        raw = lw.getstr(h_win - 4, 2 + len(p_str), max_in)
                        filter_query = raw.decode('utf-8').strip()
                    except: pass
                    curses.noecho(); curses.curs_set(0); cur = 0
                elif key == 27:
                    if filter_query: filter_query = ""; cur = 0
                    else: break
                elif key in [ord('j'), curses.KEY_DOWN]: cur = min(len(items)-1, cur + 1)
                elif key in [ord('k'), curses.KEY_UP]: cur = max(0, cur - 1)
                elif key == curses.KEY_NPAGE: cur = min(len(items)-1, cur + r_available)
                elif key == curses.KEY_PPAGE: cur = max(0, cur - r_available)
                elif key == curses.KEY_HOME: cur = 0
                elif key == curses.KEY_END: cur = len(items) - 1
                elif key in [ord('d'), curses.KEY_DC] and items:
                    p_to_del, _ = items[cur]
                    if p_to_del in hist_data:
                        del hist_data[p_to_del]
                        with open(self.history_file, "w") as f: json.dump(hist_data, f)
                        all_items = [it for it in all_items if it[0] != p_to_del]
                elif key in [10, 13, curses.KEY_ENTER] and items:
                    new_p, _ = items[cur]; self.save_history(); self.filename = os.path.abspath(new_p)
                    h = hist_data.get(self.filename, {})
                    self.par_index = h.get("pos", 0)
                    
                    # ИСПРАВЬ ЭТУ СТРОКУ ТУТ:
                    self.bookmarks = h.get("bookmarks", [])
                    if not isinstance(self.bookmarks, list):
                        self.bookmarks = []
                        
                    if "lang" in h: self.load_lang(h["lang"])
                    ext = self.filename.lower()
                    if ext.endswith('.epub'): self.content = epub_parse(self.filename, self.tr('meta_unknown'), self.tr('meta_error'))
                    elif ext.endswith(('.fb2', '.zip')): self.content = fb2parse(self.filename, self.tr('meta_unknown_title'), self.tr('meta_unknown'))
                    else: self.content = txt_parse(self.filename, self.tr('meta_unknown'))
                    self.notes = getattr(self.content, 'notes', {}); self.prepare_lines(); return
                elif key in [ord('q'), ord('L')]: break
        except: pass
        self.redraw_scr()

    def show_bookmarks(self):
        if not self.bookmarks: return
        
        cur = 0
        r, c = self.screen.getmaxyx()
        w_win = min(c - 4, 50)
        h_win = min(r - 4, 15)
        y, x = (r - h_win) // 2, (c - w_win) // 2
        
        try:
            bw = curses.newwin(h_win, w_win, y, x)
            bw.keypad(True)
            bw.bkgd(" ", curses.color_pair(1))
            
            while True:
                bw.erase(); bw.box()
                title = f" {self.tr('ui_bookmarks')} "
                bw.addstr(0, (w_win - len(title)) // 2, title, curses.A_BOLD)
                
                for i, bm in enumerate(self.bookmarks[:h_win-2]):
                    style = curses.A_REVERSE if i == cur else curses.A_NORMAL
                    pct = int((bm['pos'] / len(self.lines)) * 100) if self.lines else 0
                    txt = f"{pct}%: {bm['text']}"[:w_win-4]
                    bw.addstr(i + 1, 2, txt.ljust(w_win-4), style)

                bw.refresh()
                key = bw.getch()

                if key in [ord('j'), curses.KEY_DOWN]: cur = min(len(self.bookmarks)-1, cur + 1)
                elif key in [ord('k'), curses.KEY_UP]: cur = max(0, cur - 1)
                elif key in [ord('x'), curses.KEY_DC]: # Удаление
                    self.bookmarks.pop(cur)
                    if not self.bookmarks: break
                    cur = max(0, cur - 1)
                elif key in [10, 13, curses.KEY_ENTER]: # Переход
                    self.par_index = self.bookmarks[cur]['pos']
                    break
                elif key in [ord('q'), 27, ord('M')]: break
        except: pass
        self.redraw_scr()


    def animate_flip(self, direction):
        r, c = self.screen.getmaxyx()
        if self.show_border == 0:
            x_l, x_r, y_top, y_bot = 0, c, 0, r - 1
        else:
            avail_c = c - 4 if self.show_border == 2 else c - 2
            w_curr = min(avail_c - 4, self.width)
            margin = (c - w_curr) // 2
            x_l = (0 if self.show_border == 1 else margin - 2) + 1
            x_r = (c - 1 if self.show_border == 1 else margin + w_curr + 1)
            y_top, y_bot = 1, r - 2
            
        width = x_r - x_l
        step = max(1, width // 20) 

        # --- ФАЗА 1: УХОД  ---
        if direction > 0:
            for x in range(x_r - 1, x_l - step, -step):
                for curr_x in range(x, min(x + step, x_r)):
                    if x_l <= curr_x < x_r:
                        self.screen.vline(y_top, curr_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                self.screen.refresh()
                time.sleep(0.01)
        else:
            for x in range(x_l, x_r + step, step):
                for curr_x in range(max(x_l, x - step), x):
                    if x_l <= curr_x < x_r:
                        self.screen.vline(y_top, curr_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                self.screen.refresh()
                time.sleep(0.01)

        d_h = r - 3 if self.show_border == 2 else (r - 2 if self.show_border == 1 else r - 1)
        self.par_index = max(0, min(len(self.lines)-1, self.par_index + (d_h if direction > 0 else -d_h)))

        # --- ФАЗА 2: ПОЯВЛЕНИЕ  ---
        if self.flip_mode == 2:
            # Старый B2: приход от края
            if direction > 0:
                for x in range(x_r - 1, x_l - step, -step):
                    self.redraw_scr()
                    for cover_x in range(x_l, x):
                        self.screen.vline(y_top, cover_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                    self.screen.refresh()
                    time.sleep(0.01)
            else:
                for x in range(x_l, x_r + step, step):
                    self.redraw_scr()
                    for cover_x in range(x, x_r):
                        self.screen.vline(y_top, cover_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                    self.screen.refresh()
                    time.sleep(0.01)
        elif self.flip_mode == 3:
            # B3: ИНВЕРТИРОВАННЫЙ приход (встречный)
            if direction > 0:
                for x in range(x_l, x_r + step, step):
                    self.redraw_scr()
                    for cover_x in range(x, x_r):
                        self.screen.vline(y_top, cover_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                    self.screen.refresh()
                    time.sleep(0.02)
            else:
                for x in range(x_r - 1, x_l - step, -step):
                    self.redraw_scr()
                    for cover_x in range(x_l, x):
                        self.screen.vline(y_top, cover_x, ord(' ') | curses.color_pair(3), y_bot - y_top)
                    self.screen.refresh()
                    time.sleep(0.02)
        else: 
            self.redraw_scr()

    def redraw_scr(self):

        r, c = self.screen.getmaxyx()

        # 1. РАСЧЕТЫ КООРДИНАТ
        if self.show_border == 2:
            top_offset, display_h = 1, r - 3
        elif self.show_border == 1:
            top_offset, display_h = 1, r - 2
        else:
            top_offset, display_h = 0, r - 1

        avail_c = c - 4 if self.show_border == 2 else (c - 2 if self.show_border == 1 else c)
        w_curr = min(avail_c - 4, self.width)
        margin = (c - w_curr) // 2

        # 2. ОЧИСТКА И ФОН (Листок бумаги)
        if self.show_border == 0:
            self.screen.bkgd(" ", curses.color_pair(1))
            self.screen.erase()
        else:
            self.screen.bkgdset(" ", curses.color_pair(4)) # Прозрачность
            self.screen.erase()
            
            # Заливка только области чтения цветом self.bg
            x_l = 0 if self.show_border == 1 else margin - 2
            x_r = c - 1 if self.show_border == 1 else margin + w_curr + 1
            for y in range(r - 1): 
                try: 
                    self.screen.addstr(y, x_l, " " * (x_r - x_l + 1), curses.color_pair(1))
                except: pass

        # 3. ОТРИСОВКА РАМОК
        if self.show_border > 0:
            self.screen.attron(curses.color_pair(1))
            x_l = 0 if self.show_border == 1 else margin - 2
            x_r = c - 1 if self.show_border == 1 else margin + w_curr + 1
            y_b = r - 1 if self.show_border == 1 else r - 2
            
            self.screen.hline(0, x_l + 1, curses.ACS_HLINE, x_r - x_l - 1)
            self.screen.hline(y_b, x_l + 1, curses.ACS_HLINE, x_r - x_l - 1)
            self.screen.vline(1, x_l, curses.ACS_VLINE, y_b - 1)
            self.screen.vline(1, x_r, curses.ACS_VLINE, y_b - 1)
            try:
                self.screen.addch(0, x_l, curses.ACS_ULCORNER)
                self.screen.addch(0, x_r, curses.ACS_URCORNER)
                self.screen.addch(y_b, x_l, curses.ACS_LLCORNER)
                self.screen.addch(y_b, x_r, curses.ACS_LRCORNER)
            except: pass
            self.screen.attroff(curses.color_pair(1))

        # 4. ОТРИСОВКА ТЕКСТА И ПОИСКА
        for i in range(display_h):
            idx = self.par_index + i
            if idx < len(self.lines):
                p_type, text = self.lines[idx]
                y = i + top_offset
                if y >= r - 1: break
                try:
                    attr = curses.color_pair(2 if p_type == "title" else 1)
                    if p_type == "title":
                        self.screen.addstr(y, (c - len(text)) // 2, text, attr | curses.A_BOLD)
                    else:
                        # 1. Сначала рисуем весь основной текст (обычным цветом)
                        self.screen.addstr(y, margin, text[:w_curr], attr)
                        
                        # 2. ПОДСВЕТКА СНОСОК (Цветом заголовков глав)
                        for m in re.finditer(r'\[.*?\]', text):
                            start, end = m.start(), m.end()
                            if start < w_curr:
                                note_label = text[start:min(end, w_curr)]
                                # Используем пару 2 (цвет глав)
                                self.screen.addstr(y, margin + start, note_label, curses.color_pair(2) | curses.A_BOLD)

                        # 3. ПОДСВЕТКА ПОИСКА (Поверх всего, инверсией)
                        if self.search_query:
                            s_query = self.search_query.lower()
                            s_text = text.lower()
                            last_found = 0
                            # Ищем все вхождения на случай, если слово повторяется в строке
                            while True:
                                start_pos = s_text.find(s_query, last_found)
                                if start_pos == -1 or start_pos >= w_curr: break
                                
                                # Берем оригинал текста из этой позиции (сохраняя регистр)
                                match = text[start_pos : start_pos + len(self.search_query)]
                                self.screen.addstr(y, margin + start_pos, match[:w_curr-start_pos], attr | curses.A_REVERSE)
                                
                                last_found = start_pos + len(s_query)
                except: pass
        # 5. СТАТУС-БАР
        try:
            # --- 1. ГОТОВИМ ДАННЫЕ ---
            # Лаконичный индикатор: просто [M], если список закладок не пуст
            bm_indicator = " [M]" if self.bookmarks else ""
            left_t = f"|==|:{self.width}{bm_indicator}"
            
            mid_t = f"{os.path.basename(self.filename)} [{self.content.encoding}]"
            
            mode_names = self.tr('ui_mode_names')
            f_mode = mode_names[self.flip_mode] if isinstance(mode_names, list) else "STD"
            
            total_l = len(self.lines)
            pct_val = min(100, int(((self.par_index + r) / total_l) * 100)) if total_l > 0 else 0
            pct_str = f"{pct_val}%".rjust(4) 
            
            am = f"[S:{self.scroll_speed}]  " if self.auto_scroll else ""
            lang_label = self.tr('ui_lang_name')
            right_t = f"{am}[{f_mode}] {pct_str}  {lang_label} "

            # --- 2. РИСУЕМ ---
            self.screen.attron(curses.color_pair(5))
            self.screen.move(r - 1, 0)
            self.screen.clrtoeol()
            
            # Заливка фона строки
            self.screen.addstr(r - 1, 0, " " * (c - 1))

            # Лево (Ширина + Метка закладок)
            if c > 10:
                self.screen.addstr(r - 1, 1, left_t[:c-2])
            
            # Центр (Название файла)
            if c > len(mid_t) + 20:
                start_x = (c - len(mid_t)) // 2
                self.screen.addstr(r - 1, start_x, mid_t)
                
            # Право (Режим, Проценты, Язык)
            if c > len(right_t) + 5:
                self.screen.insstr(r - 1, c - len(right_t), right_t)

            self.screen.attroff(curses.color_pair(5))
        except: pass

    def run(self):
        self.screen.nodelay(True)
        self.screen.keypad(True)
        curses.curs_set(0)
        last_r, last_c = self.screen.getmaxyx()
        while True:
            r, c = self.screen.getmaxyx()
            if (r, c) != (last_r, last_c):
                self.prepare_lines()
                last_r, last_c = r, c
            if self.auto_scroll:
                if time.time() - self.last_auto_time >= 5 / self.scroll_speed:
                    self.par_index = min(len(self.lines)-1, self.par_index + 1)
                    self.last_auto_time = time.time()
            self.redraw_scr()
            ch = self.screen.getch()
            if ch == -1:
                time.sleep(0.01); continue
            if ch in [ord('.'), 1102]: ch = ord('/')

            elif ch == ord('K'): 
                # Находим текущий язык в списке доступных
                try:
                    curr_idx = self.available_langs.index(self.lang_code)
                except ValueError:
                    curr_idx = 0
                
                # Берем следующий по кругу
                next_idx = (curr_idx + 1) % len(self.available_langs)
                self.lang_code = self.available_langs[next_idx]
                
                # Загружаем и применяем
                self.load_lang(self.lang_code)
                self.prepare_lines()
                self.redraw_scr()
                continue # Сразу уходим на новый круг, чтобы не сработали другие кнопки

            # Остальное управление
            elif ch == ord('q'): 
                self.save_history()
                break
            elif ch == ord('/'): self.do_search()
            elif ch == ord('n'): self.find_next()
            elif ch == ord('N'): self.find_prev()
            elif ch == ord('h'): 
                self.show_help()
                continue
            elif ch == ord('i'):
                self.show_info()
            elif ch == ord('L'):
                self.show_library()
            elif ch == ord('t'): 
                self.show_toc()
                continue
            elif ch == ord('p'): 
                self.jump_to_pct()
                continue
            elif ch == ord('e'):
                self.flip_mode = (self.flip_mode + 1) % 4
            
            elif ch == ord('m'):
                # Берем текст из кортежа (тип, текст) -> line[1]
                line_data = self.lines[self.par_index]
                text_content = line_data[1] if isinstance(line_data, tuple) else str(line_data)
                
                curr_text = text_content[:30].strip() + "..." if text_content else "..."
                self.bookmarks.append({"pos": self.par_index, "text": curr_text})
                self.save_history()

            elif ch == ord('M'):
                # Открыть список закладок
                if self.bookmarks:
                    self.show_bookmarks()
            
            elif ch == ord('f'):
                self.open_footnote()

            # Управление автоскроллом
            elif ch == ord('a'):
                self.auto_scroll = not self.auto_scroll
                self.last_auto_time = time.time()
            elif ch == ord('s') and self.auto_scroll: self.scroll_speed = min(10, self.scroll_speed + 1)
            elif ch == ord('S') and self.auto_scroll: self.scroll_speed = max(1, self.scroll_speed - 1)
            
            # Навигация
            elif ch in [ord('j'), curses.KEY_DOWN]: self.par_index = min(len(self.lines)-1, self.par_index + 1)
            elif ch in [ord('k'), curses.KEY_UP]: self.par_index = max(0, self.par_index - 1)

            elif ch in [ord(' '), curses.KEY_NPAGE, curses.KEY_RIGHT]: 
                r, c = self.screen.getmaxyx()
                d_h = r - 3 if self.show_border == 2 else (r - 2 if self.show_border == 1 else r - 1)

                if self.flip_mode == 0: # 1 режим: МГНОВЕННО
                    self.par_index = min(len(self.lines)-1, self.par_index + d_h)
                else: # 2 и 3 режимы: через функцию анимации
                    if self.par_index < len(self.lines) - d_h:
                        self.animate_flip(1)

            elif ch in [curses.KEY_PPAGE, curses.KEY_LEFT]: 
                r, c = self.screen.getmaxyx()
                d_h = r - 3 if self.show_border == 2 else (r - 2 if self.show_border == 1 else r - 1)

                if self.flip_mode == 0: # 1 режим: МГНОВЕННО
                    self.par_index = max(0, self.par_index - d_h)
                else: # 2 и 3 режимы
                    if self.par_index > 0:
                        self.animate_flip(-1)

            elif ch == curses.KEY_HOME or ch == ord('g'): self.par_index = 0
            elif ch == curses.KEY_END or ch == ord('G'):
                r, c = self.screen.getmaxyx()
                # Вычисляем чистую высоту текстового поля (как в redraw_scr)
                if self.show_border == 2:   d_h = r - 3
                elif self.show_border == 1: d_h = r - 2
                else:                       d_h = r - 1
                self.par_index = max(0, len(self.lines) - d_h)
            elif ch == ord('d'): self.par_index = min(len(self.lines)-1, self.par_index + (r-2)//2)
            elif ch == ord('u'): self.par_index = max(0, self.par_index - (r-2)//2)
            elif ch == ord('['): self.jump_chapter(-1)
            elif ch == ord(']'): self.jump_chapter(1)  
            elif ch == ord('Z'): # Заглавная Z
                self.scan_directory() 
            
            # Настройки
            elif ch == ord('='): self.width = min(c-10, self.width+4); self.prepare_lines()
            elif ch == ord('-'): self.width = max(20, self.width-4); self.prepare_lines()
            elif ch == ord('c'): 
                self.fg = (self.fg + 1) % 8
                if self.fg == self.bg: # Если совпало с фоном — прыгаем дальше
                    self.fg = (self.fg + 1) % 8
                self.update_colors()

            elif ch == ord('B'):
                # Переключаем 0 -> 1 -> 2 -> 0
                self.show_border = (self.show_border + 1) % 3
                self.prepare_lines()
                
            elif ch == ord('b'): 
                self.bg = (self.bg + 1) % 8
                # Если фон стал как текст или как заголовки — прыгаем дальше
                while self.bg == self.fg or self.bg == self.head_color:
                    self.bg = (self.bg + 1) % 8
                self.update_colors()
                
            elif ch == ord('v'):
                self.head_color = (self.head_color + 1) % 8
                if self.head_color == self.bg: # Если заголовок совпал с фоном
                    self.head_color = (self.head_color + 1) % 8
                self.update_colors()
            
            if ch != -1 and ch not in [ord('n'), ord('N'), ord('/'), ord('f'), -1]:
                self.search_query = ""

            # Выключение автоскролла при любой активности, кроме кнопок скорости
            if self.auto_scroll and ch not in [ord('a'), ord('s'), ord('S'), -1]:
                self.auto_scroll = False
def main():
    import sys, curses, os, json, argparse
    from fb2less_lib.reader import MainWindow

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('-v', '--version', action='store_true')
    parser.add_argument('filename', nargs='?')
    args = parser.parse_args()

    # --- ЗАГРУЗКА ЯЗЫКА ДЛЯ КОНСОЛИ ---
    # Пытаемся понять, какой язык был последним, чтобы выдать справку на нем
    history_path = os.path.expanduser("~/.fb2less_history")
    lang_code = "ru" # по умолчанию
    if os.path.exists(history_path):
        try:
            with open(history_path, "r") as f:
                data = json.load(f)
                # Берем язык из последней открытой книги
                latest = max(data.items(), key=lambda x: x[1].get('time', 0))
                lang_code = latest[1].get('lang', 'ru')
        except: pass

    # Загружаем JSON перевода вручную для main
    def get_msg(key, default):
        try:
            lp = os.path.join(os.path.dirname(__file__), 'fb2less_lib', 'locales', f'{lang_code}.json')
            with open(lp, 'r', encoding='utf-8') as f:
                return json.load(f).get(key, default)
        except: return default

    if args.version:
        print("fb2less version 7.0")
        return

    if args.help:
        # Используем локализацию даже в консоли!
        print(get_msg('cli_usage', "Usage: fb2less <file.fb2>"))
        print(f"\n{get_msg('cli_controls', 'Controls:')}")
        print(f"  h            - {get_msg('cli_help', 'help')}")
        print(f"  L            - {get_msg('cli_lib', 'library')}")
        print(f"  q            - {get_msg('cli_exit', 'exit')}")
        return

    filename = args.filename
    if not filename and os.path.exists(history_path):
        try:
            with open(history_path, "r") as f:
                data = json.load(f)
                if data:
                    filename = max(data.items(), key=lambda x: x[1].get('time', 0))[0]
        except: pass

    if filename:
        if not os.path.exists(filename):
            print(f"{get_msg('err_file_not_found', 'File not found')}: {filename}")
            return
        
        curses.wrapper(lambda stdscr: MainWindow(stdscr, filename))
    else:
        print(get_msg('cli_usage', "Usage: fb2less [FILE]"))
