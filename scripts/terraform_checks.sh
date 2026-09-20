#!/usr/bin/env bash
#
# Static Terraform checks: formatting, validation and lint, for every root and module under
# infrastructure/.
#
# Nothing here needs AWS credentials and nothing here reads an AWS account. `terraform init` runs
# with -backend=false, so no state bucket is opened, no lock is taken and no credential is
# resolved; the only network this script uses is the provider registry and the tflint plugin
# registry.
#
# That is deliberate. Until the GitHub OIDC plan/apply roles of v2-e10-t03 exist, CI has no way to
# reach the account, and every plan and apply is an operator step (docs/process/working-agreements.md,
# docs/runbooks/terraform-bootstrap.md). These checks are what CI and pre-commit run instead.
#
# Usage:  scripts/terraform_checks.sh [--no-lint] [--sync-tflint]
#         TERRAFORM_BIN=... TFLINT_BIN=... scripts/terraform_checks.sh
#
# --sync-tflint copies infrastructure/.tflint.hcl into every Terraform directory that needs one.
# It exists because tflint does not inherit configuration from parent directories; see the header
# of infrastructure/.tflint.hcl.
#
# Runs every check before reporting, so one run lists every problem rather than only the first,
# and exits non-zero if any of them failed.
#
# Written for bash 3.2, which is what macOS ships.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="${REPO_ROOT}/infrastructure"

TERRAFORM_BIN="${TERRAFORM_BIN:-terraform}"
TFLINT_BIN="${TFLINT_BIN:-tflint}"

run_lint=true
sync_tflint=false
if [ $# -gt 0 ]; then
  for arg in "$@"; do
    case "${arg}" in
      --no-lint) run_lint=false ;;
      --sync-tflint) sync_tflint=true ;;
      *)
        echo "usage: $(basename "$0") [--no-lint] [--sync-tflint]" >&2
        exit 64
        ;;
    esac
  done
fi

failure_count=0
failure_list=""

fail() {
  echo "FAIL  $1"
  failure_count=$((failure_count + 1))
  failure_list="${failure_list}  - $1
"
}

pass() {
  echo "ok    $1"
}

require_tool() {
  # $1 binary, $2 human name, $3 install hint
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "error: $2 is not installed or not on PATH." >&2
    echo "       Install it with: $3" >&2
    echo "       Versions this repository is pinned to: .terraform-version, infrastructure/.tflint.hcl." >&2
    exit 127
  fi
}

# The directory whose .tflint.hcl is deliberately different from the shared one, and why.
# infrastructure/bootstrap/organization/.tflint.hcl documents it.
TFLINT_CONFIG_EXCEPTIONS="infrastructure/bootstrap/organization"

check_tflint_configs() {
  shared_config="${INFRA_DIR}/.tflint.hcl"
  if [ ! -f "${shared_config}" ]; then
    fail "infrastructure/.tflint.hcl is missing"
    return
  fi

  # Every directory holding .tf files needs its own copy, because tflint inherits nothing from a
  # parent directory. Without this check a directory added by a later task would be linted with
  # tflint's built-in defaults and the tagging standard would quietly stop applying to it.
  for dir in $(find "${INFRA_DIR}" -name '*.tf' -not -path '*/.terraform/*' -exec dirname {} \; | sort -u); do
    rel="${dir#"${REPO_ROOT}/"}"
    case " ${TFLINT_CONFIG_EXCEPTIONS} " in
      *" ${rel} "*)
        if [ ! -f "${dir}/.tflint.hcl" ]; then
          fail "tflint config missing in ${rel} (documented exception, but the file has to exist)"
        else
          pass "tflint config ${rel} (documented exception)"
        fi
        continue
        ;;
    esac

    if [ "${sync_tflint}" = true ]; then
      cp "${shared_config}" "${dir}/.tflint.hcl"
    fi

    if [ ! -f "${dir}/.tflint.hcl" ]; then
      fail "tflint config missing in ${rel} (run: scripts/terraform_checks.sh --sync-tflint)"
    elif ! cmp -s "${shared_config}" "${dir}/.tflint.hcl"; then
      fail "tflint config in ${rel} differs from infrastructure/.tflint.hcl (run: scripts/terraform_checks.sh --sync-tflint)"
    else
      pass "tflint config ${rel}"
    fi
  done
}

require_tool "${TERRAFORM_BIN}" terraform "brew install hashicorp/tap/terraform"

# Roots are the directories that configure a backend; modules are the directories under
# infrastructure/modules. Discovering them rather than listing them means a root added by a later
# task is checked without editing this script.
roots="$(find "${INFRA_DIR}" -name backend.tf -not -path '*/.terraform/*' -exec dirname {} \; | sort)"
modules="$(find "${INFRA_DIR}/modules" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)"

if [ -z "${roots}" ]; then
  echo "error: no Terraform roots found under ${INFRA_DIR} (each root has a backend.tf)." >&2
  exit 1
fi

echo "== terraform fmt =="
fmt_output="$("${TERRAFORM_BIN}" fmt -check -recursive -no-color "${INFRA_DIR}" 2>&1)"
if [ $? -eq 0 ]; then
  pass "fmt -check -recursive infrastructure"
else
  fail "fmt -check -recursive infrastructure (fix with: terraform fmt -recursive infrastructure)"
  echo "${fmt_output}" | sed 's/^/      /'
fi

echo
echo "== terraform validate =="
for dir in ${roots} ${modules}; do
  rel="${dir#"${REPO_ROOT}/"}"
  validate_output="$(
    "${TERRAFORM_BIN}" -chdir="${dir}" init -backend=false -input=false -no-color 2>&1 &&
      "${TERRAFORM_BIN}" -chdir="${dir}" validate -no-color 2>&1
  )"
  if [ $? -eq 0 ]; then
    pass "validate ${rel}"
  else
    fail "validate ${rel}"
    echo "${validate_output}" | sed 's/^/      /'
  fi
done

if [ "${run_lint}" = true ]; then
  echo
  echo "== tflint =="
  require_tool "${TFLINT_BIN}" tflint "brew install tflint"

  # tflint reads the .tflint.hcl of the directory it is linting and inherits nothing from the
  # parent, so `--recursive` only enforces the tagging standard in directories that hold a copy
  # of the shared config. Checking that first is what stops the run below from passing because
  # the rules were never loaded.
  check_tflint_configs

  # --recursive resolves .tflint.hcl per directory, which is how bootstrap/organization keeps its
  # documented exception to the tagging standard while every other directory uses the shared
  # config. Plugins are installed per config, so --init runs the same way.
  init_output="$("${TFLINT_BIN}" --chdir="${INFRA_DIR}" --recursive --init --no-color 2>&1)"
  if [ $? -ne 0 ]; then
    fail "tflint --init (plugin install)"
    echo "${init_output}" | sed 's/^/      /'
  else
    lint_output="$("${TFLINT_BIN}" --chdir="${INFRA_DIR}" --recursive --no-color 2>&1)"
    if [ $? -eq 0 ]; then
      pass "tflint --recursive infrastructure"
    else
      fail "tflint --recursive infrastructure"
      echo "${lint_output}" | sed 's/^/      /'
    fi
  fi
fi

echo
if [ "${failure_count}" -gt 0 ]; then
  echo "${failure_count} check(s) failed:"
  printf '%s' "${failure_list}"
  exit 1
fi
echo "All Terraform checks passed."
