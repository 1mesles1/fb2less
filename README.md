# fb2less (v0.8)

Advanced console eBook reader for FB2, EPUB, and TXT.

## Features
- **Formats**: FB2, EPUB, TXT (including ZIP archives).
- **Localization**: Full support for English and Russian (switchable with `K`).
- **Navigation**: Chapters, percentages, and search within the book.
- **Library**: Built-in history with search and per-book settings.
- **Customization**: Change colors, text width, and borders on the fly.
- **Bilingual Manual**: Man pages in English and Russian.

## Screenshots
![1](screenshots/01.png)
![2](screenshots/02.png)
![3](screenshots/03.png)

## Installation

### Arch Linux
1. Clone the repo: `git clone https://github.com`
2. Run `makepkg -si`.

### Ubuntu / Debian
You can install it manually:
1. `sudo apt install python3`
2. Clone the repo.
3. Run the following to install system-wide:
```bash
sudo cp -r fb2less_lib /usr/lib/python3/dist-packages/
sudo cp fb2less.1 /usr/share/man/man1/
sudo cp fb2less.ru.1 /usr/share/man/ru/man1/fb2less.1
# Create executable
echo -e '#!/usr/bin/env python3\nfrom fb2less_lib.reader import main\nimport sys\nsys.exit(main())' | sudo tee /usr/bin/fb2less
sudo chmod +x /usr/bin/fb2less
```

## Usage
`fb2less [file]`
