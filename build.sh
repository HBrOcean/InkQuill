#!/usr/bin/env bash
# macOS / Linux 一键打包：./build.sh
set -e
cd "$(dirname "$0")"
echo "Installing dependencies ..."
python3 -m pip install -q -r requirements.txt pyinstaller
echo "Building ..."
python3 build.py
echo "Done. See ./dist/"
