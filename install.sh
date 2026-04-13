#!/bin/bash
# WhisperTranscribe — Instalador para macOS
# Instala todas as dependencias e gera o .app

set -e

echo ""
echo "================================================"
echo "  WhisperTranscribe — Instalador macOS"
echo "================================================"
echo ""

# --- Verificar macOS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERRO: WhisperTranscribe funciona apenas no macOS com Apple Silicon."
    exit 1
fi

# --- Verificar Apple Silicon ---
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo "AVISO: WhisperKit funciona melhor em Apple Silicon (M1/M2/M3/M4)."
    echo "Em Intel, a performance pode ser significativamente menor."
    read -p "Deseja continuar? (s/n) " -n 1 -r
    echo
    [[ ! $REPLY =~ ^[Ss]$ ]] && exit 1
fi

# --- Verificar Homebrew ---
if ! command -v brew &>/dev/null; then
    echo "Homebrew nao encontrado. Instalando..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# --- Instalar WhisperKit CLI ---
echo "[1/5] Instalando WhisperKit CLI..."
if command -v whisperkit-cli &>/dev/null; then
    echo "  -> whisperkit-cli ja instalado ($(whisperkit-cli --version 2>/dev/null || echo 'ok'))"
else
    brew install whisperkit-cli
    echo "  -> whisperkit-cli instalado com sucesso!"
fi

# --- Instalar yt-dlp ---
echo "[2/5] Instalando yt-dlp..."
if command -v yt-dlp &>/dev/null; then
    echo "  -> yt-dlp ja instalado"
else
    brew install yt-dlp
    echo "  -> yt-dlp instalado com sucesso!"
fi

# --- Verificar Python 3 ---
echo "[3/5] Verificando Python 3..."
if ! command -v python3 &>/dev/null; then
    echo "  -> Python 3 nao encontrado. Instalando via Homebrew..."
    brew install python@3.12
fi

PYTHON_VERSION=$(python3 --version 2>&1)
echo "  -> $PYTHON_VERSION"

# --- Verificar tkinter ---
echo "[4/5] Verificando tkinter..."
if ! python3 -c "import tkinter" &>/dev/null; then
    echo "  -> tkinter nao encontrado. Instalando python-tk..."
    brew install python-tk@3.12
fi
echo "  -> tkinter OK"

# --- Criar venv e instalar deps ---
echo "[5/5] Criando ambiente e compilando o app..."
VENV_DIR="$(pwd)/.venv"

python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

pip install --quiet customtkinter py2app

# --- Compilar .app ---
echo ""
echo "Compilando WhisperTranscribe.app..."
python3 setup.py py2app 2>&1 | grep -E "^(Done|error|Error)" || true

if [[ -d "dist/WhisperTranscribe.app" ]]; then
    echo ""
    echo "================================================"
    echo "  BUILD CONCLUIDO!"
    echo "================================================"
    echo ""
    echo "O app foi gerado em: dist/WhisperTranscribe.app"
    echo ""

    echo "Instalando em /Applications..."
    rm -rf /Applications/WhisperTranscribe.app
    cp -R dist/WhisperTranscribe.app /Applications/
    echo ""
    echo "Instalado em /Applications/WhisperTranscribe.app"
    echo "Voce pode abrir pelo Launchpad ou Spotlight!"
else
    echo ""
    echo "ERRO: Falha ao compilar o app."
    echo "Verifique os erros acima e tente novamente."
    exit 1
fi

echo ""
echo "Para instalar a extensao do Chrome:"
echo "  1. Abra chrome://extensions no Chrome"
echo "  2. Ative o 'Modo do desenvolvedor' (canto superior direito)"
echo "  3. Clique em 'Carregar sem compactacao'"
echo "  4. Selecione a pasta: $(pwd)/extension"
echo ""
echo "Pronto! Abra o WhisperTranscribe e comece a transcrever."
echo ""
