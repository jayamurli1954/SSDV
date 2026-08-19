# OfficeMitra brand assets

| File | Use |
| --- | --- |
| `officemitra.png` | Marketing, docs, about screens |
| `officemitra.ico` | Windows desktop shortcut, setup wizard, `OfficeMitra-Setup.exe` |

To rebuild the `.ico` from the PNG (requires Pillow):

```powershell
python -c "from PIL import Image; from pathlib import Path; p=Path('assets/officemitra.png'); img=Image.open(p).convert('RGBA'); img.save(p.with_suffix('.ico'), format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
```
