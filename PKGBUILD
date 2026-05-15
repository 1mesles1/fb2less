# Maintainer: 1mesles1 <https://github.com/1mesles1>

pkgname=fb2less
pkgver=1.0.0
pkgrel=1
pkgdesc="Advanced console reader (FB2, EPUB, TXT) with multi-language support and TTS"
arch=('any')
url="https://github.com/1mesles1/fb2less"
license=('GPL3')
depends=('python' 'speech-dispatcher')
optdepends=(
  'espeak-ng: alternative lightweight speech engine'
  'rhvoice: high-quality speech engine (highly recommended for Russian language)'
)
makedepends=('git' 'python-build' 'python-installer' 'python-setuptools' 'python-wheel')

# Ссылка соберется автоматически из переменной url
source=("git+${url}.git#tag=v${pkgver}")
sha256sums=('SKIP')

build() {
  cd "$pkgname"
  python -m build --wheel --no-isolation
}

package() {
  cd "$pkgname"

  python -m installer --destdir="$pkgdir" dist/*.whl

  install -Dm644 fb2less.1 "$pkgdir/usr/share/man/man1/fb2less.1"
  install -Dm644 fb2less.ru.1 "$pkgdir/usr/share/man/ru/man1/fb2less.1"
  
  if [ -f "LICENSE" ]; then
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  fi
}
