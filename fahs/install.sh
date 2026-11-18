#!/data/data/com.termux/files/usr/bin/bash
# تنصيب أداة فحص فـ Termux
set -e
BASE="https://raw.githubusercontent.com/zaid5195/tajriba/ccr-ae29b074-06q1fo/fahs"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DIR="$PREFIX/share/fahs"
BIN="$PREFIX/bin/fahs"

echo "[1/3] Python..."
command -v python >/dev/null 2>&1 || pkg install -y python

echo "[2/3] Arabic support..."
pip install -q "python-bidi==0.4.2" arabic-reshaper || echo "(skip: Arabic libs failed)"

echo "[3/3] Downloading fahs..."
mkdir -p "$DIR"
for f in fahs.py fahs_web.py fahs_web.html; do
  curl -fsSL "$BASE/$f?$(date +%s)" -o "$DIR/$f"
done
cat > "$BIN" <<EOS
#!/data/data/com.termux/files/usr/bin/bash
exec python "$DIR/fahs.py" "\$@"
EOS
chmod +x "$BIN"

echo ""
echo "Done! Run:  fahs        (menu)"
echo "      or:   fahs --web  (dashboard in your browser)"
echo "Tip: run 'termux-setup-storage' first so fahs can scan your files."
