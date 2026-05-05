import textwrap
import re

def justify_text(text, width):
    words = text.split()
    if len(words) < 2: return text.ljust(width)
    chars_len = sum(len(w) for w in words)
    if chars_len >= width: return " ".join(words)
    total_spaces = width - chars_len
    gaps = len(words) - 1
    sp_per_gap = total_spaces // gaps
    extra = total_spaces % gaps
    res = ""
    for i in range(gaps):
        res += words[i] + " " * (sp_per_gap + (1 if i < extra else 0))
    res += words[-1]
    return res

def prepare_layout(paragraphs, width, meta_author="", notes=None, notes_label="--- СНОСКИ ---"):
    new_lines = []
    toc = []
    
    for p_type, text in paragraphs:
        if not text.strip():
            if new_lines and new_lines[-1][1] != "":
                new_lines.append(("body", ""))
            continue

        t = text.strip()
        if p_type == "title":
            if new_lines and new_lines[-1][1] != "":
                new_lines.append(("body", ""))
            if t != meta_author:
                toc.append((text, len(new_lines)))
            for lt in textwrap.wrap(text, width=width):
                new_lines.append(("title", lt))
            new_lines.append(("body", ""))
            
        elif p_type == "poem":
            # СТИХИ: Отступ 10 пробелов для каждой строки (твоя оригинальная логика)
            for lt in textwrap.wrap(t, width=width-15):
                new_lines.append(("body", " " * 10 + lt))
                
        elif p_type == "epigraph":
            indent = width // 3
            for lt in textwrap.wrap(t, width=width - indent - 2):
                new_lines.append(("body", " " * indent + lt))

        elif p_type == "cite":
            if new_lines and new_lines[-1][1] != "":
                new_lines.append(("body", ""))
            for lt in textwrap.wrap(text, width=width-8):
                new_lines.append(("body", "    " + lt))

        elif p_type == "emphasis_block":
            for lt in textwrap.wrap(text, width=width-8):
                new_lines.append(("body", "    " + lt))

        elif p_type in ("author", "text-author"): 
            # Твоя новая динамическая логика для автора справа
            clean_text = text.strip()
            indent_size = max(0, width - len(clean_text) - 4)
            if indent_size < 10: indent_size = max(0, width // 2)
            avail_w = max(10, width - indent_size)
            for lt in textwrap.wrap(clean_text, width=avail_w):
                new_lines.append(("body", " " * indent_size + lt))
            new_lines.append(("body", ""))
            
        else:
            # ОБЫЧНЫЙ ТЕКСТ (body)
            # 1. Убираем лишние пробелы, чтобы textwrap работал чисто
            t_content = text.strip()
            
            # 2. Нарезаем текст (оставляем место под 2 пробела)
            wrapped = textwrap.wrap(t_content, width=width-2)
            
            for i, line in enumerate(wrapped):
                if i == 0:
                    # КРАСНАЯ СТРОКА: ровно 2 пробела в начале абзаца
                    if len(wrapped) > 1: 
                        line = justify_text(line, width-2)
                    new_lines.append(("body", "  " + line))
                else:
                    # Остальные строки абзаца — без отступа
                    if i < len(wrapped) - 1: 
                        line = justify_text(line, width)
                    new_lines.append(("body", line))

    if notes:
        new_lines.append(("body", ""))
        toc.append((notes_label, len(new_lines)))
        new_lines.append(("title", notes_label))
        new_lines.append(("body", ""))
        def nat_sort(s): 
            return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]
        for n_id in sorted(notes.keys(), key=nat_sort):
            display_id = "".join(filter(str.isdigit, n_id)) or n_id
            note_text = notes[n_id]
            wrapped = textwrap.wrap(f"[{display_id}] {note_text}", width=width)
            for line in wrapped:
                new_lines.append(("body", line))
    
    return new_lines, toc
