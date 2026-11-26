#!/bin/sh
# Mutation testing in a Linux container (mutmut 3 does not run on Windows).
# Run from the project root:
#   docker run --rm -v "${PWD}:/repo" python:3.12-slim sh /repo/scripts/run_mutation.sh
# Writes mutation-report.json (SonarQube generic issues) into the project root.
set -eu

pip install --quiet --root-user-action=ignore --disable-pip-version-check \
    -r /repo/requirements-dev.txt

# mutmut rewrites files under mutants/ and runs the tests thousands of times;
# a copy inside the container keeps that off the slow bind mount and off .venv.
rm -rf /work && mkdir /work
cd /repo
tar cf - --exclude=./.venv --exclude=./.git --exclude=./mutants \
    --exclude=__pycache__ --exclude=./e2e . | tar xf - -C /work
cd /work

started=$(date +%s)
# mutmut exits non-zero when mutants survive; the report still has to be made.
mutmut run --max-children "$(nproc)" > mutmut.log 2>&1 || true
echo "mutmut finished in $(( $(date +%s) - started )) s"

python scripts/mutants_to_sonar.py --output /repo/mutation-report.json
