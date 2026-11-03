#!/usr/bin/env bash
# gate.sh -- the one build script. Everything that decides "is this code good enough
# to leave my machine / to merge" runs here, and ONLY here.
#
#   .githooks/pre-push      -> runs this before a push
#   .github/workflows/ci.yml -> runs this on every push and PR
#
# That is the whole point of the file: the local gate and the pipeline cannot drift
# apart, because there is only one of them. (Curriculum 201, Build Scripts: a build
# that only works in one person's environment is not a build.)
#
# Usage:
#   bash scripts/gate.sh                          # sweep placeholders over the whole tree
#   bash scripts/gate.sh --changed-files <path>   # sweep only the paths listed in <path>
#   bash scripts/gate.sh --list                   # print what it would run, run nothing
#   bash scripts/gate.sh --install-deps           # install every project's deps (CI uses this)
#   bash scripts/gate.sh --stage python|node|repo  # one stage only (CI runs the three at once)
#
# Stages: python (each Python project's ruff, pyright and pytest, with the test Postgres), node
# (each Node project's lint, test and build), repo (the placeholder and secret sweeps, the
# vulnerability scan, the duplication check and the image builds). With no --stage, all three,
# one after the other -- the pre-push hook. A stage that runs zero checks fails, as the gate does.
#
# Exit codes: 0 = every applicable check ran and passed. 1 = something failed, or a
# check that should have run could not run. There is deliberately no third state --
# see "the skip rule" below.
#
# ---------------------------------------------------------------------------
# THE SKIP RULE (read this before you "fix" the script by making it lenient)
#
#   A check that did not run is a FAILED check, not a passed one.
#
# The gate never reports green because it found nothing to do. If a directory has a
# pyproject.toml but no usable interpreter, that is a broken environment and the push
# is blocked. If the whole repo has no project manifest at all but the commits being
# pushed contain source files, that is a misconfigured gate and the push is blocked.
# The only silent pass is a repo that genuinely has no code in it yet.
#
# The earlier version of this gate did the opposite -- it skipped anything it could not
# run, printed "Test gate passed", and let untested code through. That is the defect
# this file exists to make impossible.
# ---------------------------------------------------------------------------

set -u

# git quotes any path holding a non-ASCII byte ("caf\303\251.py") unless told not to, and
# a quoted path matches no file on disk -- it would drop out of every sweep silently.
git() { command git -c core.quotePath=false "$@"; }

root="$(git rev-parse --show-toplevel)"
cd "$root"

changed_files_list=""
list_only=0
install_only=0
stage=""

while [ $# -gt 0 ]; do
  case "$1" in
    --changed-files) changed_files_list="${2:-}"; shift 2 ;;
    --list)          list_only=1; shift ;;
    --install-deps)  install_only=1; shift ;;
    --stage)
      stage="${2:-}"; shift 2
      case "$stage" in python|node|repo) ;; *) echo "gate.sh: --stage is python, node or repo, not '$stage'" >&2; exit 2 ;; esac
      ;;
    -h|--help)       sed -n '2,42p' "$0"; exit 0 ;;
    *) echo "gate.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

fail=0
ran=0
manifests=0

# Packages with no test suite yet, each declared against the task ID that will close
# the gap: UNTESTED["apps/web"]="T031". Empty by default -- see check_node(). This is
# the AGENTS.md 2a "explicitly declared stub with a follow-up task" rule, applied to a
# whole package. An entry here does not make the gate pass quietly; it still reports
# the gap on every run.
declare -A UNTESTED=()

# Tunables for the checks below. They live here, not in CI or the hook, like everything else.
DUPLICATION_THRESHOLD=5   # max % of duplicated lines across the repo's source (jscpd)
JSCPD_VERSION=5.2.0       # pinned: npx fetches exactly this version, never "latest"

# Committed lockfiles of the projects found, scanned together by vuln_scan().
LOCKFILES=()

say()  { printf '%s\n' "$*"; }
step() { printf '\n-> %s\n' "$*"; }
bad()  { printf '!! %s\n' "$*"; }

# Directories that can hold a project of their own. Root first, then the layout
# docs/project-structure.md describes, then the two flat layouts people actually use
# before the microservices split happens.
project_dirs() {
  printf '%s\n' "$root"
  for d in "$root"/services/* "$root"/apps/* "$root"/packages/* \
           "$root/backend" "$root/frontend" "$root/web" "$root/api"; do
    [ -d "$d" ] && printf '%s\n' "$d"
  done
}

# ---------------------------------------------------------------- Python ----
# Resolved in strict order, most-pinned first. A bare `python` on PATH is the LAST
# resort and never the assumption: on Debian/Ubuntu derivatives `python` does not
# exist at all (only `python3`), which is exactly how the old gate silently skipped
# every Python suite it was supposed to run.
py_runner=""      # how to invoke a tool, e.g. "uv run --frozen" or "/path/.venv/bin/python -m"
py_kind=""
py_venv=""        # the virtualenv the runner belongs to, when it is one

# Run a Python tool in $1, with the environment the tool expects.
#
# Picking the right interpreter is not enough for tools that *inspect* the
# environment rather than just importing from it -- pyright and pip-audit both do.
# Invoked as a bare `.venv/bin/python -m pyright`, pyright resolves imports against
# the system environment and reports phantom "could not be resolved" errors for
# packages that are plainly installed. Setting VIRTUAL_ENV is what `uv run` does for
# you, and what this reproduces.
pyrun() {
  local d="$1"; shift
  if [ -n "$py_venv" ]; then
    ( cd "$d" && VIRTUAL_ENV="$py_venv" PATH="$py_venv/bin:$PATH" $py_runner "$@" )
  else
    ( cd "$d" && $py_runner "$@" )
  fi
}

is_python_project() {
  [ -f "$1/pyproject.toml" ] || [ -f "$1/requirements.txt" ] || [ -f "$1/setup.py" ]
}

resolve_python() {
  local dir="$1"
  py_runner=""; py_kind=""; py_venv=""

  if [ -x "$dir/.venv/bin/python" ]; then
    py_runner="$dir/.venv/bin/python -m"; py_kind="venv ($dir/.venv)"; py_venv="$dir/.venv"; return 0
  fi
  if [ -x "$root/.venv/bin/python" ]; then
    py_runner="$root/.venv/bin/python -m"; py_kind="venv ($root/.venv)"; py_venv="$root/.venv"; return 0
  fi
  if [ -f "$dir/uv.lock" ] && command -v uv >/dev/null 2>&1; then
    py_runner="uv run --frozen"; py_kind="uv (uv.lock)"; return 0
  fi
  if command -v uv >/dev/null 2>&1 && [ -f "$dir/pyproject.toml" ]; then
    py_runner="uv run"; py_kind="uv"; return 0
  fi
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import pytest" >/dev/null 2>&1; then
      py_runner="$candidate -m"; py_kind="$candidate on PATH"; return 0
    fi
  done
  return 1
}

check_python() {
  local dir="$1" rel="$2" rc
  is_python_project "$dir" || return 0
  manifests=$((manifests + 1))

  if ! resolve_python "$dir"; then
    bad "$rel has a Python project but no usable interpreter."
    bad "   Tried: $dir/.venv, $root/.venv, uv, python3+pytest, python+pytest."
    bad "   Fix the environment -- a gate that cannot run is not a gate that passed."
    bad "   e.g.  uv venv .venv && uv pip install -e '.[dev]'"
    fail=1
    return 0
  fi
  say "   python: $py_kind"

  if [ "$list_only" -eq 1 ]; then say "   would run: ruff check, ruff format --check, pyright, pytest ($rel)"; return 0; fi

  # Static analysis is part of the gate, not a nicety. Code rots one commit at a
  # time (Curriculum 201, Code Analysis); the cheapest place to catch it is here.
  if pyrun "$dir" ruff --version >/dev/null 2>&1; then
    step "ruff check ($rel)"
    pyrun "$dir" ruff check . || fail=1
    step "ruff format --check ($rel)"
    pyrun "$dir" ruff format --check . || fail=1
    ran=$((ran + 1))
  else
    # The skip rule covers lint exactly as it covers tests. This used to print
    # "skipping lint" and carry on -- a skipped check reporting green.
    bad "$rel has no ruff in its environment, so its lint and format checks cannot run."
    bad "   Add it as a dev dependency:  uv add --dev ruff   (or list it in requirements.txt)"
    fail=1
  fi

  # Type checking -- the tool pyrun() sets VIRTUAL_ENV for. It catches the call that
  # passes a str where the signature says int, which lint can't see and a test only
  # sees if someone thought to write that test.
  if pyrun "$dir" pyright --version >/dev/null 2>&1; then
    step "pyright ($rel)"
    pyrun "$dir" pyright || fail=1
    ran=$((ran + 1))
  else
    bad "$rel has no pyright in its environment, so its type check cannot run."
    bad "   Add it as a dev dependency:  uv add --dev pyright   (or list it in requirements.txt)"
    fail=1
  fi

  step "pytest ($rel)"
  pyrun "$dir" pytest -q
  rc=$?
  ran=$((ran + 1))
  if [ "$rc" -eq 5 ]; then
    # 5 == "no tests collected". Legitimate only while a package genuinely has no
    # suite yet. It is reported loudly so it cannot quietly become permanent.
    bad "   no tests collected in $rel -- if this package has behaviour, it needs tests."
  elif [ "$rc" -ne 0 ]; then
    fail=1
  fi
}

# ------------------------------------------------------------------ Node ----
# The package manager is whatever the committed lockfile says it is, not npm by
# assumption. Running `npm run build` in a pnpm workspace either fails outright or
# silently resolves a different dependency tree than the one that was locked.
node_pm() {
  local dir="$1"
  if   [ -f "$dir/pnpm-lock.yaml" ] || [ -f "$root/pnpm-lock.yaml" ]; then echo pnpm
  elif [ -f "$dir/yarn.lock" ]      || [ -f "$root/yarn.lock" ];      then echo yarn
  elif [ -f "$dir/bun.lock" ] || [ -f "$dir/bun.lockb" ] \
       || [ -f "$root/bun.lock" ] || [ -f "$root/bun.lockb" ];        then echo bun
  else echo npm
  fi
}

# Does the package.json in $1 declare script $2? Ask package.json directly:
# `npm test --if-present` exits 0 when there is no test script at all, which reads
# as a pass.
has_script() {
  node -e 'const p=require(process.argv[1]);process.exit(p.scripts&&p.scripts[process.argv[2]]?0:1)' \
    "$1/package.json" "$2" 2>/dev/null
}

check_node() {
  local dir="$1" rel="$2" pm
  [ -f "$dir/package.json" ] || return 0
  manifests=$((manifests + 1))

  pm="$(node_pm "$dir")"
  if ! command -v "$pm" >/dev/null 2>&1; then
    bad "$rel is locked to '$pm' (its lockfile says so) but '$pm' is not on PATH."
    bad "   Install it, or the gate cannot run this package's checks."
    fail=1
    return 0
  fi

  # node_modules is checked per directory, not at the repo root. A monorepo with
  # apps/web/node_modules and nothing at the root used to skip every JS suite.
  if [ ! -d "$dir/node_modules" ] && [ ! -d "$root/node_modules" ]; then
    bad "$rel has a package.json but no installed dependencies -- its suite cannot run."
    bad "   Run '$pm install' in $rel (or at the workspace root)."
    fail=1
    return 0
  fi

  if ! command -v node >/dev/null 2>&1; then
    bad "$rel has a package.json but node is not on PATH -- its suite cannot run."
    fail=1
    return 0
  fi

  local has_lint=no has_test=no has_build=no
  has_script "$dir" lint  && has_lint=yes
  has_script "$dir" test  && has_test=yes
  has_script "$dir" build && has_build=yes

  if [ "$list_only" -eq 1 ]; then
    say "   would run ($pm): $( [ "$has_lint" = yes ] && printf 'lint ' )$( [ "$has_test" = yes ] && printf 'test ' )$( [ "$has_build" = yes ] && printf 'build ' )($rel)"
    [ "$has_lint" = no ] && say "   (no 'lint' script -- would FAIL)"
    [ "$has_test" = no ] && say "   (no 'test' script -- would FAIL)"
    return 0
  fi

  # Static analysis runs before the tests, as it does for Python. The gate can't know
  # which JS tools a package uses, so the package declares them in its `lint` script
  # -- and a package without one fails, the same way a Python project without ruff does.
  if [ "$has_lint" = yes ]; then
    step "$pm run lint ($rel)"
    ( cd "$dir" && "$pm" run lint ) || fail=1
    ran=$((ran + 1))
  else
    bad "$rel declares no 'lint' script, so its code ships unanalysed."
    bad "   Add one that runs its static checks, e.g."
    bad "   \"lint\": \"eslint . && prettier --check . && tsc --noEmit\""
    fail=1
  fi

  if [ "$has_test" = yes ]; then
    step "$pm test ($rel)"
    ( cd "$dir" && "$pm" test ) || fail=1
    ran=$((ran + 1))
  else
    # Untested code is the thing the gate exists to stop. A package that declares no
    # test script does not "have no tests to run" -- it has tests nobody wrote.
    #
    # The single exception mirrors AGENTS.md 2a's rule for stubs: it is allowed only if
    # it has been *explicitly declared* against a follow-up task ID. Set UNTESTED in a
    # project-local block above, e.g.
    #     UNTESTED["apps/web"]="T031"
    # That keeps the gap loud on every single run and attached to a task somebody owns,
    # which is the opposite of silencing it with a fake "test" script.
    local declared="${UNTESTED[$rel]:-}"
    if [ -n "$declared" ]; then
      bad "$rel has no test suite -- declared, tracked as $declared."
      bad "   Its behaviour is unproven. This exemption is not a pass; close $declared."
    else
      bad "$rel declares no 'test' script, so its code ships unproven."
      bad "   Write the suite. If it genuinely cannot be written yet, the package is"
      bad "   BLOCKED, not done: add a task for it and declare it via UNTESTED[\"$rel\"]."
      fail=1
    fi
  fi

  if [ "$has_build" = yes ]; then
    step "$pm run build ($rel)"
    ( cd "$dir" && "$pm" run build ) || fail=1
    ran=$((ran + 1))
  fi
}

# ------------------------------------------------------------ file lists ----
# Paths travel through this script as newline-separated lists and are handed to grep and
# jscpd as arrays -- never as one space-joined string. The sweeps used to build
# `existing="$existing $root/$f"` and expand it unquoted, so a repo cloned into
# "~/projects/88 redesign" handed grep the fragments ".../88" and "redesign/src/x.html",
# grep could open neither, and both sweeps printed "clean" having read nothing.
#
# Read a newline-separated list of repo-relative paths on stdin; fill the array named
# $1 with the absolute path of each one that exists. Blank lines are dropped.
existing_files() {
  local -n _out="$1"
  local f
  _out=()
  while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$root/$f" ] && _out+=("$root/$f")
  done
  return 0
}

# ---------------------------------------------------------- placeholders ----
# AGENTS.md 2a is the kit's central rule -- nothing ships with a stub standing in for
# real work -- and until now nothing enforced it mechanically. This does.
#
# Note it sweeps the files being *pushed*, not `git diff --cached`: at pre-push time
# the index is empty, so a sweep written that way reads zero files and always passes.
placeholder_sweep() {
  step "placeholder sweep"
  local files rc
  local -a existing

  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    files="$(cat "$changed_files_list")"
  else
    say "   no change list given -- sweeping the whole tracked tree"
    files="$(git ls-files)"
  fi

  # Excluded: markdown and docs (prose about TODOs is not a TODO), fixtures and
  # mocks (stand-in data is their job), and the kit's own tooling -- the gate, and the
  # setup script that explains the no-placeholder rule to whoever runs it -- which
  # contain the very words being searched for and would otherwise always fail on
  # themselves. setup-project.sh used to be swept, and failed every new project's
  # first CI run on the word "TODO" in its own instructions.
  files="$(printf '%s\n' "$files" \
            | grep -Ev '^(docs/|legacy/|\.githooks/|\.github/|scripts/gate\.sh$|setup-project\.sh$)' \
            | grep -Ev '(^|/)(fixtures|mocks|__mocks__|testdata)/' \
            | grep -Ev '\.(md|txt|lock|svg|png|jpg|jpeg|gif|webp|ico)$' || true)"

  existing_files existing <<< "$files"
  [ "${#existing[@]}" -gt 0 ] || { say "   nothing to sweep"; return 0; }

  # `XXX` is deliberately NOT in this list. It collides with real data far too often --
  # ISO 4217's "no currency" code, redacted digits, placeholder hostnames -- and a sweep
  # that cries wolf gets disabled, which costs more than the few stubs it would catch.
  #
  # grep exits 0 on a match, 1 on none, and 2 when it could not read a file. Only 1 is
  # clean: treating 2 as "no match" is how this sweep passed without reading anything.
  grep -nE '\b(TODO|FIXME|HACK|NotImplementedError|not implemented)\b' -- "${existing[@]}"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    bad "Placeholders found in the code being pushed."
    bad "   A task closed on a stub is BLOCKED, not done (AGENTS.md 2a)."
    bad "   If a stub is genuinely declared by the task, name its follow-up task ID beside it"
    bad "   and it stops being a placeholder -- but say so, do not hide it."
    fail=1
  elif [ "$rc" -ne 1 ]; then
    bad "The placeholder sweep could not read the files above (grep exit $rc)."
    bad "   A sweep that did not read the code is a failed sweep, not a clean one."
    fail=1
  else
    say "   clean"
  fi
  ran=$((ran + 1))
}

# --------------------------------------------------------------- secrets ----
# Curriculum 200, Secrets and Password Management: a secret is anything that must stay
# private, and the cost of leaking one is not "fix and move on" -- once it is in git
# history it is compromised and must be rotated. So this runs before the push, which is
# the last moment it is still cheap.
#
# Pattern-matching cannot catch every secret and does not claim to. It catches the ones
# that actually leak in practice: a committed .env, a pasted key, a hardcoded password.
secret_sweep() {
  step "secret sweep"
  local files hits=0 rc
  local -a existing

  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    files="$(cat "$changed_files_list")"
  else
    files="$(git ls-files)"
  fi

  # Committed env files are the single most common leak, and no content check is
  # needed -- the filename is the finding. `.env.example` is the intended pattern.
  local envfiles
  envfiles="$(printf '%s\n' "$files" | grep -E '(^|/)\.env($|\.)' \
               | grep -Ev '\.(example|sample|template)$' || true)"
  if [ -n "$envfiles" ]; then
    bad "   env file(s) staged for push -- these belong in .gitignore, never in git:"
    printf '%s\n' "$envfiles" | sed 's/^/     /'
    hits=1
  fi

  files="$(printf '%s\n' "$files" \
            | grep -Ev '^(docs/|legacy/|\.githooks/|\.github/|scripts/gate\.sh$)' \
            | grep -Ev '\.(md|lock|svg|png|jpg|jpeg|gif|webp|ico)$' || true)"
  existing_files existing <<< "$files"

  if [ "${#existing[@]}" -gt 0 ]; then
    # Well-known key shapes, plus assignment of a secret-ish name to a literal that
    # isn't obviously a placeholder or an env lookup. As in the placeholder sweep, grep
    # exit 2 means it could not read a file -- that fails the sweep instead of passing it.
    grep -nE \
        -e '(AKIA|ASIA)[0-9A-Z]{16}' \
        -e 'sk-[A-Za-z0-9_-]{20,}' \
        -e 'ghp_[A-Za-z0-9]{36}' \
        -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
        -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
        -- "${existing[@]}"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      bad "   the above matches the shape of a real credential (AWS / OpenAI / GitHub /"
      bad "   Slack token, or a private key). Rotate it -- assume it is already burned."
      hits=1
    elif [ "$rc" -ne 1 ]; then
      bad "   the credential scan could not read the files above (grep exit $rc)."
      hits=1
    fi
    grep -nEi '(api[_-]?key|secret|password|passwd|token|credential)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{12,}["'"'"']' \
        -- "${existing[@]}" \
        | grep -Eiv '(example|placeholder|changeme|your[_-]?|xxx|\*{4,}|dummy|fake|test|sample|<|\$\{|process\.env|os\.environ|getenv)'
    local -a pst=("${PIPESTATUS[@]}")
    if [ "${pst[0]}" -gt 1 ]; then
      bad "   the secret-literal scan could not read the files above (grep exit ${pst[0]})."
      hits=1
    fi
    if [ "${pst[1]}" -eq 0 ]; then
      bad "   a secret-looking literal is assigned in the code above."
      bad "   Read it from the environment instead, and rotate it if it is real."
      hits=1
    fi
  fi

  if [ "$hits" -ne 0 ]; then
    bad "Secrets must never enter git history -- rewriting the commit is not enough,"
    bad "   anything already pushed must be rotated. Fix before pushing."
    fail=1
  else
    say "   clean"
  fi
  ran=$((ran + 1))
}

# ------------------------------------------------------------- lockfiles ----
# Echo the committed lockfile pinning $1's dependencies of kind $2 (py | node): the
# directory's own, else the workspace root's. Committed only -- CI's install step
# generates a lockfile when none exists, and a generated one pins nothing anyone
# reviewed. requirements.txt counts only in the project's own directory, and only
# its == pins are exact enough to scan.
committed_lockfile() {
  local dir="$1" kind="$2" d f names path
  for d in "$dir" "$root"; do
    if [ "$kind" = py ]; then
      names="uv.lock poetry.lock pdm.lock Pipfile.lock"
      [ "$d" = "$dir" ] && names="$names requirements.txt"
    else
      names="pnpm-lock.yaml yarn.lock bun.lock package-lock.json npm-shrinkwrap.json"
    fi
    for f in $names; do
      path="${d#"$root"}"; path="${path#/}"; path="${path:+$path/}$f"
      if git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
        printf '%s\n' "$path"; return 0
      fi
    done
  done
  return 1
}

# Every project needs one. Without it there is nothing exact to scan for vulnerabilities,
# and nothing reproducible to install (architecture-defaults.md section 5) -- so a
# missing lockfile fails here rather than letting the scan quietly cover less.
collect_lockfiles() {
  local dir="$1" rel="$2" kind lock
  for kind in py node; do
    if [ "$kind" = py ]; then is_python_project "$dir" || continue
    else [ -f "$dir/package.json" ] || continue
    fi
    if lock="$(committed_lockfile "$dir" "$kind")"; then
      case " ${LOCKFILES[*]:-} " in *" $lock "*) ;; *) LOCKFILES+=("$lock") ;; esac
    else
      bad "$rel has no committed lockfile, so its dependencies cannot be scanned for known vulnerabilities."
      if [ "$kind" = py ]; then
        bad "   Create one with  uv lock  (or pin every line of requirements.txt with ==), and commit it."
      else
        bad "   Run '$(node_pm "$dir") install' and commit the lockfile it writes."
      fi
      fail=1
    fi
  done
}

# ------------------------------------------------------- vulnerabilities ----
# Every committed lockfile, checked against OSV (which aggregates the GitHub, PyPI and
# other advisory feeds). Unlike every other check here, the result can change while the
# code doesn't: an advisory published tonight fails tomorrow's push on a branch nobody
# touched. That is the point -- a vulnerable dependency is exactly as vulnerable in
# unchanged code.
#
# Exemptions live in osv-scanner.toml at the repo root, one [[IgnoredVulns]] block each,
# under the same rule as UNTESTED: the reason names the task that will close it, and every
# run prints it. An ignoreUntil date makes an exemption expire on its own.
osv_exemptions() {   # prints "id<TAB>reason" per [[IgnoredVulns]] block of $1
  awk '
    function flush() { if (inblock) printf "%s\t%s\n", id, reason; inblock = 0; id = ""; reason = "" }
    /^[[:space:]]*\[\[IgnoredVulns\]\]/ { flush(); inblock = 1; next }
    /^[[:space:]]*\[/                   { flush(); next }
    inblock && /^[[:space:]]*id[[:space:]]*=/     { v = $0; sub(/^[^=]*=[[:space:]]*/, "", v); gsub(/"/, "", v); id = v }
    inblock && /^[[:space:]]*reason[[:space:]]*=/ { v = $0; sub(/^[^=]*=[[:space:]]*/, "", v); gsub(/"/, "", v); reason = v }
    END { flush() }
  ' "$1"
}

vuln_scan() {
  step "dependency vulnerability scan (osv-scanner)"
  local config="$root/osv-scanner.toml" lock id reason rc
  local args=()

  if ! command -v osv-scanner >/dev/null 2>&1; then
    bad "osv-scanner is not on PATH, so dependencies cannot be checked for known vulnerabilities."
    bad "   Install it: https://google.github.io/osv-scanner/installation/"
    bad "   e.g.  go install github.com/google/osv-scanner/v2/cmd/osv-scanner@v2.5.1"
    fail=1
    return 0
  fi

  if [ -f "$config" ]; then
    args+=(--config "$config")
    while IFS=$'\t' read -r id reason; do
      if printf '%s' "$reason" | grep -qE '\bT[0-9]+\b'; then
        bad "   accepted: $id -- $reason"
      else
        bad "   $id is ignored in osv-scanner.toml, but its reason names no task."
        bad "   An exemption nobody owns is a vulnerability nobody fixes: reason = \"T0nn: ...\""
        fail=1
      fi
    done < <(osv_exemptions "$config")
  fi

  for lock in "${LOCKFILES[@]}"; do args+=(-L "$root/$lock"); done
  say "   lockfiles: ${LOCKFILES[*]}"

  osv-scanner scan source "${args[@]}"
  rc=$?
  ran=$((ran + 1))
  if [ "$rc" -eq 1 ]; then
    bad "Known vulnerabilities in the dependencies above. Upgrade to the fixed version --"
    bad "   or, only if none exists yet, declare it in osv-scanner.toml against a task."
    fail=1
  elif [ "$rc" -ne 0 ]; then
    bad "osv-scanner could not complete (exit $rc) -- usually no network. A scan that did not"
    bad "   run is a failed scan, not a clean one."
    fail=1
  fi
}

# ------------------------------------------------------------ duplication ----
# Copy-paste across the whole repo, measured by jscpd. AI assistants produce a local copy
# of logic far more readily than they reuse the shared version, and a multi-service repo
# hides the copy well: the same helper pasted into services/a and services/b passes every
# per-service check. So this runs once over all tracked source, and fails when duplicated
# lines exceed DUPLICATION_THRESHOLD percent.
#
# Not counted: tests (repeated, explicit setup is normal there), fixtures and mocks,
# vendored or built trees, and shadcn/ui's components/ui/ -- copied in from a registry and
# alike by design. A deliberate copy is marked in the code, with the reason beside it:
#     # jscpd:ignore-start -- <why this copy is intended>
#     # jscpd:ignore-end
duplication_check() {
  step "duplication check (jscpd $JSCPD_VERSION, threshold $DUPLICATION_THRESHOLD%)"
  local out rc tree
  local -a files

  mapfile -t files < <(git ls-files \
            | grep -E '\.(py|ts|tsx|js|jsx|mjs|cjs|go|rs|java|rb|php|c|cc|cpp|h|hpp|cs|kt|swift)$' \
            | grep -Ev '(^|/)(docs|legacy|fixtures|mocks|__mocks__|testdata|node_modules|vendor|dist|build|tests?|__tests__)/' \
            | grep -Ev '(^|/)components/ui/' \
            | grep -Ev '(\.(test|spec)\.[a-z]+|(^|/)test_[^/]*\.py|_test\.(py|go))$' || true)
  if [ "${#files[@]}" -eq 0 ]; then
    say "   no source files to compare"
    ran=$((ran + 1))
    return 0
  fi

  if ! command -v npx >/dev/null 2>&1; then
    bad "npx is not on PATH, so the duplication check (jscpd) cannot run. Install Node.js."
    fail=1
    return 0
  fi

  # jscpd reads a copy of exactly these files, laid out as in the repo, through one directory
  # argument. Handing it the files themselves broke on Windows: npx runs through cmd.exe, whose
  # command line stops at 8,191 characters, and the list passed that on 2026-10-19 (213 files,
  # 7,993 characters). cmd printed "The syntax of the command is incorrect." and jscpd never ran.
  tree="$(mktemp -d)"
  if ! ( cd "$root" && printf '%s\0' "${files[@]}" | xargs -0 cp --parents -t "$tree" ); then
    bad "Could not copy the source files for the duplication check (jscpd). A check that did not run is a failed check."
    fail=1
    rm -rf "$tree"
    return 0
  fi
  out="$(mktemp)"
  ( cd "$tree" && npx --yes "jscpd@$JSCPD_VERSION" --threshold "$DUPLICATION_THRESHOLD" \
      --reporters console --no-colors . ) 2>&1 | tee "$out"
  rc=${PIPESTATUS[0]}
  ran=$((ran + 1))
  rm -rf "$tree"
  if [ "$rc" -ne 0 ]; then
    if grep -q 'too many duplicates' "$out"; then
      bad "Duplicated code is over the threshold. Reuse the shared version instead of copying it,"
      bad "   or mark a deliberate copy with jscpd:ignore-start / jscpd:ignore-end and a reason."
    else
      bad "jscpd could not run (exit $rc) -- see above. A check that did not run is a failed check."
    fi
    fail=1
  fi
  rm -f "$out"
}

# ------------------------------------------------------------------ image ---
# The API is deployed from its Dockerfile, built by the host from main (docs/design/deploy.md
# §6, *The image*, T068). A Dockerfile that no longer builds, or an image missing a module the
# app imports, would otherwise be found only there, after the merge. So each project directory
# with a Dockerfile is built here, with that directory as the context (as compose builds it), and
# the image is started once to import the app. One check per Dockerfile; Docker is required.
image_dirs() {
  # Python projects only: the web's Dockerfile serves compose, and Vercel builds the web itself.
  while IFS= read -r dir; do
    [ -f "$dir/Dockerfile" ] && is_python_project "$dir" && printf '%s
' "$dir"
  done < <(project_dirs)
}

# Run in the image (deploy.md §6, *The image*): the app imports, and the files it reads at run time
# are there, the public styles included (T063).
IMAGE_PROBE='import pathlib, app.main
from app.comic.layout import FONT_PATH
from app.storyboard.styles import PUBLIC_STYLES, load_styles
for need in (FONT_PATH, pathlib.Path("alembic.ini"), pathlib.Path("migrations/env.py")):
    assert need.is_file(), f"missing in the image: {need}"
load_styles(PUBLIC_STYLES, None)'

image_check() {
  local dir="$1" rel="$2" tag err
  step "image build ($rel)"
  ran=$((ran + 1))
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    bad "Docker is needed to build the API's image ($rel/Dockerfile): start Docker."
    bad "   A check that did not run is a failed check."
    fail=1
    return 0
  fi
  tag="panelwise-gate/$(basename "$dir" | tr '[:upper:]' '[:lower:]'):check"
  err="$(mktemp)"
  if ! docker build -q -t "$tag" "$dir" >/dev/null 2>"$err"; then
    bad "$rel/Dockerfile doesn't build:"
    tail -n 25 "$err" | sed 's/^/     /'
    fail=1
  elif ! docker run --rm --entrypoint .venv/bin/python "$tag" -c "$IMAGE_PROBE" >/dev/null 2>"$err"; then
    bad "$rel's image builds, but the app doesn't import or a file it reads is missing:"
    tail -n 25 "$err" | sed 's/^/     /'
    fail=1
  else
    say "   built $tag; app.main imports; the font, alembic.ini, migrations and the public styles are in it"
  fi
  docker image rm -f "$tag" >/dev/null 2>&1 || true
  rm -f "$err"
}

# ---------------------------------------------------------------- install ---
# CI installs dependencies by calling `gate.sh --install-deps`, so the installer walks
# exactly the directories project_dirs() lists and uses exactly the package manager
# check_node() will. It used to be a loop in ci.yml with its own directory list, and
# the two drifted: CI never installed a frontend/ package that the checks then failed
# for having no node_modules. The pre-push hook never calls this -- locally, a missing
# install is yours to fix, and the checks say so rather than fixing it behind your back.
install_deps() {
  local dir="$1" rel="$2" pm

  if is_python_project "$dir"; then
    manifests=$((manifests + 1))
    step "install Python dependencies ($rel)"
    if ! command -v uv >/dev/null 2>&1; then
      bad "   uv is not on PATH -- cannot install $rel's dependencies."
      fail=1
    elif [ -f "$dir/pyproject.toml" ]; then
      ( cd "$dir" && { uv sync --frozen || uv sync; } ) || fail=1
    elif [ -f "$dir/requirements.txt" ]; then
      ( cd "$dir" && { [ -d .venv ] || uv venv .venv; } && uv pip install -r requirements.txt ) || fail=1
    else
      ( cd "$dir" && { [ -d .venv ] || uv venv .venv; } && uv pip install -e . ) || fail=1
    fi
  fi

  if [ -f "$dir/package.json" ]; then
    manifests=$((manifests + 1))
    pm="$(node_pm "$dir")"
    step "$pm install ($rel)"
    if ! command -v "$pm" >/dev/null 2>&1; then
      bad "   $rel is locked to '$pm' (its lockfile says so) but '$pm' is not on PATH."
      fail=1
    elif [ "$pm" = npm ]; then
      ( cd "$dir" && { npm ci || npm install; } ) || fail=1
    else
      ( cd "$dir" && "$pm" install ) || fail=1
    fi
  fi
}

# ------------------------------------------------------------ test Postgres --
# docs/design/deploy.md §6 (T009; option A, Postgres 17.11): the database tests need a real
# Postgres, and the gate provides it, so the hook and CI run the same thing (CI's runner has
# Docker). TEST_DATABASE_URL wins if set; else a throwaway container; else the gate FAILS -- a
# database test is never silently skipped here (PANELWISE_REQUIRE_DB=1 makes pytest fail, not skip).
TEST_PG_IMAGE="postgres:17.11-trixie"
test_pg_container=""

stop_test_postgres() {
  if [ -n "$test_pg_container" ]; then
    docker rm -f "$test_pg_container" >/dev/null 2>&1 || true
    test_pg_container=""
  fi
}

start_test_postgres() {
  export PANELWISE_REQUIRE_DB=1
  if [ -n "${TEST_DATABASE_URL:-}" ]; then
    say "   test Postgres: TEST_DATABASE_URL (set by the caller)"
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    bad "No Postgres for the database tests: start Docker, or set TEST_DATABASE_URL"
    bad "   (a database whose name ends in _test; docs/design/deploy.md §6)."
    fail=1
    return 0
  fi
  local password port i err
  password="gate-$RANDOM$RANDOM"
  err="$(mktemp)"
  test_pg_container="$(docker run -d --rm -e POSTGRES_PASSWORD="$password" \
      -e POSTGRES_DB=panelwise_test -p 127.0.0.1::5432 "$TEST_PG_IMAGE" 2>"$err")" || {
    bad "Could not start $TEST_PG_IMAGE for the database tests:"
    sed 's/^/     /' "$err"
    rm -f "$err"
    fail=1
    test_pg_container=""
    return 0
  }
  rm -f "$err"
  trap stop_test_postgres EXIT
  for i in $(seq 1 60); do
    # pg_isready over TCP: the image's first, socket-only start is not the real server.
    if docker exec "$test_pg_container" pg_isready -h 127.0.0.1 -U postgres -d panelwise_test \
        >/dev/null 2>&1; then
      port="$(docker port "$test_pg_container" 5432/tcp | head -n1 | sed 's/.*://')"
      export TEST_DATABASE_URL="postgresql://postgres:$password@127.0.0.1:$port/panelwise_test"
      say "   test Postgres: $TEST_PG_IMAGE on 127.0.0.1:$port (removed on exit)"
      return 0
    fi
    sleep 1
  done
  bad "$TEST_PG_IMAGE did not become ready within 60 s."
  fail=1
}

# ------------------------------------------------------------------ run -----
# Whether this run includes a stage: every stage when --stage is not given.
want() { [ -z "$stage" ] || [ "$stage" = "$1" ]; }

say "== gate: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)${stage:+ (stage $stage)} =="

# Once, before the per-project checks, so every pyrun subshell inherits TEST_DATABASE_URL; never
# for --list or --install-deps.
if [ "$install_only" -eq 0 ] && [ "$list_only" -eq 0 ] && want python; then
  while IFS= read -r dir; do
    if is_python_project "$dir"; then
      step "test Postgres"
      start_test_postgres
      break
    fi
  done < <(project_dirs)
fi

while IFS= read -r dir; do
  rel="${dir#"$root"/}"
  [ "$rel" = "$dir" ] && rel="."
  if [ "$install_only" -eq 1 ]; then
    install_deps "$dir" "$rel"
  else
    # A stage skips another stage's checks but still counts its manifests, so "no project
    # manifest" and "zero checks ran" mean the same in a stage as in the whole gate.
    if want python; then check_python "$dir" "$rel"; elif is_python_project "$dir"; then manifests=$((manifests + 1)); fi
    if want node; then check_node "$dir" "$rel"; elif [ -f "$dir/package.json" ]; then manifests=$((manifests + 1)); fi
    collect_lockfiles "$dir" "$rel"
  fi
done < <(project_dirs)

if [ "$install_only" -eq 1 ]; then
  say ""
  if [ "$fail" -ne 0 ]; then say "== dependency install FAILED =="; exit 1; fi
  say "== dependencies installed for $manifests project manifest(s) =="
  exit 0
fi

# --list stops here, before the sweeps. It used to run both of them and then report
# "nothing was executed".
if [ "$list_only" -eq 1 ]; then
  say ""
  say "-> would run: placeholder sweep, secret sweep"
  if [ "$manifests" -gt 0 ]; then
    say "-> would run: dependency vulnerability scan over: ${LOCKFILES[*]:-(no committed lockfiles)}"
    command -v osv-scanner >/dev/null 2>&1 || say "   (osv-scanner not on PATH -- would FAIL)"
    say "-> would run: duplication check (jscpd $JSCPD_VERSION, threshold $DUPLICATION_THRESHOLD%)"
    command -v npx >/dev/null 2>&1 || say "   (npx not on PATH -- would FAIL)"
    while IFS= read -r dir; do
      say "-> would run: image build (${dir#"$root"/})"
      command -v docker >/dev/null 2>&1 || say "   (docker not on PATH -- would FAIL)"
    done < <(image_dirs)
  fi
  say ""
  say "(--list: no checks were run. $manifests project manifest(s) found.)"
  exit 0
fi

if want repo; then
placeholder_sweep
secret_sweep
fi

# Both look at the whole repo rather than one project, so they run once, and only once
# there is a project to look at.
if [ "$manifests" -gt 0 ] && want repo; then
  [ "${#LOCKFILES[@]}" -gt 0 ] && vuln_scan
  duplication_check
  while IFS= read -r dir; do
    image_check "$dir" "${dir#"$root"/}"
  done < <(image_dirs)
fi

# --- the two ways a gate lies about being green ----------------------------
if [ "$manifests" -eq 0 ]; then
  # No project manifest anywhere. Fine for a scaffold-only repo; NOT fine if the
  # commits being pushed contain source code, because then real code is going in
  # entirely unchecked and the gate would otherwise say "passed".
  code=""
  if [ -n "$changed_files_list" ] && [ -f "$changed_files_list" ]; then
    code="$(grep -E '\.(py|ts|tsx|js|jsx|go|rs|java|rb|php|c|cc|cpp|h|hpp|cs|kt|swift)$' \
              "$changed_files_list" || true)"
  fi
  if [ -n "$code" ]; then
    bad "Source files are being pushed, but this repo has no project manifest"
    bad "   (no pyproject.toml / requirements.txt / package.json anywhere the gate looks)."
    bad "   The gate cannot check this code, so it will not pretend to have checked it."
    bad "   Add the manifest, or add this directory to project_dirs() in scripts/gate.sh."
    printf '%s\n' "$code" | sed 's/^/     /'
    exit 1
  fi
  say ""
  say "No project manifests yet -- scaffold-only repo, nothing to build. Placeholder sweep ran."
elif [ "$ran" -eq 0 ]; then
  say ""
  bad "Found $manifests project manifest(s) but ran zero checks."
  bad "   That is a misconfiguration, not a pass. Fix scripts/gate.sh or the environment."
  exit 1
fi

if [ "$fail" -ne 0 ]; then
  say ""
  say "== gate FAILED =="
  exit 1
fi

say ""
say "== gate passed ($ran check(s) run across $manifests project(s))${stage:+ in stage $stage} =="
exit 0
