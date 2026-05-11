#!/bin/bash

# для сборки deb и whl fb2less
#
# --- НАСТРОЙКИ ---
VERSION="0.9.4"
MAINTAINER="YourName"
# -----------------

echo "--- Сборка версии $VERSION ---"

# 1. Сборка Python Wheel
echo "[1/5] Собираю Python Wheel..."
python3 -m build --wheel

# 2. Подготовка структуры DEB
echo "[2/5] Подготовка структуры DEB-пакета..."
rm -rf deb_build
mkdir -p deb_build/usr/bin
mkdir -p deb_build/usr/share/man/man1
mkdir -p deb_build/usr/share/man/ru/man1
mkdir -p deb_build/usr/lib/python3/dist-packages/fb2less_lib
mkdir -p deb_build/DEBIAN

# 3. Копирование файлов
echo "[3/5] Копирование файлов..."
cp -r fb2less_lib/* deb_build/usr/lib/python3/dist-packages/fb2less_lib/
cp fb2less.1 deb_build/usr/share/man/man1/
cp fb2less.ru.1 deb_build/usr/share/man/ru/man1/fb2less.1

# 4. Создание служебных файлов (Control и Исполняемый)
echo "[4/5] Генерация служебных файлов..."

cat <<EOF > deb_build/DEBIAN/control
Package: fb2less
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-urwid
Maintainer: $MAINTAINER
Description: Advanced console reader (FB2, EPUB, TXT) with smart formatting.
EOF

cat <<EOF > deb_build/usr/bin/fb2less
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')
from fb2less_lib.reader import main
if __name__ == "__main__":
    sys.exit(main())
EOF

# 5. Права и сборка
echo "[5/5] Установка прав и финальная сборка..."
find deb_build -type d -exec chmod 755 {} +
find deb_build -type f -exec chmod 644 {} +
chmod 755 deb_build/usr/bin/fb2less
chmod 755 deb_build/DEBIAN/control

dpkg-deb --build deb_build "fb2less_${VERSION}_amd64.deb"

echo "--- Готово! Пакеты собраны. ---"
ls -l *.deb *.whl
