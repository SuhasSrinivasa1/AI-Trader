from pathlib import Path

p = Path('delivery-momentum/app/src/main/java/com/suhas/nsedeliverymomentum/MainActivity.java')
s = p.read_text()
old = 'root.setOnApplyWindowInsetsListener((v,insets)->{android.graphics.Insets bars=insets.getInsets(WindowInsets.Type.systemBars());v.setPadding(dp(18),bars.top+dp(10),dp(18),bars.bottom+dp(24));return insets;});'
new = 'root.setOnApplyWindowInsetsListener((v,insets)->{int top=insets.getSystemWindowInsetTop(),bottom=insets.getSystemWindowInsetBottom();v.setPadding(dp(18),top+dp(10),dp(18),bottom+dp(24));return insets;});'
if old not in s:
    raise SystemExit('v1.1 inset anchor not found')
s = s.replace(old, new, 1)
p.write_text(s)
assert 'WindowInsets.Type.systemBars()' not in s
assert 'getSystemWindowInsetTop()' in s
assert 'getSystemWindowInsetBottom()' in s
print('Delivery Momentum v1.1 API26-safe system inset fix applied')
