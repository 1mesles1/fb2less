pkgname=fb2less
pkgver=0.8.5
pkgrel=2
pkgdesc="Advanced console reader (FB2, EPUB, TXT) with multi-language support"
arch=('any')
url="https://localhost"
license=('GPL')
depends=('python')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
source=()

build() {
  cd "$startdir"
  python -m build --wheel --no-isolation
}

package() {
  cd "$startdir"
  # 1. Основная установка кода через инсталлер
  python -m installer --destdir="$pkgdir" dist/*.whl

  # 2. Явное копирование ВСЕХ локалей (чтобы "карусель" видела новые файлы)
  # Находим куда инсталлер положил либу и докидываем туда JSON-ы
  local site_packages=$(python -c "import site; print(site.getsitepackages()[0])")
  install -Dm644 fb2less_lib/locales/*.json -t "$pkgdir/$site_packages/fb2less_lib/locales/"

  # 3. Установка мануалов (Английский — основной, Русский — в свою папку)
  install -Dm644 fb2less.1 "$pkgdir/usr/share/man/man1/fb2less.1"
  install -Dm644 fb2less.ru.1 "$pkgdir/usr/share/man/ru/man1/fb2less.1"
}
