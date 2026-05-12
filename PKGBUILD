# Maintainer: 1mesles1 <https://github.com/1mesles1>

pkgname=fb2less
pkgver=0.9.6
pkgrel=1
pkgdesc="Advanced console reader (FB2, EPUB, TXT) with multi-language support and TTS"
arch=('any')
url="https://github.com/1mesles1/fb2less"
license=('GPL3')
depends=('python' 'speech-dispatcher')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')

source=("fb2less.1" "fb2less.ru.1") 
sha256sums=('SKIP' 'SKIP')

build() {
  cd "$startdir"
  python -m build --wheel --no-isolation
}

package() {
  cd "$startdir"

  python -m installer --destdir="$pkgdir" dist/*.whl

  local site_packages=$(python -c "import sys; print(f'/usr/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')")
  
  install -Dm644 fb2less_lib/locales/*.json -t "$pkgdir/$site_packages/fb2less_lib/locales/"

  install -Dm644 fb2less.1 "$pkgdir/usr/share/man/man1/fb2less.1"
  install -Dm644 fb2less.ru.1 "$pkgdir/usr/share/man/ru/man1/fb2less.1"
  
  if [ -f "LICENSE" ]; then
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  fi
}
