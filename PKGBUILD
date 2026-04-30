pkgname=fb2less
pkgver=0.8
pkgrel=1
pkgdesc="Advanced console FB2 reader (modular version)"
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
  python -m installer --destdir="$pkgdir" dist/*.whl
  
  install -Dm644 fb2less.1 "$pkgdir/usr/share/man/man1/fb2less.1"
  install -Dm644 fb2less.ru.1 "$pkgdir/usr/share/man/ru/man1/fb2less.1"
}
