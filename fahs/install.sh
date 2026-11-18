#!/data/data/com.termux/files/usr/bin/bash
# تنصيب أداة فحص فـ Termux
set -e
URL="https://raw.githubusercontent.com/zaid5195/tajriba/ccr-ae29b074-06q1fo/fahs/fahs.py"
BIN="${PREFIX:-/data/data/com.termux/files/usr}/bin/fahs"

echo "[1/3] Python..."
command -v python >/dev/null 2>&1 || pkg install -y python

echo "[2/3] Arabic support..."
pip install -q "python-bidi==0.4.2" arabic-reshaper || echo "(skip: Arabic libs failed)"

echo "[3/3] Downloading fahs..."
curl -fsSL "$URL" -o "$BIN"
chmod +x "$BIN"

echo ""
echo "Done! Run:  fahs"
echo "Tip: run 'termux-setup-storage' first so fahs can scan your files."
