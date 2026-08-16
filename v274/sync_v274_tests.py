from pathlib import Path

p = Path('android-stable/app/src/test/java/com/suhas/multyfiautobuy/stable/SignalParserTest.java')
s = p.read_text(encoding='utf-8')
old_name = 'parsesCompleteSignalWithDefaultOnePointFivePercentBuffer'
assert old_name in s
s = s.replace(old_name, 'parsesCompleteSignalWithFixedHalfPercentBuffer', 1)
assert 'assertEquals(694.20d, signal.maxBuyPrice, 0.001d);' in s
s = s.replace('assertEquals(694.20d, signal.maxBuyPrice, 0.001d);',
              'assertEquals(687.40d, signal.maxBuyPrice, 0.001d);', 1)
assert 'contains("planned ₹9718.80")' in s
s = s.replace('contains("planned ₹9718.80")', 'contains("planned ₹9623.60")', 1)
p.write_text(s, encoding='utf-8')
print('Synchronized legacy SignalParser default-buffer test to v2.7.4 fixed +0.50% policy')
