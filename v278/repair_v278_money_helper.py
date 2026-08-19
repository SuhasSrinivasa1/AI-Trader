from pathlib import Path

p = Path('android-stable/app/src/main/java/com/suhas/multyfiautobuy/stable/Stage2Engine.java')
s = p.read_text()

if 'private static String money(double value)' not in s:
    anchor = '    private static SharedPreferences prefs(Context context) {\n'
    assert anchor in s, 'Stage2Engine prefs anchor missing'
    helper = '''    private static String money(double value) {\n        return String.format(Locale.US, "%.2f", value);\n    }\n\n'''
    s = s.replace(anchor, helper + anchor, 1)
    p.write_text(s)

s = p.read_text()
assert 'private static String money(double value)' in s
assert 'String.format(Locale.US, "%.2f", value)' in s
print('Repaired v2.7.8 Stage2Engine money formatter helper')
