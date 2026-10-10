#!/usr/bin/env bash

set -e

workers="${ZENDRIVER_TEST_WORKERS:-auto}"
if [ "$ZENDRIVER_PAUSE_AFTER_TEST" = "true" ]; then
  # pausing between tests only works when running in a single process
  workers=0
fi

command=( "$@" )
if [ "${#command[@]}" -eq 0 ]; then
  command=( pytest -n "$workers" --cov=zendriver --cov-report=xml )
fi

chrome_executable=$(uv run python -c "from zendriver.core.config import find_executable;print(find_executable())")
echo "Chrome executable: $chrome_executable"

chrome_version=$(uv run python -c "import os, subprocess, sys; path = r'$chrome_executable'; print(subprocess.run([path, '--version'], capture_output=True, text=True).stdout.strip()) if os.name != 'nt' else print('SKIP: Windows chrome.exe may not return version')")
echo "Chrome version: $chrome_version"

set -x
uv run ${command[@]}
