#!/bin/bash
# Doppelklick-Starter für Cherry Mac Remapper (macOS)
cd "$(dirname "$0")" || exit 1
python3 cherry_remapper.py serve
