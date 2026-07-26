from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent
runpy.run_path(str(ROOT / "apply_v1_6_patch_wrapper.py"), run_name="__main__")
layout = ROOT / "app/src/main/res/layout/activity_main.xml"
text = layout.read_text(encoding="utf-8")
text = text.replace('android:text="TIME-WINDOW SIZING & ENTRY"',
                    'android:text="TIME-WINDOW SIZING &amp; ENTRY"')
layout.write_text(text, encoding="utf-8")
print("Finalized escaped Android XML for Multyfi AutoBuy S24 v1.6.0.")
