import curses, os, json, time, re, textwrap
from .fb2_parser import fb2parse
from .layout import prepare_layout
from .txt_parser import txt_parse
from .epub_parser import epub_parse
from .storage import Storage
from . import dialogs

class MainWindow:
    def __init__(self, stdscr, filename):
        self.screen = stdscr
        # Используем новый класс для работы с данными
        self.storage = Storage(filename)
        self.filename = self.storage.filename
        
        # 1. ЗАГРУЗКА ДАННЫХ
        conf = self.storage.load_config()
        self.history_data = self.storage.load_full_history()
        hist = self.history_data.get(self.filename, {})

        # 2. НАСТРОЙКИ ИНТЕРФЕЙСА (из конфига)
        self.fg = conf.get("fg", 7)
        self.bg = conf.get("bg", 0)
        self.head_color = conf.get("hc", 6)
        self.width = conf.get("width", 100)
        self.scroll_speed = conf.get("speed", 3)
        self.show_border = conf.get("border", 0)
        self.flip_mode = conf.get("flip", 0)
        self.lang_code = conf.get("lang", "en")
        self.show_status = conf.get("status", 1)
        self.scan_path = conf.get("scan_path", os.getcwd())
        
        self.auto_scroll = False
        self.last_auto_time = time.time()
        
        # 3. ПРОГРЕСС КНИГИ
        self.par_index = hist.get("pos", 0)
        self.bookmarks = hist.get("bookmarks", [])
        if not isinstance(self.bookmarks, list): self.bookmarks = []
            
        # 4. ЛОКАЛИЗАЦИЯ
        locales_dir = os.path.join(os.path.dirname(__file__), 'locales')
        try:
            self.available_langs = sorted([f[:-5] for f in os.listdir(locales_dir) if f.endswith('.json')])
        except:
            self.available_langs = ['en', 'ru']

        if self.lang_code not in self.available_langs:
            self.lang_code = self.available_langs[0] if self.available_langs else 'en'
        self.load_lang(self.lang_code)
        
        # 5. ЗАГРУЗКА КОНТЕНТА
        self.reload_content()

        self.search_query = ""
        curses.start_color()
        curses.use_default_colors()
        self.update_colors()
        self.prepare_lines()
        self.run()

    def update_colors(self): 
        curses.init_pair(1, self.fg, self.bg)
        curses.init_pair(2, self.head_color, self.bg)
        curses.init_pair(3, self.bg, self.bg)
        curses.init_pair(4, -1, -1)
        curses.init_pair(5, self.bg, self.fg)

    def load_lang(self, lang_code):
        self.lang_code = lang_code
        path = os.path.join(os.path.dirname(__file__), 'locales', f'{lang_code}.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
        except: self.translations = {}

    def tr(self, key):
        return self.translations.get(key, key)

    def save_history(self):
        # 1. Принудительно обновляем путь перед сохранением
        self.storage.filename = self.filename 
        
        config_data = {
            "fg": self.fg, "bg": self.bg, "hc": self.head_color,
            "width": self.width, "speed": self.scroll_speed,
            "border": self.show_border, "flip": self.flip_mode,
            "lang": self.lang_code, 
            "status": 1 if self.show_status else 0,
            "scan_path": getattr(self, 'scan_path', os.getcwd())
        }
        
        book_info = {
            "pos": self.par_index,
            "bookmarks": self.bookmarks,
            "title": self.content.meta.get('title', self.tr('meta_unknown_title')),
            "author": self.content.meta.get('author', self.tr('meta_unknown')),
            "series": self.content.meta.get('series', ''),
            "time": time.time() # Это важно для автооткрытия последней книги
        }
        
        self.storage.save_all(config_data, self.history_data, book_info)

    def reload_content(self):
        ext = self.filename.lower()
        if ext.endswith('.txt'):
            self.content = txt_parse(self.filename, self.tr('meta_unknown'))
        elif ext.endswith('.epub'):
            self.content = epub_parse(self.filename, self.tr('meta_unknown'), self.tr('meta_error'))
        else:
            self.content = fb2parse(self.filename, self.tr('meta_unknown_title'), self.tr('meta_unknown'))
        
        self.notes = getattr(self.content, 'notes', {})
        if not self.content.paragraphs:
            self.content.paragraphs = [('body', self.tr('err_empty_file'))]

    def prepare_lines(self):
        r, c = self.screen.getmaxyx()
        border_space = 2 if self.show_border > 0 else 0
        w = min(c - border_space - 4, self.width)
        self.lines, self.toc = prepare_layout(
            self.content.paragraphs, w, 
            self.content.meta.get('author', ''),
            notes=self.notes, notes_label=self.tr('ui_notes_section')
        )

    def jump_chapter(self, direction):
        if not self.toc: return
        
        # Получаем только индексы строк из оглавления
        chapter_indices = sorted([item[1] for item in self.toc])
        
        if direction > 0:
            # Ищем первую главу, индекс которой больше текущего
            for idx in chapter_indices:
                if idx > self.par_index:
                    self.par_index = idx
                    return
        else:
            for idx in reversed(chapter_indices):
                if idx < self.par_index - 1:
                    self.par_index = idx
                    return
            self.par_index = 0

    def find_next(self):
        if not self.search_query: return
        for i in range(self.par_index + 1, len(self.lines)):
            if self.search_query.lower() in self.lines[i][1].lower():
                self.par_index = i; return

    def animate_flip(self, direction):
        r, c = self.screen.getmaxyx()
        d_h = r - (3 if self.show_border == 2 else (2 if self.show_border == 1 else 1))
        
        # Границы листа для анимации
        avail_c = c - (4 if self.show_border == 2 else 2)
        w_curr = min(avail_c - 4, self.width)
        margin = (c - w_curr) // 2
        x_l = (0 if self.show_border == 1 else margin - 2) + 1
        x_r = (c - 1 if self.show_border == 1 else margin + w_curr + 1)
        y_t, y_b = 1, r - 2
        
        width = x_r - x_l
        step = max(1, width // 20)

        # ФАЗА 1: Уход (для режимов 1, 3, 4 медленно, для 2 - мгновенно)
        if self.flip_mode in [1, 3, 4]:
            rng = range(x_r-1, x_l-step, -step) if direction > 0 else range(x_l, x_r+step, step)
            for x in rng:
                for cx in range(x, x+step if direction > 0 else x-step, 1 if direction > 0 else -1):
                    if x_l <= cx < x_r: self.screen.vline(y_t, cx, ord(' ')|curses.color_pair(3), y_b-y_t)
                self.screen.refresh(); time.sleep(0.01)
        elif self.flip_mode == 2:
            for x in range(x_l, x_r): self.screen.vline(y_t, x, ord(' ')|curses.color_pair(3), y_b-y_t)
            self.screen.refresh()

        self.par_index = max(0, min(len(self.lines)-1, self.par_index + (d_h if direction > 0 else -d_h)))

        # ФАЗА 2: Появление
        if self.flip_mode in [2, 3, 4]:
            for x in (range(x_r-1, x_l-step, -step) if (self.flip_mode in [2,3] and direction > 0) or (self.flip_mode==4 and direction < 0) else range(x_l, x_r+step, step)):
                self.redraw_scr()
                cov_rng = range(x_l, x) if (self.flip_mode in [2,3] and direction > 0) or (self.flip_mode==4 and direction < 0) else range(x, x_r)
                for cx in cov_rng: self.screen.vline(y_t, cx, ord(' ')|curses.color_pair(3), y_b-y_t)
                self.screen.refresh(); time.sleep(0.01 if self.flip_mode != 2 else 0.02)
        else: self.redraw_scr()

    def redraw_scr(self):
        r, c = self.screen.getmaxyx()
        f_off = 1 if self.show_status else 0
        
        # 1. Расчет высоты
        if self.show_border == 2:
            t_off, d_h, y_b = 1, r - 2 - f_off, r - 1 - f_off
        elif self.show_border == 1:
            t_off, d_h, y_b = 1, r - 1 - f_off, r - 1 - f_off
        else:
            t_off, d_h, y_b = 0, r - f_off, r - f_off

        # 2. Расчет ширины листа и границ заливки
        avail_c = c - (4 if self.show_border == 2 else (2 if self.show_border == 1 else 0))
        w_curr = min(avail_c - 4, self.width)
        margin = (c - w_curr) // 2
        
        # Если рамок нет (0) или рамка по окну (1) — заливаем весь экран
        if self.show_border in [0, 1]:
            x_l, x_r = 0, c - 1
        else:
            x_l, x_r = margin - 2, margin + w_curr + 1

        # 3. Очистка подложки
        self.screen.bkgd(" ", curses.color_pair(4))
        self.screen.erase()

        # 4. Заливка цветом листа
        for y in range(0, y_b + (1 if self.show_border == 0 else 0)):
            try:
                self.screen.addstr(y, x_l, " " * (x_r - x_l + 1), curses.color_pair(1))
            except: pass

        # 5. Отрисовка рамок
        if self.show_border > 0:
            self.screen.attron(curses.color_pair(1))
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

        # 6. Отрисовка текста
        for i in range(d_h):
            idx = self.par_index + i
            if idx < len(self.lines):
                y_pos = i + t_off
                if y_pos >= y_b and self.show_border > 0: break
                
                p_type, text = self.lines[idx]
                attr = curses.color_pair(2 if p_type == "title" else 1)
                
                try:
                    if p_type == "title":
                        self.screen.addstr(y_pos, (c - len(text)) // 2, text[:c-2], attr | curses.A_BOLD)
                    else:
                        # 1. Рисуем основной текст строки
                        self.screen.addstr(y_pos, margin, text[:w_curr], attr)
                        
                        # 2. ПОДСВЕТКА СНОСОК
                        for m in re.finditer(r'\[(.*?)\]', text[:w_curr]):
                            self.screen.addstr(y_pos, margin + m.start(), m.group(0), curses.color_pair(2) | curses.A_BOLD)
                            
                        # 3. ПОДСВЕТКА ПОИСКА
                        if self.search_query:
                            # Ищем все вхождения поискового запроса (без учета регистра)
                            for m in re.finditer(re.escape(self.search_query), text[:w_curr], re.IGNORECASE):
                                start_x = m.start()
                                word = text[start_x : start_x + len(self.search_query)]
                                # Красим в инвертированный цвет заголовка (или любой другой заметный)
                                self.screen.addstr(y_pos, margin + start_x, word, curses.color_pair(2) | curses.A_REVERSE)
                except: pass
        
        # 7. Рисуем статус-бар (если включен)
        self.draw_status(r, c)

    def draw_status(self, r, c):
        if not self.show_status: return
        try:
            # 1. Индикатор закладок
            bm = " [M]" if self.bookmarks else ""
            left = f"|==|:{self.width}{bm}"
            
            # 2. Индикатор автоскролла [S:x]
            am_indicator = f"[S:{self.scroll_speed}] " if self.auto_scroll else ""
            
            mid = f"{os.path.basename(self.filename)} [{self.content.encoding}]"
            
            # 3. ФИКСИРОВАННЫЕ ПРОЦЕНТЫ
            # Используем rjust(4), чтобы под "100%" всегда было 4 символа (три цифры + %)
            total = len(self.lines)
            pct_val = min(100, int(((self.par_index + r) / total) * 100)) if total > 0 else 0
            pct_str = f"{pct_val}%".rjust(4) 
            
            bar = f"[{'█'*(pct_val//10)}{' '*(10-(pct_val//10))}] {pct_str}"
            
            mode_names = self.tr('ui_mode_names')
            f_mode = mode_names[self.flip_mode] if isinstance(mode_names, list) else "STD"
            
            # Собираем правую часть: [Скорость] [Режим] [Бар Проценты] Язык
            right = f"{am_indicator}[{f_mode}] {bar}  {self.tr('ui_lang_name')} "

            # РИСОВАНИЕ
            self.screen.attron(curses.color_pair(5))
            self.screen.move(r - 1, 0)
            self.screen.clrtoeol()
            self.screen.addstr(r - 1, 0, " " * (c - 1)) # Заливка всей строки

            if c > 10:
                self.screen.addstr(r - 1, 1, left[:c-2])
            if c > len(mid) + len(right) + 20:
                self.screen.addstr(r - 1, (c - len(mid)) // 2, mid)
            if c > len(right) + 5:
                # Печатаем правую часть с конца
                self.screen.addstr(r - 1, c - len(right), right)
            self.screen.attroff(curses.color_pair(5))
        except: pass
        self.screen.refresh()

    def run(self):
        self.screen.nodelay(True)
        self.screen.keypad(True)
        curses.curs_set(0)
        last_size = None

        while True:
            r, c = self.screen.getmaxyx()
            size = self.screen.getmaxyx()
            if size != last_size:
                self.prepare_lines()
                last_size = size
            
            if self.auto_scroll and time.time() - self.last_auto_time >= 5 / self.scroll_speed:
                self.par_index = min(len(self.lines)-1, self.par_index + 1)
                self.last_auto_time = time.time()

            self.redraw_scr()
            
            ch = self.screen.getch()
            if ch == -1: 
                time.sleep(0.01)
                continue

            # 1. СИСТЕМНЫЕ (Выход, Настройки, Раскладка)
            if ch in [ord('q'), 1081]: # q или й
                if self.search_query:
                    self.search_query = ""
                    continue
                self.save_history()
                break

            elif ch in [ord('o'), 1097]: # o или щ
                dialogs.show_settings(self)
                curses.flushinp()
                while self.screen.getch() != -1: pass
                continue 

            if ch in [ord('.'), 1102, 44]: ch = ord('/')
            if ch in [ord('['), 1093]: ch = ord('[')
            if ch in [ord(']'), 1098]: ch = ord(']')

            # 2. ДИАЛОГИ И ИНФО
            if ch == ord('h'): dialogs.show_help(self)
            elif ch == ord('i'): dialogs.show_info(self)
            elif ch == ord('L'): 
                dialogs.show_library(self)
                continue
            elif ch == ord('t'): dialogs.show_toc(self)
            elif ch == ord('M'): dialogs.show_bookmarks(self)
            elif ch == ord('Z'): self.storage.scan_directory(self)

            # 3. ПОИСК, СНОСКИ, ЗАКЛАДКИ
            elif ch == ord('/'): self.do_search()
            elif ch == ord('n'): self.find_next()
            elif ch == ord('N'): self.find_prev()
            elif ch == ord('f'): self.open_footnote()
            elif ch == ord('m'):
                line_data = self.lines[self.par_index]
                text = line_data[1] if isinstance(line_data, tuple) else str(line_data)
                self.bookmarks.append({"pos": self.par_index, "text": text[:30].strip() + "..."})
                self.save_history()

            # 4. НАВИГАЦИЯ (Стрелки, j/k, Home/End)
            elif ch in [ord('j'), curses.KEY_DOWN]: 
                self.par_index = min(len(self.lines)-1, self.par_index + 1)
            elif ch in [ord('k'), curses.KEY_UP]: 
                self.par_index = max(0, self.par_index - 1)
            elif ch == curses.KEY_HOME or ch == ord('g'): 
                self.par_index = 0
            elif ch == curses.KEY_END or ch == ord('G'):
                r, c = self.screen.getmaxyx()
                d_h = r - (3 if self.show_border == 2 else (2 if self.show_border == 1 else 1))
                self.par_index = max(0, len(self.lines) - d_h)
            elif ch == ord('['): self.jump_chapter(-1)
            elif ch == ord(']'): self.jump_chapter(1)

            # 5. ПОСТРАНИЧНОЕ ЛИСТАНИЕ (с анимацией)
            elif ch in [ord(' '), curses.KEY_NPAGE, curses.KEY_RIGHT]: 
                r, c = self.screen.getmaxyx()
                d_h = r - (3 if self.show_border == 2 else (2 if self.show_border == 1 else 1))
                if self.flip_mode == 0: 
                    self.par_index = min(len(self.lines)-1, self.par_index + d_h)
                elif self.par_index < len(self.lines) - d_h:
                    self.animate_flip(1)
            elif ch == ord('d'): # Пол-экрана вперед
                self.par_index = min(len(self.lines)-1, self.par_index + (r-2)//2)
            elif ch == ord('u'): # Пол-экрана назад
                self.par_index = max(0, self.par_index - (r-2)//2)

            elif ch in [curses.KEY_PPAGE, curses.KEY_LEFT]: 
                r, c = self.screen.getmaxyx()
                d_h = r - (3 if self.show_border == 2 else (2 if self.show_border == 1 else 1))
                if self.flip_mode == 0: 
                    self.par_index = max(0, self.par_index - d_h)
                elif self.par_index > 0:
                    self.animate_flip(-1)

            # 6. ГОРЯЧИЕ КЛАВИШИ ВИДА И АВТОСКРОЛЛА
            elif ch == ord('a'): 
                self.auto_scroll = not self.auto_scroll
                self.last_auto_time = time.time()
                self.redraw_scr()
            elif ch == ord('s') and self.auto_scroll: self.scroll_speed = min(10, self.scroll_speed + 1)
            elif ch == ord('S') and self.auto_scroll: self.scroll_speed = max(1, self.scroll_speed - 1)
            elif ch == ord('c'): self.fg = (self.fg + 1) % 8; self.update_colors()
            elif ch == ord('b'): self.bg = (self.bg + 1) % 8; self.update_colors()
            elif ch == ord('v'): self.head_color = (self.head_color + 1) % 8; self.update_colors()
            elif ch == ord('B'): self.show_border = (self.show_border + 1) % 3; self.prepare_lines()
            elif ch == ord('e'): self.flip_mode = (self.flip_mode + 1) % 5
            elif ch == ord('='): self.width = min(c-10, self.width+4); self.prepare_lines()
            elif ch == ord('-'): self.width = max(20, self.width-4); self.prepare_lines()

            # --- Смена языка (K) ---
            elif ch == ord('K'):
                idx = self.available_langs.index(self.lang_code)
                self.lang_code = self.available_langs[(idx + 1) % len(self.available_langs)]
                self.load_lang(self.lang_code)
                self.prepare_lines()

                # ИСПРАВЛЕНИЕ: Стираем 5 символов в самом углу перед отрисовкой
                r, c = self.screen.getmaxyx()
                try:
                    # Затираем место, где написано 'En' или 'Ru'
                    self.screen.addstr(r - 1, c - 6, "     ", curses.color_pair(5))
                    self.screen.refresh() # Принудительно выводим "пустоту"
                except: pass

                self.redraw_scr()

            # --- Скрыть/показать бар (H) ---
            elif ch == ord('H'):
                self.show_status = not self.show_status
                self.prepare_lines()
                self.screen.erase()
                self.redraw_scr()

            # --- Переход на процент (p) ---
            elif ch == ord('P'):
                self.jump_to_pct()

            # Сброс поиска при любом другом действии
            if ch != -1 and ch not in [ord('n'), ord('N'), ord('/'), ord('f')]:
                # Если поиск активен и нажата 'q', мы просто гасим поиск, 
                # но не выходим из программы сразу
                if self.search_query and ch == ord('q'):
                    self.search_query = ""
                    continue # Пропускаем стандартную обработку 'q' (выход)
                self.search_query = ""

    def do_search(self):
        self.screen.nodelay(False)
        r, c = self.screen.getmaxyx()
        prompt = "/ "
        self.screen.attron(curses.color_pair(5))
        self.screen.move(r - 1, 0)
        self.screen.clrtoeol()
        self.screen.addstr(r - 1, 0, (prompt + " " * (c - len(prompt) - 1))[:c-1])
        
        curses.echo(); curses.curs_set(1)
        try:
            raw = self.screen.getstr(r - 1, len(prompt))
            res = raw.decode('utf-8', errors='replace').strip()
            if res: 
                self.search_query = res
                self.find_next()
        except: pass
        curses.noecho(); curses.curs_set(0); self.screen.nodelay(True)

    def find_prev(self):
        if not self.search_query: return
        for i in range(self.par_index - 1, -1, -1):
            if self.search_query.lower() in self.lines[i][1].lower():
                self.par_index = i; return

    def jump_to_pct(self):
        self.screen.nodelay(False)
        r, c = self.screen.getmaxyx()
        prompt = self.tr('ui_jump_to')
        
        self.screen.attron(curses.color_pair(5))
        self.screen.move(r - 1, 0)
        self.screen.clrtoeol()
        self.screen.addstr(r - 1, 0, (prompt + " " * (c - len(prompt) - 1))[:c-1])
        
        curses.echo()
        try:
            raw = self.screen.getstr(r - 1, len(prompt))
            val = int(raw.decode('utf-8'))
            if 0 <= val <= 100:
                # Пересчитываем индекс строки исходя из процента
                self.par_index = int((len(self.lines) - 1) * (val / 100.0))
        except: pass
        
        curses.noecho()
        self.screen.nodelay(True)
        self.redraw_scr()

    def open_footnote(self):
        r, c = self.screen.getmaxyx()
        d_h = r - (3 if self.show_border == 2 else (2 if self.show_border == 1 else 1))
        visible_notes = []
        for i in range(d_h):
            idx = self.par_index + i
            if idx < len(self.lines):
                line_text = self.lines[idx][1]
                m = re.findall(r'\[(.*?)\]', line_text)
                for note_id in m:
                    if (note_id in self.notes or any(note_id in k for k in self.notes)) and note_id not in visible_notes:
                        visible_notes.append(note_id)
        if not visible_notes: return
        
        if not hasattr(self, 'last_note_idx'): self.last_note_idx = -1
        self.last_note_idx = (self.last_note_idx + 1) % len(visible_notes)
        self.show_note(visible_notes[self.last_note_idx])

    def show_note(self, note_label):
        note_text = self.notes.get(note_label)
        if not note_text:
            digits = "".join(filter(str.isdigit, note_label))
            for k, v in self.notes.items():
                if digits and "".join(filter(str.isdigit, k)) == digits:
                    note_text = v; break
        if not note_text: return

        r, c = self.screen.getmaxyx()
        max_w = min(c - 6, 70)
        wrapped = textwrap.wrap(note_text, width=max_w - 4)
        h = min(r - 4, len(wrapped) + 2)
        y, x = (r - h) // 2, (c - max_w) // 2
        
        try:
            nw = curses.newwin(h, max_w, y, x)
            nw.bkgd(" ", curses.color_pair(1)); nw.box()
            nw.addstr(0, 2, f" {self.tr('ui_note_title')} ", curses.A_BOLD)
            for i, line in enumerate(wrapped[:h-2]):
                nw.addstr(i + 1, 2, line)
            nw.refresh(); nw.getch()
        except: pass
        self.redraw_scr()

def main():
    import sys, curses, os, json, argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('-v', '--version', action='store_true')
    parser.add_argument('filename', nargs='?')
    args = parser.parse_args()

    config_dir = os.path.expanduser("~/.config/fb2less")
    history_path = os.path.join(config_dir, "history.json")

    if args.version:
        print("fb2less version 0.9.5")
        return

    if args.help:
        print("Usage: fb2less [FILE]")
        print("\nControls:")
        print("  h            - Help screen")
        print("  o            - Settings menu")
        print("  L            - Library")
        print("  Z            - Scan directory")
        print("  q            - Exit")
        return

    filename = args.filename
    
    # Авто-поиск последней книги, если аргумент не передан
    if not filename and os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                # Фильтруем только книги и берем путь самой свежей
                books = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('time')}
                if books:
                    # Находим ключ (путь) книги с максимальным временем
                    filename = max(books.items(), key=lambda x: x[1]['time'])[0]
        except Exception:
            pass

    if filename:
        full_path = os.path.abspath(os.path.expanduser(filename))
        if not os.path.exists(full_path):
            print(f"Error: File not found - {full_path}")
            return
        
        # Запускаем MainWindow (он находится в этом же файле, импорт не нужен)
        curses.wrapper(lambda stdscr: MainWindow(stdscr, full_path))
    else:
        print("Usage: fb2less [FILE]")
        print("Hint: Open the library (L) or scan a folder (Z) to add books.")

if __name__ == "__main__":
    main()
