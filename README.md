# fb2less (v1.0.1) Final Release
**16 May 2026**

Advanced terminal-based eBook reader for FB2, EPUB, and TXT formats.

## Features
- **Multi-format Support**: FB2, EPUB, and TXT. Direct reading from ZIP archives.
- **Smart Parsing**: Enhanced EPUB rendering that handles complex layouts and properly reconstructs paragraph breaks.
- **Multilingual Interface**: Full support for **English**, **Russian**, and **German** (toggle instantly with `K`).
- **Advanced Library**:
  - Persistent reading history and per-book settings.
  - Interactive library manager (`L`) with search and smart sorting.
  - **Sorting**: Organize your collection by **Title**, **Author**, or **Series** (`s`).
- **Voice Reading (TTS)**:
  - Synchronized line-by-line speech generation (`V`).
  - **Dynamic Engines & Voices**: Switch between `spd-say` and `espeak-ng` dynamically. Select any installed system voice via an interactive, scrollable popup menu.
  - **Visual Focus**: The currently read line is highlighted in real-time.
  - **Smart Pagination**: Automatically turns pages as the narrator finishes the text.
  - **Multilingual Voices**: Automatically synchronizes the reading language with the selected system voice.
  - **Adjustable Speed**: Change speech rate (50% to 200%) on the fly in settings.
- **Rich Navigation**:
  - Chapter navigation (`[` / `]`) and Table of Contents (`t`).
  - Search within books (`/`) and bookmarks manager (`M`).
  - Interactive status bar with progress percentage and visual bar `[███  ]`.
- **Visual Customization**:
  - **3 Border Styles**: Toggle between no borders, a window-frame, or text-focused borders (`B`) for a focused reading experience.
  - **5 Flip Animations**: Various page-turn effects (`e`) from instant to sliding.
  - **Dynamic Theming**: On-the-fly adjustments for Text, Background, and Header colors (`c`, `b`, `v`).
  - **Adjustable Layout**: Change text width and alignment to fit any terminal size.
- **Auto-scroll**: Hands-free reading with adjustable speed.
- **Footnotes**: Instant access to footnotes and links in a popup window (`f`).
- **Documentation**: Manual pages (man) available in both English and Russian.

## Screenshots
[<img src="screenshots/01.png" width="400">](screenshots/01.png) [<img src="screenshots/02.png" width="400">](screenshots/02.png)
[<img src="screenshots/03.png" width="400">](screenshots/03.png) [<img src="screenshots/04.png" width="400">](screenshots/04.png)

### Installation (Arch Linux)
```bash
git clone https://github.com/1mesles1/fb2less
cd fb2less
makepkg -si
```

### Ubuntu / Debian (Build from source)
1. Install build tools:
   ```bash
   sudo apt update && sudo apt install python3-build python3-installer git
   ```
2. Clone and build:
   ```bash
   git clone https://github.com/1mesles1/fb2less
   cd fb2less
   python3 -m build --wheel --no-isolation
   ```
3. Install package and manual pages:
   ```bash
   sudo python3 -m installer dist/*.whl
   sudo cp fb2less.1 /usr/share/man/man1/
   sudo mkdir -p /usr/share/man/ru/man1
   sudo cp fb2less.ru.1 /usr/share/man/ru/man1/fb2less.1
   ```

## Usage
`fb2less [file]`

## Requirements
For the **Voice Reading (TTS)** feature, you need to have the following installed:
- **Linux**: `speech-dispatcher` (providing `spd-say`) and at least one engine like `espeak-ng` or `rhvoice` (e.g., `rhvoice-ru` for high-quality Russian voices).
