#!/usr/bin/env bash
# Download the MaleCNS v1.0 flat connectome files into data/ (resumable with curl -C -).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
B=https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome
for f in body-annotations-male-cns-v1.0-minconf-0.5.feather \
         body-neurotransmitters-male-cns-v1.0.feather \
         connectome-weights-male-cns-v1.0-minconf-0.5.feather; do
  echo "== $f"
  curl -fL --retry 5 --retry-delay 5 -C - -o "data/$f" "$B/$f"
done
ls -lh data/
