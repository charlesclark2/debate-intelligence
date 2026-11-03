# syntax=docker/dockerfile:1
# check=skip=InvalidDefaultArgInFrom
#
# The student search pilot's container image (ADR-0019 (a) 1 and (b) 2). Built by
# scripts/tub_deploy.sh, never by hand and never by CI:
#
#   docker buildx build --platform linux/arm64 --provenance=false \
#     --build-arg PYTHON_VERSION=<the one Python requires-python allows> \
#     -f packages/debate_api/Dockerfile <staging directory>
#
# The build context is a staging directory the script fills, not the repository: requirements.txt
# (exported from uv.lock with hashes) and wheels/ (debate-core and debate-api, built by uv). So
# nothing else in the checkout, and no evidence, can end up in the image (ADR-0019 (c) 4).
#
# --provenance=false matters: with provenance attestations buildx pushes a manifest list, and
# Lambda refuses one.

# The base image follows packages/debate_core/pyproject.toml's requires-python. The script derives
# the tag from it; this file states no version of its own, which is why PYTHON_VERSION has no
# default and why the check directive at the top skips BuildKit's warning about that.
ARG PYTHON_VERSION

# The Lambda Web Adapter, copied in as an extension, pinned by digest and never by tag. The digest
# is the multi-platform index of release 1.1.0; buildx picks the arm64 image from it.
FROM public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0@sha256:17cfd08eff1dfea3f6a9a1e9c65fdac80aa4919b6085e746615530f43f57d2f1 AS lambda_web_adapter

FROM public.ecr.aws/lambda/python:${PYTHON_VERSION}

COPY --from=lambda_web_adapter /lambda-adapter /opt/extensions/lambda-adapter

COPY requirements.txt /tmp/build/requirements.txt
COPY wheels/ /tmp/build/wheels/

# Third-party packages exactly as uv.lock pins them, each checked against its hash and taken only
# as a published wheel; then the two workspace packages, with no dependency resolution of their
# own.
RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes --only-binary=:all: \
      -r /tmp/build/requirements.txt \
 && pip install --no-cache-dir --disable-pip-version-check --no-deps /tmp/build/wheels/*.whl \
 && rm -rf /tmp/build

# uvicorn as the function's process. The Lambda base image's own entrypoint starts the runtime
# interface client for a handler; here the Web Adapter talks to the Runtime API instead, and
# forwards each event to this server on port 8080 once /healthz answers. --no-access-log: an
# access log line holds the client's address and the query string (gate item 4).
ENTRYPOINT ["python3", "-m", "uvicorn", "debate_api.container:create_app_from_environment", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
