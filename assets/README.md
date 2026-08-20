# OfficeMitra brand assets

| File | Use |
| --- | --- |
| `officemitra-app-icon.png` | **Primary app icon** — OM monogram for desktop/taskbar |
| `officemitra.png` | Same as app icon (used by shortcuts) |
| `officemitra.ico` | Windows `.ico` for desktop shortcut, installer, setup wizard |
| `officemitra.icns` | macOS app icon (created by `installer/macos/build-macos.sh`) |
| `officemitra-logo-banner.png` | Wide logo with “OfficeMitra” wordmark — splash, website, docs |

The **OM** monogram is designed to stay readable at 32×32 px on the Windows desktop.

To rebuild the `.ico` from the app icon (requires Pillow):

```powershell
python -c "from PIL import Image; from pathlib import Path; p=Path('assets/officemitra-app-icon.png'); img=Image.open(p).convert('RGBA'); img.save(p.with_name('officemitra.ico'), format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
```
