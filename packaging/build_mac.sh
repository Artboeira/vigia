#!/bin/bash
# Gera Vigia.app para a arquitetura deste Mac, com janela nativa (pywebview). Rode num Mac:
#   bash packaging/build_mac.sh
# Precisa de Python 3.10+ (python.org ou Homebrew). Baixa PyInstaller, Pillow e pywebview num venv.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="${PY:-python3}"

"$PY" -m venv build/venv
. build/venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet pyinstaller pillow pywebview

python -m unittest discover -s tests -t . >/dev/null
python packaging/make_icon.py build/icon.png

pyinstaller --noconfirm --windowed --name "Vigia" --icon "$ROOT/build/icon.png" \
  --osx-bundle-identifier br.com.estudioab.vigia --paths "$ROOT" \
  --add-data "$ROOT/vigia/infra/web/static:vigia/infra/web/static" \
  --distpath "$ROOT/dist" --workpath "$ROOT/build/work" --specpath "$ROOT/build" \
  "$ROOT/packaging/run_vigia.py"

APP="$ROOT/dist/Vigia.app"
PLIST="$APP/Contents/Info.plist"
# macOS 15+: pedido de permissão de Rede Local (anúncio UDP 7654 e controle TCP 7765)
MSG="O Vigia escuta as DACs Ether Dream na rede local."
/usr/libexec/PlistBuddy -c "Add :NSLocalNetworkUsageDescription string '$MSG'" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :NSLocalNetworkUsageDescription '$MSG'" "$PLIST"
codesign --force --deep -s - "$APP"  # assinatura ad-hoc: obrigatória no Apple Silicon

ZIP="$ROOT/dist/Vigia-mac-$(uname -m).zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
echo "ok: $ZIP"
