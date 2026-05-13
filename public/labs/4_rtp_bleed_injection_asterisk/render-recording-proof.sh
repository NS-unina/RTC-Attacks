#!/bin/sh
set -eu

INPUT_PATH=${1:-}
OUTPUT_PATH=${2:-}

if [ -z "$INPUT_PATH" ]; then
  INPUT_PATH=$(ls -1t recordings/*.wav 2>/dev/null | head -n 1 || true)
fi

if [ -z "$INPUT_PATH" ] || [ ! -f "$INPUT_PATH" ]; then
  echo "No recording found" >&2
  exit 1
fi

if [ -z "$OUTPUT_PATH" ]; then
  OUTPUT_PATH="recordings/$(basename "$INPUT_PATH" .wav)-proof.png"
fi

ffmpeg -y -i "$INPUT_PATH" \
  -filter_complex "[0:a]showwavespic=s=1600x240:colors=DodgerBlue[wave];[0:a]showspectrumpic=s=1600x900:legend=disabled:mode=combined:color=intensity[spec];[wave][spec]vstack=inputs=2" \
  -frames:v 1 "$OUTPUT_PATH" >/dev/null 2>&1

ffprobe -v error \
  -show_entries format=filename,duration,size:stream=codec_name,sample_rate,channels \
  -of default=noprint_wrappers=1 "$INPUT_PATH" >"${OUTPUT_PATH%.png}.txt"

printf '%s\n' "$OUTPUT_PATH"
