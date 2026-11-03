#!/usr/bin/env bash
# install-hooks.sh -- run once per clone, by every contributor.
#
# `core.hooksPath` is local config: it lives in .git/config, which is NOT cloned.
# So the person who bootstrapped the repo has the gate and nobody else does, silently,
# until they run this. That is why it is a script with a self-test rather than a line
# of prose in a README that everyone skims past.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

echo "Installing the pre-push gate for this clone..."

[ -f .githooks/pre-push ] || { echo "!! .githooks/pre-push is missing."; exit 1; }
[ -f scripts/gate.sh ]    || { echo "!! scripts/gate.sh is missing."; exit 1; }
[ -f .githooks/post-merge ]       || { echo "!! .githooks/post-merge is missing."; exit 1; }
[ -f scripts/prune-branches.sh ]  || { echo "!! scripts/prune-branches.sh is missing."; exit 1; }

chmod +x .githooks/pre-push .githooks/post-merge scripts/gate.sh scripts/prune-branches.sh
git config core.hooksPath .githooks
echo "  core.hooksPath = $(git config core.hooksPath)"

# Merged branches are deleted everywhere (docs/git-workflow.md, "Merged branches are
# deleted"). fetch.prune drops remote-tracking refs for branches deleted on the server;
# the post-merge hook then deletes the local branches that merged.
git config fetch.prune true
echo "  fetch.prune    = $(git config fetch.prune)"

# Prove it actually works, rather than assuming. A gate nobody has ever seen fire is
# indistinguishable from no gate.
echo
echo "Self-test 1/2: does the hook reject a push to main?"
if printf 'refs/heads/main %s refs/heads/main %s\n' \
     "$(git rev-parse HEAD)" "$(git rev-parse HEAD)" \
     | bash .githooks/pre-push origin >/dev/null 2>&1; then
  echo "  FAIL -- the hook allowed a push to main. Do not rely on it; fix it first."
  exit 1
else
  echo "  ok -- pushes to main are rejected."
fi

echo
echo "Self-test 2/2: what will the gate actually run here?"
bash scripts/gate.sh --list | sed 's/^/  /'

# The server half of branch deletion is a repo setting, which only an admin can change.
# Check it rather than assume it -- the same reason the hook is fired above.
echo
echo "Check: does the server delete a branch when its pull request merges?"
auto_delete=""
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  auto_delete="$(gh api 'repos/{owner}/{repo}' --jq .delete_branch_on_merge 2>/dev/null || true)"
fi
case "$auto_delete" in
  true)
    echo "  ok -- merged branches are deleted on the server." ;;
  false)
    echo "  NO -- merged branches pile up on the server. A repo admin turns it on with:"
    echo "    gh repo edit --delete-branch-on-merge" ;;
  *)
    echo "  unknown -- gh is missing, not logged in, or this remote isn't on GitHub. Check by"
    echo "  hand: repo Settings -> General -> \"Automatically delete head branches\"." ;;
esac

cat <<'EOF'

Done. From here:
  - every push runs scripts/gate.sh first, and a check that cannot run counts as failed
  - pushes to main/master are rejected -- branch and open a PR
  - 'git pull' on main deletes your local branches that have merged (scripts/prune-branches.sh)
  - CI runs the same scripts/gate.sh, so local green and pipeline green mean the same thing

If the gate is ever wrong, fix scripts/gate.sh -- do not reach for --no-verify twice.
EOF
