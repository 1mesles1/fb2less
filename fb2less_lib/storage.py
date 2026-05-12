import os, json, time, curses

class Storage:
    def __init__(self, filename):
        self.filename = os.path.abspath(filename)
        self.config_dir = os.path.expanduser("~/.config/fb2less")
        os.makedirs(self.config_dir, exist_ok=True)
        
        self.history_file = os.path.join(self.config_dir, "history.json")
        self.config_file = os.path.join(self.config_dir, "config.json")

    def load_config(self):
        """Загружает глобальные настройки (цвета, язык, ширина)."""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return {}

    def load_full_history(self):
        """Загружает всю базу данных книг из истории."""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding='utf-8') as f:
                    return json.load(f)
        except: pass
        return {}

    def save_all(self, config_data, history_data, current_book_info=None):
        try:
            # Сохраняем глобальный конфиг (язык, статус-бар, ПУТЬ)
            with open(self.config_file, "w", encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)

            # Если передана инфа о книге, обновляем её в истории
            if current_book_info:
                history_data[self.filename] = current_book_info
            
            with open(self.history_file, "w", encoding='utf-8') as f:
                json.dump(history_data, f, ensure_ascii=False, indent=4)
        except: pass

    def clear_library(self, current_filename):
        # Загружаем всё
        all_hist = self.load_full_history()
        # Ищем данные именно той книги, которую передали (текущая читаемая)
        target_path = os.path.abspath(current_filename)
        current_data = all_hist.get(target_path, {})
        
        # Оставляем только её
        new_hist = {target_path: current_data}
        
        try:
            with open(self.history_file, "w", encoding='utf-8') as f:
                json.dump(new_hist, f, ensure_ascii=False, indent=4)
            return new_hist
        except:
            return all_hist

    def scan_directory(self, app, custom_path=None):
        import curses
        r, c = app.screen.getmaxyx()
        # Создаем окно прогресса
        sw = curses.newwin(3, 46, (r-3)//2, (c-46)//2)
        sw.bkgd(" ", curses.color_pair(5))
        sw.box()
        
        # Определяем путь для сканирования
        start_dir = custom_path or getattr(app, 'scan_path', os.getcwd())
        start_dir = os.path.abspath(os.path.expanduser(start_dir))

        if not os.path.isdir(start_dir):
            err_msg = f"! {app.tr('err_path_nf')} !"
            sw.addstr(1, (46-len(err_msg))//2, err_msg, curses.color_pair(2))
            sw.refresh()
            time.sleep(1.5)
            return
            
        scan_msg = f"{app.tr('msg_scanning')}..."
        sw.addstr(1, (46-len(scan_msg))//2, scan_msg)
        sw.refresh()

        found_new = 0
        total_found = 0
        hist_data = self.load_full_history()
        existing_titles = [info.get('title', '') for info in hist_data.values()]

        # Импортируем парсеры для извлечения метаданных
        from .fb2_parser import fb2parse
        from .epub_parser import epub_parse

        for root_dir, dirs, files in os.walk(start_dir):
            for file in files:
                if file.lower().endswith(('.fb2', '.fb2.zip', '.zip', '.epub', '.txt')):
                    full_path = os.path.abspath(os.path.join(root_dir, file))
                    total_found += 1
                    
                    if full_path not in hist_data:
                        ext = file.lower()
                        author = app.tr('meta_unknown')
                        title = file
                        series = ""

                        try:
                            if ext.endswith(('.fb2', '.zip')):
                                content = fb2parse(full_path)
                                title = content.meta.get('title', file)
                                author = content.meta.get('author', author)
                                series = content.meta.get('series', '')
                            elif ext.endswith('.epub'):
                                content = epub_parse(full_path)
                                title = content.meta.get('title', file)
                                author = content.meta.get('author', author)
                        except:
                            pass
                        
                        if title in existing_titles:
                            title = "*" + title
                        
                        hist_data[full_path] = {
                            "pos": 0,
                            "bookmarks": [],
                            "title": str(title),
                            "author": str(author),
                            "series": str(series),
                            "time": time.time()
                        }
                        existing_titles.append(title)
                        found_new += 1

        # Очистка истории от несуществующих файлов
        deleted_count = 0
        for path in list(hist_data.keys()):
            if path != "settings" and not os.path.exists(path):
                del hist_data[path]
                deleted_count += 1

        # Сохраняем обновленную базу (используем текущий конфиг)
        self.save_all(app.storage.load_config(), hist_data)
        
        # Финальный результат
        sw.erase()
        sw.box()
        total_label = app.tr('scan_total') if app.tr('scan_total') != 'scan_total' else "Всего"
        res_msg = (
            f"{total_label}: {total_found} "
            f"({app.tr('scan_new')}: {found_new}) / "
            f"{app.tr('scan_del')}: {deleted_count}"
        )
        sw.addstr(1, max(1, (46 - len(res_msg)) // 2), res_msg[:44])
        sw.refresh()
        time.sleep(1.5)
        
        # Обновляем данные в запущенном приложении
        app.history_data = hist_data
        app.redraw_scr()
