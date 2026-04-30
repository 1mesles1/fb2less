import os

class TXTParser:
    # Добавляем unknown_author в аргументы
    def __init__(self, filename, unknown_author="Unknown Author"):
        self.paragraphs = []
        self.notes = {}
        # Используем переданный перевод для автора
        self.meta = {
            'title': os.path.basename(filename), 
            'author': unknown_author, 
            'series': '', 
            'annotation': ''
        }
        self.encoding = 'utf-8'
        self._parse(filename)

    def _parse(self, filename):
        try:
            with open(filename, 'rb') as f:
                raw_data = f.read()
            
            for enc in ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']:
                try:
                    text = raw_data.decode(enc)
                    self.encoding = enc
                    lines = text.splitlines()
                    current_paragraph = []

                    for line in lines:
                        clean_line = line.strip()
                        if clean_line:
                            current_paragraph.append(clean_line)
                        else:
                            if current_paragraph:
                                self.paragraphs.append(('body', " ".join(current_paragraph)))
                                current_paragraph = []
                            self.paragraphs.append(('body', ""))
                    
                    if current_paragraph:
                        self.paragraphs.append(('body', " ".join(current_paragraph)))
                    break
                except: continue
        except: pass

# Обновляем обертку
def txt_parse(filename, unknown_author="Unknown Author"):
    return TXTParser(filename, unknown_author)
