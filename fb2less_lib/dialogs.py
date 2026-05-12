import curses, textwrap, os, json, time, re

def show_help(app):
    import curses
    r, c = app.screen.getmaxyx()
    h_commands = app.tr('help_commands')
    # Увеличиваем область под текст, так как заголовок ушел на рамку
    h_h, h_w = min(r - 2, 22), min(c - 4, 60)
    h_y, h_x = (r - h_h) // 2, (c - h_w) // 2
    
    try:
        hw = curses.newwin(h_h, h_w, h_y, h_x)
        hw.keypad(True)
        hw.bkgd(" ", curses.color_pair(1))
        
        # visible_rows теперь больше, так как мы не тратим строки на header внутри
        cur_top, visible_rows = 0, h_h - 4 
        
        while True:
            hw.erase()
            hw.box()
            
            # ЗАГОЛОВОК ПО ЦЕНТРУ РАМКИ
            title_label = f" {app.tr('help_header')} "
            start_x_title = max(0, (h_w - len(title_label)) // 2)
            hw.addstr(0, start_x_title, title_label, curses.A_BOLD)
            
            # ТЕКСТ КОМАНД
            for i in range(visible_rows):
                idx = i + cur_top
                if idx < len(h_commands):
                    # Печатаем со второй строки окна (индекс i + 1)
                    hw.addstr(i + 1, 2, h_commands[idx][:h_w-4])
            
            # ПОДСКАЗКА ПО СКРОЛЛУ (внизу на рамке или в последней строке)
            hint = f" {app.tr('help_scroll_hint')} "
            if h_w > len(hint) + 4:
                hw.addstr(h_h - 1, (h_w - len(hint)) // 2, hint, curses.A_BOLD)
            
            hw.refresh()
            ch = hw.getch()
            if ch in [ord('j'), curses.KEY_DOWN]:
                if cur_top + visible_rows < len(h_commands): cur_top += 1
            elif ch in [ord('k'), curses.KEY_UP]:
                if cur_top > 0: cur_top -= 1
            elif ch in [27, ord('q'), ord('h'), 10, 13]: 
                break
    except: 
        pass
    app.redraw_scr()

def show_info(app):
    import curses, os, textwrap
    r, c = app.screen.getmaxyx()
    
    # 1. Готовим текст
    m = app.content.meta
    info_text = [
        f" {app.tr('info_title')}: {m['title']}",
        f" {app.tr('info_author')}: {m['author']}",
    ]
    if m['series']:
        info_text.append(f" {app.tr('info_series')}: {m['series']}")
        
    info_text.append("-" * 40)
    
    # Техданные
    f_size = os.path.getsize(app.filename) // 1024 if os.path.exists(app.filename) else 0
    ext = app.filename.lower()
    if ext.endswith('.zip'): f_type = "ZIP/FB2"
    elif ext.endswith('.epub'): f_type = "EPUB"
    elif ext.endswith('.txt'): f_type = "TXT"
    else: f_type = "FB2"

    total_pages = (len(app.lines) // 50) + 1
    
    info_text.append(f" {app.tr('info_file')}:     {os.path.basename(app.filename)} ({f_type})")
    info_text.append(f" {app.tr('info_size')}:   {f_size} KB")
    info_text.append(f" {app.tr('info_volume')}:   {len(app.lines)} {app.tr('info_lines')} (~{total_pages} {app.tr('info_pages')})")
    info_text.append("-" * 40)
    
    if m['annotation']:
        info_text.append(f" {app.tr('info_annot')}:")
        wrapped_ann = textwrap.wrap(m['annotation'], width=min(c - 10, 50))
        info_text.extend(["   " + line for line in wrapped_ann[:15]])
        if len(wrapped_ann) > 15: info_text.append("   ...")

    # 2. Отрисовка окна
    h_h, h_w = len(info_text) + 2, min(c - 4, 60)
    y, x = (r - h_h) // 2, (c - h_w) // 2
    
    try:
        iw = curses.newwin(h_h, h_w, max(0, y), max(0, x))
        iw.keypad(True)
        iw.bkgd(" ", curses.color_pair(1))
        iw.box()
        
        # ЗАГОЛОВОК ПОСЕРЕДИНЕ
        title_label = app.tr('info_header')
        # Вычисляем центр: (ширина окна - длина текста) // 2
        start_x_title = max(0, (h_w - len(title_label)) // 2)
        iw.addstr(0, start_x_title, title_label, curses.A_BOLD)
        
        for i, line in enumerate(info_text):
            if i < h_h - 2:
                iw.addstr(i + 1, 2, line[:h_w-4])
        iw.refresh()
        iw.getch()
    except: pass
    app.redraw_scr()

def show_toc(app):
    if not app.toc: return
    r, c = app.screen.getmaxyx()
    w_win = min(c - 4, 60)
    h_win = min(r - 4, len(app.toc) + 2)
    y, x = (r - h_win) // 2, (c - w_win) // 2
    
    try:
        tw = curses.newwin(h_win, w_win, y, x)
        tw.keypad(True); tw.bkgd(" ", curses.color_pair(1))
        cur = 0
        for i, (title, l_idx) in enumerate(app.toc):
            if l_idx <= app.par_index: cur = i
        
        r_avail = h_win - 2
        off = max(0, cur - r_avail // 2)

        while True:
            tw.erase(); tw.box()
            header = f" {app.tr('ui_toc_title')} "
            tw.addstr(0, (w_win - len(header)) // 2, header, curses.A_BOLD)
            
            off = max(0, min(cur, len(app.toc) - r_avail)) if cur < off or cur >= off + r_avail else off

            for i in range(r_avail):
                idx = i + off
                if idx < len(app.toc):
                    style = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                    name = app.toc[idx][0][:w_win-6]
                    tw.addstr(i + 1, 2, f"  {name}".ljust(w_win-4), style)
            
            tw.refresh()
            key = tw.getch()
            if key in [ord('j'), curses.KEY_DOWN]: cur = min(len(app.toc)-1, cur + 1)
            elif key in [ord('k'), curses.KEY_UP]: cur = max(0, cur - 1)
            elif key == curses.KEY_HOME: 
                cur = 0
            elif key == curses.KEY_END: 
                cur = len(app.toc) - 1
            elif key == curses.KEY_NPAGE: 
                cur = min(len(app.toc) - 1, cur + r_avail)
            elif key == curses.KEY_PPAGE: 
                cur = max(0, cur - r_avail)
            elif key in [10, 13, curses.KEY_ENTER]:
                app.par_index = app.toc[cur][1]
                break
            elif key in [ord('q'), ord('t'), 27]: break
    except: pass
    app.redraw_scr()

def show_bookmarks(app):
    if not app.bookmarks: return
    r, c = app.screen.getmaxyx()
    w_win, h_win = min(c - 4, 50), min(r - 4, 15)
    y, x = (r - h_win) // 2, (c - w_win) // 2
    try:
        bw = curses.newwin(h_win, w_win, y, x)
        bw.keypad(True); bw.bkgd(" ", curses.color_pair(1))
        cur = 0
        while True:
            bw.erase(); bw.box()
            title = f" {app.tr('ui_bookmarks')} "
            bw.addstr(0, (w_win - len(title)) // 2, title, curses.A_BOLD)
            for i, bm in enumerate(app.bookmarks[:h_win-2]):
                style = curses.A_REVERSE if i == cur else curses.A_NORMAL
                pct = int((bm['pos'] / len(app.lines)) * 100) if app.lines else 0
                bw.addstr(i + 1, 2, f"{pct}%: {bm['text']}"[:w_win-4].ljust(w_win-4), style)
            bw.refresh()
            key = bw.getch()
            if key in [ord('j'), curses.KEY_DOWN]: cur = min(len(app.bookmarks)-1, cur + 1)
            elif key in [ord('k'), curses.KEY_UP]: cur = max(0, cur - 1)
            elif key in [ord('x'), ord('D'), curses.KEY_DC]:
                app.bookmarks.pop(cur)
                if not app.bookmarks: break
                cur = max(0, cur - 1)
            elif key in [10, 13, curses.KEY_ENTER]:
                app.par_index = app.bookmarks[cur]['pos']
                break
            elif key in [ord('q'), 27, ord('M')]: break
    except: pass
    app.redraw_scr()

def show_settings(app):
    import curses, os, time
    r, c = app.screen.getmaxyx()
    conf = app.storage.load_config()
    # Берем путь из памяти приложения или из конфига
    scan_path = getattr(app, 'scan_path', conf.get("scan_path", os.getcwd()))

    cur = 0
    w_win, h_win = min(c - 4, 60), 12
    y, x = (r - h_win) // 2, (c - w_win) // 2
    
    try:
        sw = curses.newwin(h_win, w_win, y, x)
        sw.keypad(True)
        sw.bkgd(" ", curses.color_pair(1))
        
        while True:
            sw.erase()
            sw.box()
            title = f" {app.tr('ui_settings')} "
            sw.addstr(0, (w_win - len(title)) // 2, title, curses.A_BOLD)
            
            st_val = app.tr('ui_on') if app.show_status else app.tr('ui_off')
            menu_items = [
                f"{app.tr('ui_language')}: {app.lang_code.upper()}",
                f"{app.tr('set_status')}: {st_val}",
                f"{app.tr('set_path')}: {scan_path}",
                app.tr('set_scan'),
                app.tr('set_clear_lib'),
                f"{app.tr('set_voice_speed')}: {app.voice_speed}%",
                f"{app.tr('ui_tts_language')}: {app.tts_lang.upper()}", # Новый пункт 6
                app.tr('set_save'),
                app.tr('ui_back')
            ]

            for i, item in enumerate(menu_items):
                style = curses.A_REVERSE if i == cur else curses.A_NORMAL
                # Обрезаем текст, если он шире окна
                d_text = item if len(item) < w_win-4 else item[:w_win-7] + "..."
                sw.addstr(i + 1, 2, d_text.ljust(w_win - 4), style)

            sw.refresh()
            key = sw.getch()

            # 1. Навигация
            if key in [ord('j'), curses.KEY_DOWN]:
                cur = (cur + 1) % len(menu_items)
            elif key in [ord('k'), curses.KEY_UP]:
                cur = (cur - 1) % len(menu_items)

            # 2. РЕГУЛИРОВКА СТРЕЛКАМИ (Влево/Вправо)
            elif key == curses.KEY_RIGHT:
                if cur == 5: # Индекс для Скорости чтения
                    app.voice_speed = min(200, app.voice_speed + 5)
            elif key == curses.KEY_LEFT:
                if cur == 5: # Твой индекс для Скорости чтения
                    app.voice_speed = max(50, app.voice_speed - 5)
            
            # 2. Мгновенный выход по кнопкам
            elif key in [ord('q'), 27, ord('o'), 1097]:
                curses.flushinp()
                break

            elif key in [10, 13, curses.KEY_ENTER]:
                if cur == 0: # 1. Язык интерфейса
                    idx = app.available_langs.index(app.lang_code)
                    app.lang_code = app.available_langs[(idx + 1) % len(app.available_langs)]
                    app.load_lang(app.lang_code)
                    app.prepare_lines()
                    app.redraw_scr()
                
                elif cur == 1: # 2. Статус-бар
                    app.show_status = not app.show_status
                    try:
                        app.screen.move(r - 1, 0)
                        app.screen.clrtoeol()
                        app.screen.addstr(r - 1, 0, " " * (c - 1), curses.color_pair(4))
                    except: pass
                    app.prepare_lines() 
                    app.redraw_scr() 
                    sw.touchwin()
                    app.screen.noutrefresh()
                    sw.noutrefresh()
                    curses.doupdate()
                
                elif cur == 2: # 3. Ввод пути
                    curses.echo(); curses.curs_set(1)
                    prompt = "> "
                    sw.addstr(h_win-2, 2, " " * (w_win-4), curses.color_pair(5))
                    sw.addstr(h_win-2, 2, prompt, curses.color_pair(5))
                    try:
                        raw = sw.getstr(h_win-2, 2 + len(prompt))
                        res = raw.decode('utf-8').strip()
                        if res:
                            test_p = os.path.abspath(os.path.expanduser(res))
                            if os.path.isdir(test_p):
                                scan_path = test_p
                                app.scan_path = scan_path
                            else:
                                err_msg = f"! {app.tr('err_path_nf')} !"
                                sw.addstr(h_win-2, 2, err_msg.center(w_win-4), curses.color_pair(2))
                                sw.refresh(); time.sleep(1.2)
                    except: pass
                    curses.noecho(); curses.curs_set(0)

                elif cur == 3: # 4. Сканирование
                    app.storage.scan_directory(app, custom_path=scan_path)
                    app.history_data = app.storage.load_full_history()
                
                elif cur == 4: # 5. Очистка библиотеки
                    app.history_data = app.storage.clear_library(app.filename)
                    sw.addstr(h_win-2, 2, " Done! ".center(w_win-4), curses.color_pair(5))
                    sw.refresh(); time.sleep(0.5)

                elif cur == 5: # Скорость чтения
                    app.voice_speed += 10
                    if app.voice_speed > 200: app.voice_speed = 50

                elif cur == 6: # ЯЗЫК ЧТЕНИЯ (TTS)
                    idx = app.available_langs.index(app.tts_lang)
                    app.tts_lang = app.available_langs[(idx + 1) % len(app.available_langs)]
                    if app.voice_active:
                        app.toggle_tts(stop=True); app.toggle_tts()

                elif cur == 7: # Сохранить
                    app.scan_path = scan_path; app.save_history()
                    curses.flushinp(); break
                
                elif cur == 8: # Назад
                    curses.flushinp(); break                
                # Возвращаем фокус на окно настроек после любого действия
                sw.touchwin()
                sw.refresh()
    except: pass

    curses.napms(50)
    curses.flushinp()
    
    app.redraw_scr()

def show_library(app):
    hist_data = app.history_data
    all_items = []
    for path, info in hist_data.items():
        if path == "settings": continue
        all_items.append({
            'path': path,
            'title': info.get('title', os.path.basename(path)),
            'author': info.get('author', app.tr('meta_unknown')),
            'series': info.get('series', '')
        })
    if not all_items: return

    sort_mode = 0 
    sort_labels = ['sort_title', 'sort_author', 'sort_series']
    filter_query = ""
    
    r, c = app.screen.getmaxyx()
    w_win, h_win = min(c - 4, 60), min(r - 4, 30)
    y, x = (r - h_win) // 2, (c - w_win) // 2
    r_available = h_win - 6 # Место под список

    try:
        lw = curses.newwin(h_win, w_win, y, x)
        lw.keypad(True); lw.bkgd(" ", curses.color_pair(1))
        
        # Флаг для первоначальной установки курсора
        first_run = True

        while True:
            # 1. Фильтрация и сортировка
            items = [it for it in all_items if not filter_query or 
                     filter_query.lower() in it['path'].lower() or 
                     filter_query.lower() in it['title'].lower()]
            
            if sort_mode == 1:
                items = sorted(items, key=lambda x: (x['author'].lower(), x['title'].lower()))
            elif sort_mode == 2:
                items = sorted(items, key=lambda x: (x['series'] == '', x['series'].lower(), x['title'].lower()))
            else:
                items = sorted(items, key=lambda x: x['title'].lower())

            # ФОКУС: Находим текущую книгу в отсортированном списке
            if first_run:
                target = os.path.abspath(app.filename)
                cur = 0
                for i, it in enumerate(items):
                    if os.path.abspath(it['path']) == target:
                        cur = i; break
                first_run = False

            if not items: cur = 0
            elif cur >= len(items): cur = len(items) - 1

            lw.erase(); lw.box()
            header = f" {app.tr('ui_lib_title')} "
            lw.addstr(0, (w_win - len(header)) // 2, header, curses.A_BOLD)

            off = max(0, cur - r_available // 2)
            if off > len(items) - r_available: off = max(0, len(items) - r_available)

            for i in range(r_available):
                idx = i + off
                if idx < len(items):
                    style = curses.A_REVERSE if idx == cur else curses.A_NORMAL
                    it = items[idx]
                    d_name = it['title']
                    if sort_mode == 1: d_name = f"{it['author']} - {it['title']}"
                    elif sort_mode == 2 and it['series']: d_name = f"({it['series']}) {it['title']}"
                    lw.addstr(i + 1, 2, d_name[:w_win-4].ljust(w_win-4), style)

            # --- ПОСТОЯННЫЙ ПОДВАЛ С РАЗДЕЛИТЕЛЕМ ---
            lw.attron(curses.color_pair(1))
            # Линия над поиском
            lw.hline(h_win - 5, 1, curses.ACS_HLINE, w_win - 2)
            
            # Очистка строки поиска
            lw.move(h_win - 4, 1)
            lw.addstr(" " * (w_win - 2))
            
            # Подготовка текста (поиск или сортировка)
            if filter_query:
                p_text = f"{app.tr('lib_search')}{filter_query}"
                attr = curses.color_pair(2) | curses.A_BOLD
            else:
                p_text = f"{app.tr('lib_sort')}{app.tr(sort_labels[sort_mode])}"
                attr = curses.color_pair(1)
            
            # ВЫЧИСЛЕНИЕ ЦЕНТРА
            display_text = p_text[:w_win-4]
            start_x = max(2, (w_win - len(display_text)) // 2)
            lw.addstr(h_win - 4, start_x, display_text, attr)

            # ЛИНИЯ-РАЗДЕЛИТЕЛЬ МЕЖДУ ПОИСКОМ И ПУТЕМ
            lw.hline(h_win - 3, 1, curses.ACS_HLINE, w_win - 2)
            
            # Очистка и отрисовка строки пути
            lw.move(h_win - 2, 1)
            lw.addstr(" " * (w_win - 2))
            if items:
                path = items[cur]['path']
                display_path = path if len(path) < w_win - 6 else "..." + path[-(w_win-7):]
                lw.addstr(h_win - 2, 2, display_path)
            lw.attroff(curses.color_pair(1))

            lw.refresh()
            key = lw.getch()

            if key == ord('/'):
                p_prompt = app.tr('lib_search')
                lw.move(h_win - 4, 1); lw.addstr(" " * (w_win - 2))
                lw.addstr(h_win - 4, 2, p_prompt, curses.color_pair(2) | curses.A_BOLD)
                curses.echo(); curses.curs_set(1)
                try:
                    raw = lw.getstr(h_win - 4, 2 + len(p_prompt))
                    filter_query = raw.decode('utf-8').strip()
                except: pass
                curses.noecho(); curses.curs_set(0); cur = 0
            elif key == 27: 
                if filter_query: filter_query = ""; cur = 0
                else: break
            elif key in [ord('s'), 1099]:
                sort_mode = (sort_mode + 1) % 3
                first_run = True
            elif key in [ord('j'), curses.KEY_DOWN]: cur = min(len(items)-1, cur + 1)
            elif key in [ord('k'), curses.KEY_UP]: cur = max(0, cur - 1)
            elif key == curses.KEY_HOME: 
                cur = 0
            elif key == curses.KEY_END: 
                cur = len(items) - 1
            elif key == curses.KEY_NPAGE:
                cur = min(len(items) - 1, cur + r_available)
            elif key == curses.KEY_PPAGE:
                cur = max(0, cur - r_available)
            elif key in [10, 13, curses.KEY_ENTER] and items:
                app.save_history()
                app.filename = items[cur]['path']
                app.reload_content()
                app.prepare_lines()
                
                new_hist = app.storage.load_full_history().get(app.filename, {})
                app.par_index = new_hist.get('pos', 0)
                app.bookmarks = new_hist.get('bookmarks', [])
                
                curses.flushinp() # ОЧИСТКА ОЧЕРЕДИ: гарантирует мгновенный выход
                break
            elif key in [ord('D'), curses.KEY_DC] and items:
                # Удаляем из истории
                p_to_del = items[cur]['path']
                if p_to_del in app.history_data:
                    del app.history_data[p_to_del]
                    # Сохраняем пустой конфиг + обновленную историю
                    app.storage.save_all(app.storage.load_config(), app.history_data, {})
                    # Обновляем локальный список для отрисовки
                    all_items = [it for it in all_items if it['path'] != p_to_del]
            elif key in [ord('q'), ord('L')]: break
    except: pass
    app.redraw_scr()
