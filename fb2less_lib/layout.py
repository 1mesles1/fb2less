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
    
    # --- 1. ОСНОВНОЙ ТЕКСТ (Убедись, что этот цикл на месте!) ---
    for p_type, text in paragraphs:
        # Если пришла пустая строка
        if not text.strip():
            # Проверяем текст (индекс 1) последнего добавленного кортежа
            if new_lines and new_lines[-1][1] != "":
                new_lines.append(("body", ""))
            continue

        t = text.strip()
        if p_type == "title":
            # Проверяем текст последнего кортежа через индекс [1]
            if new_lines and new_lines[-1][1] != "":
                new_lines.append(("body", ""))
            
            if t != meta_author:
                toc.append((text, len(new_lines)))
            for lt in textwrap.wrap(text, width=width):
                new_lines.append(("title", lt))
            new_lines.append(("body", ""))
        elif p_type == "poem":
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
            # Используем text вместо t для надежности
            for lt in textwrap.wrap(text, width=width-8):
                new_lines.append(("body", "    " + lt))

        elif p_type in ("author", "text-author"): 
            # Объединил оба варианта в один блок
            for lt in textwrap.wrap(text, width=width-12):
                new_lines.append(("body", "        " + lt))
            new_lines.append(("body", ""))
        else:
            # Разбиваем абзац на строки
            wrapped = textwrap.wrap(t, width=width-1)
            for i, line in enumerate(wrapped):
                if i == 0:
                    # Это первая строка абзаца — делаем «красную строку» (отступ в 1 пробел)
                    if len(wrapped) > 1: 
                        line = justify_text(line, width-1)
                    line = " " + line # Вот он, отступ!
                else:
                    # Это середина абзаца — растягиваем по ширине
                    if i < len(wrapped) - 1: 
                        line = justify_text(line, width)
                    # Если это последняя строка, мы её НЕ растягиваем (justify_text не вызываем)
                
                new_lines.append(("body", line))
    # --- 2. СНОСКИ В КОНЦЕ ---
    if notes:
        new_lines.append(("body", ""))
        # Используем переданный notes_label вместо жесткого текста
        toc.append((notes_label, len(new_lines)))
        new_lines.append(("title", notes_label))
        new_lines.append(("body", ""))
        
        def nat_sort(s): 
            return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]
            
        for n_id in sorted(notes.keys(), key=nat_sort):
            # ЧИСТИМ ID: если это FbAutId_2, превращаем в "2"
            display_id = "".join(filter(str.isdigit, n_id)) or n_id
            note_text = notes[n_id]
            
            wrapped = textwrap.wrap(f"[{display_id}] {note_text}", width=width)
            for line in wrapped:
                new_lines.append(("body", line))
    
    return new_lines, toc

def justify_text(text, width):
    words = text.split()
    if len(words) < 2:
        return text.ljust(width)

    chars_len = sum(len(w) for w in words)
    if chars_len >= width:
        return " ".join(words)

    total_spaces = width - chars_len
    gaps = len(words) - 1

    sp_per_gap = total_spaces // gaps
    extra = total_spaces % gaps
    res = ""
    for i in range(gaps):
        res += words[i] + " " * (sp_per_gap + (1 if i < extra else 0))
    res += words[-1]
    return res

