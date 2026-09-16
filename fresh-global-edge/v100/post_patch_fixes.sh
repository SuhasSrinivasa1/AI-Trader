#!/usr/bin/env bash
set -euo pipefail

P='app/src/main/java/com/suhas/ucsentinel/data/local/AppPreferences.kt'
sed -i \
  -e 's/:List<StrategySetup>=/:List<StrategySetup> =/g' \
  -e 's/:List<TradingStrategyDefinition>=/:List<TradingStrategyDefinition> =/g' \
  "$P"
