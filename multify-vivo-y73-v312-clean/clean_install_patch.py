from pathlib import Path

root = Path("android")

# Install alongside earlier debug-signed builds to avoid Android signature-conflict errors.
p = root / "app/build.gradle.kts"
s = p.read_text()
s = s.replace('applicationId = "com.multify.traderpro"', 'applicationId = "com.multify.traderpro.vivoy73"')
s = s.replace("versionCode = 312", "versionCode = 3121")
s = s.replace('versionName = "3.1.2-vivo-y73"', 'versionName = "3.1.2-vivo-y73-clean"')
p.write_text(s)

# Give the clean-install build a visibly distinct label.
p = root / "app/src/main/res/values/strings.xml"
s = p.read_text()
s = s.replace('<string name="app_name">Multify Trader Pro</string>',
              '<string name="app_name">Multify Trader Pro Y73</string>')
p.write_text(s)

print("Applied Vivo Y73 clean-install package identity.")
