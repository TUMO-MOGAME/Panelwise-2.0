#!/usr/bin/env bash
# hack: this event's clock and checks. Run  ./hack --help  for the commands.
#
# The work is done by .hack/hack.py, which needs Python 3.11+ (for tomllib). When the system
# Python is older, uv fetches a suitable one. The first run may download it, so run
# ./hack status once the night before.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  exec python3 "$here/.hack/hack.py" "$@"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --quiet --no-project --python '>=3.11' "$here/.hack/hack.py" "$@"
fi
echo "hack: needs Python 3.11 or newer, or uv to fetch one (https://docs.astral.sh/uv/)" >&2
exit 1
