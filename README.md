# fb2less (v0.8)

Advanced terminal-based eBook reader for FB2, EPUB, and TXT formats.

## Features
- **Formats**: FB2, EPUB, TXT (including ZIP archives).
- **Localization**: Full English and Russian support (toggle with `K`).
- **Navigation**: Chapter jumps, percentage-based navigation, and in-book search.
- **Library**: Built-in reading history with search support and per-book settings.
- **Customization**: Change colors, text width, and borders on the fly.
- **Bilingual Documentation**: Manual pages (man) available in both English and Russian.

## Screenshots
[<img src="screenshots/01.png" width="400">](screenshots/01.png) [<img src="screenshots/02.png" width="400">](screenshots/02.png)
[<img src="screenshots/03.png" width="400">](screenshots/03.png) [<img src="screenshots/04.png" width="400">](screenshots/04.png)

## Installation

### Arch Linux
1. Clone the repository: `git clone https://github.com/1mesles1/fb2less`
2. Run `makepkg -si`.

### Ubuntu / Debian
Manual installation:
1. Install Python 3: `sudo apt update && sudo apt install python3`
2. Clone the repository.
3. Install system-wide:
```bash
sudo cp -r fb2less_lib /usr/lib/python3/dist-packages/
sudo cp fb2less.1 /usr/share/man/man1/fb2less.1
sudo mkdir -p /usr/share/man/ru/man1
sudo cp fb2less.ru.1 /usr/share/man/ru/man1/fb2less.1
# Create executable
echo -e '#!/usr/bin/env python3\nimport sys\nfrom fb2less_lib.reader import main\nsys.exit(main())' | sudo tee /usr/bin/fb2less
sudo chmod +x /usr/bin/fb2less
```

## Usage
`fb2less [FILE]`
```

## Usage
`fb2less [FILE]`
