import curses, os, json, time, re, textwrap, threading
from .fb2_parser import fb2parse
from .layout import prepare_layout
from .txt_parser import txt_parse
from .epub_parser import epub_parse
from .storage import Storage
from . import dialogs

class MainWindow:
    def __init__(self, stdscr, filename):
        self.screen = stdscr
        self.storage = Storage(filename)
        self.filename = self.storage.filename
        self.voice_active = False
        
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
        self.show_version = conf.get("show_version", 1)
        self.scan_path = conf.get("scan_path", os.getcwd())
        self.tts_proc = None
        
        self.auto_scroll = False
        self.last_auto_time = time.time()

        self.current_engine = conf.get("current_engine", "spd-say")
        self.current_voice = conf.get("current_voice", "rhvoice")
        self.voice_speed = conf.get("voice_speed", 100)
        
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
        self._cached_width = None
        self._cached_lines = None
        self._cached_toc = None
        self._last_parsed_filename = None
        self._last_parsed_content = None
        self._footnote_re = re.compile(r'\[(.*?)\]')
        self._search_re = None
        self.reload_content()

        self.search_query = ""
        curses.start_color()
        curses.use_default_colors()
        self.update_colors()
        self.prepare_lines()
        self.run()

    @property
    def border_padding(self):
        """Возвращает вертикальный отступ в зависимости от стиля рамки"""
        if self.show_border == 2:
            return 3
        elif self.show_border == 1:
            return 2
        return 1

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
            "voice_speed": getattr(self, 'voice_speed', 100),
            "tts_lang": getattr(self, 'tts_lang', 'ru'),
            "scan_path": getattr(self, 'scan_path', os.getcwd()),
            "current_engine": getattr(self, 'current_engine', 'spd-say'),
            "current_voice": getattr(self, 'current_voice', 'rhvoice')
        }
        
        def clean_meta(text):
            if not text: 
                return ""
            # Кодируем в utf-8 и декодируем с заменой невалидных символов, гарантируя валидный JSON
            return str(text).encode('utf-8', errors='ignore').decode('utf-8', errors='replace')

        book_info = {
            "pos": self.par_index,
            "bookmarks": self.bookmarks,
            "title": clean_meta(self.content.meta.get('title', self.tr('meta_unknown_title'))),
            "author": clean_meta(self.content.meta.get('author', self.tr('meta_unknown'))),
            "series": clean_meta(self.content.meta.get('series', '')),
            "time": time.time() # Это важно для автооткрытия последней книги
        }
        
        self.storage.save_all(config_data, self.history_data, book_info)

    def reload_content(self):
        import os
        if not self.filename or not os.path.exists(self.filename):
            return

        # Сбрасываем кэш разметки экрана при открытии любой книги
        self._cached_width = None
        self._cached_lines = None
        self._cached_toc = None

        file_size_mb = os.path.getsize(self.filename) / (1024 * 1024)
        if file_size_mb > 25: 
            try:
                self.screen.attron(curses.color_pair(2))
                r, c = self.screen.getmaxyx()
                msg = f"! Warning: Large file ({file_size_mb:.1f} MB), parsing may take a moment... !"
                self.screen.addstr(r - 1, 0, msg[:c-1].center(c-1))
                self.screen.refresh()
            except: pass

        if getattr(self, '_last_parsed_filename', None) == self.filename and getattr(self, '_last_parsed_content', None) is not None:
            self.content = self._last_parsed_content
            self.notes = getattr(self.content, 'notes', {})
            return

        # Нативный парсинг в зависимости от расширения файла
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

        # Сохраняем успешно распарсенный контент в глобальный кэш
        self._last_parsed_filename = self.filename
        self._last_parsed_content = self.content

    def prepare_lines(self, force=False):
        r, c = self.screen.getmaxyx()
        border_space = 2 if self.show_border > 0 else 0
        w = min(c - border_space - 4, self.width)
        
        if not force and getattr(self, '_cached_width', None) == w and getattr(self, '_cached_lines', None) is not None:
            self.lines = self._cached_lines
            self.toc = self._cached_toc
            return

        self.lines, self.toc = prepare_layout(
            self.content.paragraphs, w, 
            self.content.meta.get('author', ''),
            notes=self.notes, notes_label=self.tr('ui_notes_section')
        )
        
        self._cached_width = w
        self._cached_lines = self.lines
        self._cached_toc = self.toc

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
        f_off = 1 if self.show_status else 0
        
        # Математически точный расчет высоты текстового поля для анимации
        if self.show_border == 2:
            t_off, d_h, y_b = 1, r - 3 - f_off, r - 1 - f_off
        elif self.show_border == 1:
            t_off, d_h, y_b = 1, r - 2 - f_off, r - 1 - f_off
        else:
            t_off, d_h, y_b = 0, r - f_off, r - f_off
            
        y_t = t_off
        
        # Полная синхронизация расчета ширины и margin с методом prepare_lines
        border_space = 2 if self.show_border > 0 else 0
        w_curr = min(c - border_space - 4, self.width)
        margin = (c - w_curr) // 2
        
        # Границы стирания старой страницы
        if self.show_border == 0:
            x_l, x_r = 0, c
        elif self.show_border == 1:
            x_l, x_r = 1, c - 1
        else:
            x_l, x_r = margin - 1, margin + w_curr + 1
            
        width = x_r - x_l
        step = max(1, width // 20)

        # ФАЗА 1: Уход старой страницы (В виртуальный буфер, без мерцания)
        if self.flip_mode in [1, 3, 4]: 
            rng = range(x_r-1, x_l-step, -step) if direction > 0 else range(x_l, x_r+step, step)
            for x in rng:
                for cx in range(x, x+step if direction > 0 else x-step, 1 if direction > 0 else -1):
                    if x_l <= cx < x_r: 
                        self.screen.vline(y_t, cx, ord(' ')|curses.color_pair(3), y_b-y_t)
                self.screen.noutrefresh()
                curses.doupdate()
                time.sleep(0.01)
        elif self.flip_mode == 2:
            for x in range(x_l, x_r): 
                self.screen.vline(y_t, x, ord(' ')|curses.color_pair(3), y_b-y_t)
            self.screen.noutrefresh()
            curses.doupdate()

        # Переключаем индекс страницы в памяти
        self.par_index = max(0, min(len(self.lines)-1, self.par_index + (d_h if direction > 0 else -d_h)))

        # ФАЗА 2: Появление новой страницы
        if self.flip_mode in [2, 3, 4]: 
            try:
                # Создаем временное виртуальное окно размером во весь экран
                v_win = curses.newwin(r, c, 0, 0)
                
                # Подменяем окно приложения на виртуальное, чтобы redraw_scr нарисовал всё туда
                orig_screen = self.screen
                self.screen = v_win
                self.redraw_scr()
                self.screen = orig_screen
                
                # Цикл анимации: шторка открывает готовую страницу из ОЗУ
                for x in (range(x_r-1, x_l-step, -step) if (self.flip_mode in [2, 3] and direction > 0) or (self.flip_mode==4 and direction < 0) else range(x_l, x_r+step, step)):
                    
                    # ТВОЯ РОДНАЯ СКОРОСТЬ: Мгновенно копируем страницу на реальный экран
                    v_win.overwrite(self.screen)
                    
                    # Накладываем поверх шторку черноты на нераскрытую часть
                    cov_rng = range(x_l, x) if (self.flip_mode in [2, 3] and direction > 0) or (self.flip_mode==4 and direction < 0) else range(x, x_r)
                    for cx in cov_rng: 
                        self.screen.vline(y_t, cx, ord(' ')|curses.color_pair(3), y_b-y_t)
                    
                    # ЖЕСТКАЯ СИНХРОНИЗАЦИЯ ДЛЯ TERMUX:
                    # noutrefresh гарантирует, что кадр уйдет на отрисовку ТОЛЬКО тогда,
                    # когда и overwrite, и все линии vline уже полностью нарисованы.
                    self.screen.noutrefresh()
                    curses.doupdate() # Атомарный вывод совмещенного кадра
                    
                    time.sleep(0.01 if self.flip_mode != 2 else 0.02)
                
                # Удаляем виртуальное окно из памяти
                del v_win
            except:
                pass
                
            # Окончательный чистый рендер страницы
            self.redraw_scr()
        else: 
            self.redraw_scr()

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
        # ИСПРАВЛЕНО: Защита Termux от мерцания фона при анимации шторки
        if not getattr(self, '_animating_now', False):
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

                # ОПРЕДЕЛЯЕМ ЦВЕТ
                is_reading = (getattr(self, 'voice_active', False) and idx == self.par_index)
                
                if is_reading:
                    attr = curses.color_pair(2) | curses.A_REVERSE | curses.A_BOLD
                else:
                    attr = curses.color_pair(2 if p_type == "title" else 1)
                
                try:
                    if p_type == "title":
                        self.screen.addstr(y_pos, (c - len(text)) // 2, text[:c-2], attr | curses.A_BOLD)
                    else:
                        # Рисуем основной текст строки
                        self.screen.addstr(y_pos, margin, text[:w_curr], attr)
                        
                        # 2. ПОДСВЕТКА СНОСОК (Оптимизировано через скомпилированную регулярку)
                        for m in self._footnote_re.finditer(text[:w_curr]):
                            self.screen.addstr(y_pos, margin + m.start(), m.group(0), curses.color_pair(2) | curses.A_BOLD)
                            
                        # 3. ПОДСВЕТКА ПОИСКА (Оптимизировано через скомпилированную регулярку)
                        if self._search_re:
                            for m in self._search_re.finditer(text[:w_curr]):
                                start_x = m.start()
                                word = m.group(0) 
                                self.screen.addstr(y_pos, margin + start_x, word, curses.color_pair(2) | curses.A_REVERSE)
                except: pass

        if self.show_border > 0:
            try:
                self.screen.attron(curses.color_pair(1))
                r_x = c - 1 if self.show_border == 1 else x_r
                l_x = 0 if self.show_border == 1 else x_l
                
                ver_str = " fb2less v1.0.6 "
                ver_x = r_x - len(ver_str) - 2  
                
                if ver_x > l_x + 2:
                    # ИСПРАВЛЕНО: Вернули проверку флага show_version
                    if bool(getattr(self, 'show_version', True)):
                        self.screen.addstr(0, ver_x, ver_str, curses.color_pair(1) | curses.A_BOLD)
                    else:
                        # Если флаг выключен — принудительно затираем текст сплошной линией рамки
                        self.screen.hline(0, ver_x, curses.ACS_HLINE, len(ver_str))
                        
                self.screen.attroff(curses.color_pair(1))
            except: pass
        
        # 7. Рисуем статус-бар (если включен)
        self.draw_status(r, c)

    def draw_status(self, r, c):
        if not self.show_status: return
        try:
            # 1. Индикаторы закладок и голоса
            bm = " [M]" if self.bookmarks else "    " 
            vs = " [V]" if getattr(self, 'voice_active', False) else "    "
            left = f"|==|:{str(self.width).ljust(3)}{bm}{vs}"
            
            # 2. Индикатор автоскролла [S:x]
            am_indicator = f"[S:{self.scroll_speed}] " if self.auto_scroll else ""
            
            mid = f"{os.path.basename(self.filename)} [{self.content.encoding}]"
            
            # 3. ИСПРАВЛЕНО: Безопасный расчет процентов без риска ZeroDivisionError
            total = len(self.lines)
            if total > 0:
                pct_val = min(100, int((self.par_index / total) * 100))
            else:
                pct_val = 0
                
            pct_str = f"{pct_val}%".rjust(4) 
            bar = f"[{'█'*(pct_val//10)}{' '*(10-(pct_val//10))}] {pct_str}"
            
            mode_names = self.tr('ui_mode_names')
            f_mode = mode_names[self.flip_mode] if isinstance(mode_names, list) else "STD"
            
            right = f"{am_indicator}[{f_mode}] {bar}  {self.tr('ui_lang_name')} "

            # РИСОВАНИЕ
            self.screen.attron(curses.color_pair(5))
            self.screen.move(r - 1, 0)
            self.screen.clrtoeol()
            self.screen.addstr(r - 1, 0, " " * (c - 1)) # Оставляем последнюю ячейку пустой!

            if c > 10:
                self.screen.addstr(r - 1, 1, left[:c-2])
            if c > len(mid) + len(right) + 20:
                self.screen.addstr(r - 1, (c - len(mid)) // 2, mid)
            if c > len(right) + 5:
                self.screen.addstr(r - 1, c - len(right), right)
            self.screen.attroff(curses.color_pair(5))
        except: pass
        self.screen.refresh()

    def _get_engines(self):
        """Возвращает список доступных в системе утилит TTS"""
        import shutil
        engines = []
        if shutil.which('spd-say'): engines.append('spd-say')
        if shutil.which('espeak-ng'): engines.append('espeak-ng')
        return engines

    def _get_voices(self, engine):
        """Правильный парсинг установленных голосов в Arch Linux"""
        import subprocess
        voices = []
        
        if engine == 'spd-say':
            try:
                res = subprocess.run(['spd-say', '-L'], capture_output=True, text=True, timeout=1)
                for line in res.stdout.splitlines():
                    if line.strip() and not line.startswith('NAME'):
                        parts = line.split()
                        if len(parts) >= 2:
                            # ID голоса, Отображаемое имя, Язык
                            voices.append((parts[0], f"spd: {parts[0]} ({parts[1]})", parts[1]))
            except: pass
            if not voices: voices.append(('rhvoice', 'RHVoice (По умолчанию)', 'ru'))
            
        elif engine == 'espeak-ng':
            try:
                res = subprocess.run(['espeak-ng', '--voices'], capture_output=True, text=True, timeout=1)
                for line in res.stdout.splitlines():
                    parts = line.split()
                    # Пропускаем заголовок таблицы espeak
                    if len(parts) >= 5 and not parts[0].startswith('Pty'):
                        lang = parts[1]
                        voice_id = parts[4] if '/' in parts[4] else parts[3]
                        voices.append((voice_id, f"espeak: {voice_id} ({lang})", lang))
            except: pass
            if not voices: voices.append(('ru', 'Espeak Ru (По умолчанию)', 'ru'))#Чтобы брал из бара, пока не убираю
            
        return voices

    def toggle_tts(self, stop=False):
        import subprocess, threading
        was_active = getattr(self, 'voice_active', False)
        self.voice_active = False 
        
        try:
            subprocess.run(['spd-say', '-S'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        
        if hasattr(self, 'tts_proc') and self.tts_proc:
            try:
                self.tts_proc.terminate()
                self.tts_proc.wait(timeout=0.2)
            except: pass
            self.tts_proc = None

        if stop or was_active:
            return 

        # Инициализируем дефолты, если их еще нет в конфиге
        if not hasattr(self, 'current_engine'): self.current_engine = 'spd-say'
        if not hasattr(self, 'current_voice'): self.current_voice = 'rhvoice'

        self.voice_active = True
        threading.Thread(target=self._tts_loop, daemon=True).start()

    def _tts_loop(self):
        import subprocess, re, time, curses
        while self.voice_active:
            if self.par_index >= len(self.lines):
                self.voice_active = False
                break
            
            p_type, text = self.lines[self.par_index]
            clean_text = re.sub(r'\[.*?\]', '', text).strip()
            
            if clean_text:
                try:
                    spd_val = int((self.voice_speed - 100) / 2) + 20
                    voice_id_str = self.current_voice[0] if isinstance(self.current_voice, (list, tuple)) else str(self.current_voice)

                    if self.current_engine == 'spd-say':
                        full_cmd = [
                            'spd-say', '-o', 'rhvoice', '-y', voice_id_str,
                            '-r', str(spd_val), '-t', 'text', '-w', clean_text
                        ]
                    elif self.current_engine == 'espeak-ng':
                        # ИСПРАВЛЕНО: возвращен расчет скорости, без которого espeak-ng падал с NameError
                        es_speed = int(175 * (self.voice_speed / 100.0))
                        full_cmd = [
                            'espeak-ng', '-v', voice_id_str, '-s', str(es_speed), clean_text
                        ]

                    self.tts_proc = subprocess.Popen(full_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    while self.tts_proc.poll() is None:
                        if not self.voice_active:
                            self.tts_proc.terminate()
                            return
                        time.sleep(0.01)
                except:
                    self.voice_active = False
                    break
            
            if self.voice_active:
                time.sleep(0.1)
                self.par_index += 1
                curses.ungetch(curses.KEY_RESIZE)

    def run(self):
        self.screen.nodelay(True)
        self.screen.keypad(True)
        curses.curs_set(0)
        last_size = None

        while True:
            # УБРАНО: Никаких блокирующих очередей tts_queue от ИИ - с его кодом не работает и он не знает почему!
            
            r, c = self.screen.getmaxyx()
            size = (r, c)
            
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

            elif ch in [ord('X'), 1063]:
                import random

                for _ in range(30):
                    r, c = self.screen.getmaxyx()

                    matrix_chars = "".join(random.choice("01$#@%&§?*+=[]{}") for _ in range(c - 1))
                    
                    self.screen.attron(curses.color_pair(5))
                    self.screen.move(r - 1, 0)
                    self.screen.clrtoeol()
                    # Выводим цифровой шум
                    self.screen.addstr(r - 1, 0, matrix_chars[:c-1])
                    
                    msg = " Follow the white rabbit... "
                    if c > len(msg) + 4:
                        self.screen.addstr(r - 1, (c - len(msg)) // 2, msg, curses.color_pair(5) | curses.A_BOLD)
                        
                    self.screen.attroff(curses.color_pair(5))
                    self.screen.refresh()
                    time.sleep(0.05) # Скорость бегущих символов
                
                self.redraw_scr()
                continue


            # 1. СИСТЕМНЫЕ
            if ch in [ord('q'), 1081]:
                if getattr(self, 'voice_active', False):
                    self.toggle_tts(stop=True)
                    self.redraw_scr()
                    continue
                if self.search_query:
                    self.search_query = ""
                    self.redraw_scr()
                    continue
                self.save_history()
                break

            elif ch in [ord('o'), 1097]:
                dialogs.show_settings(self)
                curses.flushinp()
                while self.screen.getch() != -1: pass
                continue 

            if ch in [ord('.'), 1102, 44]: ch = ord('/')
            if ch in [ord('['), 1093]: ch = ord('[')
            if ch in [ord(']'), 1098]: ch = ord(']')

            # 2. ДИАЛОГИ И ИНФО
            if ch == ord('h'): dialogs.show_help(self); continue
            elif ch == ord('i'): dialogs.show_info(self); continue
            elif ch == ord('L'): dialogs.show_library(self); continue
            elif ch == ord('t'): dialogs.show_toc(self); continue
            elif ch == ord('M'): dialogs.show_bookmarks(self); continue
            elif ch == ord('Z'): 
                self.storage.scan_directory(self)
                self.redraw_scr()
                continue

            # 3. ПОИСК, СНОСКИ, ЗАКЛАДКИ
            elif ch == ord('/'): self.do_search(); continue
            elif ch == ord('n'): self.find_next(); self.redraw_scr()
            elif ch == ord('N'): self.find_prev(); self.redraw_scr()
            elif ch == ord('f'): self.open_footnote(); continue

            elif ch == ord('V'): 
                self.toggle_tts()
                self.redraw_scr()

            elif ch == ord('m'):
                line_data = self.lines[self.par_index]
                text = line_data[1] if isinstance(line_data, tuple) else str(line_data)
                self.bookmarks.append({"pos": self.par_index, "text": text[:30].strip() + "..."})
                self.save_history()
                self.redraw_scr()

            # 4. НАВИГАЦИЯ
            elif ch in [ord('j'), curses.KEY_DOWN]: 
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                old_pos = self.par_index
                self.par_index = min(max(0, len(self.lines) - d_h), self.par_index + 1)
                if old_pos != self.par_index: self.redraw_scr()
            elif ch in [ord('k'), curses.KEY_UP]: 
                old_pos = self.par_index
                self.par_index = max(0, self.par_index - 1)
                if old_pos != self.par_index: self.redraw_scr()
            elif ch == curses.KEY_HOME or ch == ord('g'): 
                self.par_index = 0
                self.redraw_scr()
            elif ch == curses.KEY_END or ch == ord('G'):
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                self.par_index = max(0, len(self.lines) - d_h)
                self.redraw_scr()
            elif ch == ord('['): self.jump_chapter(-1); self.redraw_scr()
            elif ch == ord(']'): self.jump_chapter(1); self.redraw_scr()

            # 5. ПОСТРАНИЧНОЕ ЛИСТАНИЕ
            elif ch in [ord(' '), curses.KEY_NPAGE, curses.KEY_RIGHT]: 
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                if self.flip_mode == 0: 
                    self.par_index = min(max(0, len(self.lines) - d_h), self.par_index + d_h)
                    self.redraw_scr()
                elif self.par_index < len(self.lines) - d_h:
                    self.animate_flip(1)
            elif ch == ord('d'): 
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                self.par_index = min(max(0, len(self.lines) - d_h), self.par_index + d_h // 2)
                self.redraw_scr()
            elif ch == ord('u'): 
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                self.par_index = max(0, self.par_index - d_h // 2)
                self.redraw_scr()

            elif ch in [curses.KEY_PPAGE, curses.KEY_LEFT]: 
                r, c = self.screen.getmaxyx()
                f_off = 1 if self.show_status else 0
                d_h = r - self.border_padding - f_off
                if self.flip_mode == 0: 
                    self.par_index = max(0, self.par_index - d_h)
                    self.redraw_scr()
                elif self.par_index > 0:
                    self.animate_flip(-1)

            # 6. ГОРЯЧИЕ КЛАВИШИ ВИДА И АВТОСКРОЛЛА (Исправлен баг слияния цветов на черном фоне)
            elif ch == ord('a'): 
                self.auto_scroll = not self.auto_scroll
                self.last_auto_time = time.time()
                self.redraw_scr()
            elif ch == ord('s') and self.auto_scroll: self.scroll_speed = min(10, self.scroll_speed + 1); self.redraw_scr()
            elif ch == ord('S') and self.auto_scroll: self.scroll_speed = max(1, self.scroll_speed - 1); self.redraw_scr()
            
            elif ch == ord('c'): 
                # Переключаем цвет текста, но если он совпал с фоном — шагаем дальше
                self.fg = (self.fg + 1) % 8
                if self.fg == self.bg: 
                    self.fg = (self.fg + 1) % 8
                self.update_colors()
                self.redraw_scr()
                
            elif ch == ord('b'): 
                # Переключаем фон, но следим, чтобы он не слился с текстом или заголовком
                self.bg = (self.bg + 1) % 8
                if self.bg == self.fg or self.bg == self.head_color:
                    self.bg = (self.bg + 1) % 8
                self.update_colors()
                self.redraw_scr()
                
            elif ch == ord('v'): 
                # Переключаем цвет заголовков, пропуская цвет фона
                self.head_color = (self.head_color + 1) % 8
                if self.head_color == self.bg:
                    self.head_color = (self.head_color + 1) % 8
                self.update_colors()
                self.redraw_scr()
                
            elif ch == ord('B'): self.show_border = (self.show_border + 1) % 3; self.prepare_lines(); self.redraw_scr()
            elif ch == ord('e'): self.flip_mode = (self.flip_mode + 1) % 5
            elif ch == ord('='): self.width = min(c-10, self.width+4); self.prepare_lines(); self.redraw_scr()
            elif ch == ord('-'): self.width = max(20, self.width-4); self.prepare_lines(); self.redraw_scr()

            elif ch == ord('K'):
                idx = self.available_langs.index(self.lang_code)
                self.lang_code = self.available_langs[(idx + 1) % len(self.available_langs)]
                self.load_lang(self.lang_code)
                self.prepare_lines()
                r, c = self.screen.getmaxyx()
                try:
                    self.screen.addstr(r - 1, c - 6, "     ", curses.color_pair(5))
                    self.screen.refresh()
                except: pass
                self.redraw_scr()

            # ПЕРЕКЛЮЧАТЕЛЬ НА ВЕРХНЮЮ РАМКУ ПО КЛАВИШЕ F:
            elif ch == ord('F'):
                current_state = getattr(self, 'show_version', True)
                # Инвертируем состояние флага
                self.show_version = not current_state
                # Принудительно очищаем и перерисовываем экран
                self.screen.erase()
                self.redraw_scr()
                continue

            elif ch == ord('H'):
                self.show_status = not self.show_status
                self.prepare_lines()
                self.screen.erase()
                self.redraw_scr()

            elif ch == ord('P'): self.jump_to_pct()

            if ch != -1 and ch not in [ord('n'), ord('N'), ord('/'), ord('f')]:
                if self.search_query and ch == ord('q'):
                    self.search_query = ""
                    continue
                self.search_query = ""

    def do_search(self):
        self.screen.nodelay(False)
        r, c = self.screen.getmaxyx()
        prompt = "/ "
        self.screen.attron(curses.color_pair(5))
        self.screen.move(r - 1, 0)
        self.screen.clrtoeol()
        self.screen.addstr(r - 1, 0, (prompt + " " * (c - len(prompt) - 1))[:c-1])
        
        curses.echo()
        curses.curs_set(1)
        try:
            raw = self.screen.getstr(r - 1, len(prompt))
            res = raw.decode('utf-8', errors='replace').strip()
            if res: 
                self.search_query = res
                self._search_re = re.compile(re.escape(res), re.IGNORECASE)
                self.find_next()
            else:
                self.search_query = ""
                self._search_re = None
        except: pass
            
        curses.noecho()
        curses.curs_set(0)
        self.screen.nodelay(True)

    def find_prev(self):
        if not self.search_query: return
        for i in range(self.par_index - 1, -1, -1):
            text = self.lines[i][1] if isinstance(self.lines[i], tuple) else str(self.lines[i])
            if self.search_query.lower() in text.lower():
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
                self.par_index = int((len(self.lines) - 1) * (val / 100.0))
        except: pass
        curses.noecho(); self.screen.nodelay(True)

    def open_footnote(self):
        r, c = self.screen.getmaxyx()
        f_off = 1 if self.show_status else 0
        d_h = r - self.border_padding - f_off
        visible_notes = []
        for i in range(d_h):
            idx = self.par_index + i
            if idx < len(self.lines):
                line_data = self.lines[idx]
                line_text = line_data[1] if isinstance(line_data, tuple) else str(line_data)
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
                nw.addstr(i + 1, 2, line[:max_w-4])
            nw.refresh(); nw.getch()
        except: pass
        self.redraw_scr()

def main():
    import sys, curses, os, json, argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('-v', '--version', action='store_true')
    parser.add_argument('--credits', action='store_true')
    parser.add_argument('filename', nargs='?')
    args = parser.parse_args()
    
    config_dir = os.path.expanduser("~/.config/fb2less")
    history_path = os.path.join(config_dir, "history.json")

    if args.version:
        print("fb2less version 1.0.6")
        return

    if args.credits:
        print("┌──────────────────────────────────────────────────────────┐")
        print("│                      fb2less v1.0.6                      │")
        print("├──────────────────────────────────────────────────────────┤")
        print("│  Разработчик:  measles                                   │")
        print("│                                                          │")
        print("│  Особая благодарность за подсказки с кодом, выравнивание │")
        print("│  рамок и победу над сносками - Gemini (Google AI)        │")
        print("└──────────────────────────────────────────────────────────┘")
        return

    if args.help:
        print("Usage: fb2less [FILE]\n\nControls:\n  h            - Help screen\n  o            - Settings menu\n  L            - Library\n  Z            - Scan directory\n  q            - Exit\n")
        return

    filename = args.filename
    if not filename and os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                books = {k: v for k, v in data.items() if isinstance(v, dict) and v.get('time')}
                if books:
                    filename = max(books.items(), key=lambda x: x[1]['time'])[0]
        except: pass

    if filename:
        full_path = os.path.abspath(os.path.expanduser(filename))
        if not os.path.exists(full_path):
            print(f"Error: File not found - {full_path}")
            return
        curses.wrapper(lambda stdscr: MainWindow(stdscr, full_path))
    else:
        print("Usage: fb2less [FILE]\nHint: Open the library (L) or scan a folder (Z) to add books.")

if __name__ == "__main__":
    main()
