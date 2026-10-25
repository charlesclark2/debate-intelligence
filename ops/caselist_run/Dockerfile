# syntax=docker/dockerfile:1
# check=skip=InvalidDefaultArgInFrom
#
# The weekly caselist run's image (ADR-0020 (1); task v1-e40-t03): debate-research from one tagged
# release, installed exactly as scripts/install_channel.sh installs it on a coach's Mac, on the slim
# Debian Python image of the one Python that packages/debate_core/pyproject.toml's requires-python
# allows. The login task and the run task both run it, by digest.
#
# Built by scripts/caselist_run_deploy.sh, on the operator's Mac and in validate-dev's image job,
# never by hand:
#
#   docker buildx build --platform linux/arm64 --provenance=false \
#     --build-arg PYTHON_VERSION=<the one Python requires-python allows> \
#     --build-arg RELEASE_TAG=<vX.Y.Z-dev.N or vX.Y.Z> \
#     -f ops/caselist_run/Dockerfile <staging directory>
#
# The build context is a staging directory the script fills, not the repository: install_channel.sh
# and assets/, the release's wheels, SHA256SUMS and build-info.json as `gh release download` fetched
# them. So no evidence, no checkout and no credential can reach the image. The build reaches PyPI
# for the third-party packages, and uv's Python downloads; it is given no token and no AWS session,
# and the image's environment holds nothing but the paths below. What makes it the cloud run (the
# environment, the token's secret name) is the task definition's, and no secret is in either:
# the CLI reads the token at run time with the task role.
#
# install_channel.sh verifies SHA256SUMS, installs on a Python uv manages (that is what it requires;
# the base image's own python3 is not the one debate-research runs on), rehearses the install, and
# refuses a build that cannot import every integration it wires or fails `doctor`. A build that
# fails any check fails here.

# The base image follows requires-python; scripts/caselist_run_deploy.sh derives the tag from it,
# which is why PYTHON_VERSION has no default and the check directive at the top skips BuildKit's
# warning about that.
ARG PYTHON_VERSION

# Both base images are pinned by digest as well as tag (v1-e40-t06), so that a tag moved upstream
# changes nothing the run is built on until a pull request moves the digest. Each is the multi-arch
# index's digest, as `docker buildx imagetools inspect <tag>` read it from the registry on 2026-10-26
# (the operator's run, in v1-e40-t06's session report); buildx takes the linux/arm64 image from it.
#
#   python, the tag `scripts/caselist_run_deploy.sh --print-base-image` names:
#     https://hub.docker.com/_/python/tags?name=slim-bookworm
#   uv 0.11.7: https://github.com/astral-sh/uv/pkgs/container/uv
#
# With a digest, the tag beside it no longer chooses the image. So when requires-python moves, the
# python digest moves in the same pull request, read the same way for the new tag; until it does,
# ops/caselist_run/check_image.sh refuses the image, whose base Python is then not the one
# debate-research runs on.

# uv, pinned. install_channel.sh needs 0.6.8 or newer for --managed-python.
FROM ghcr.io/astral-sh/uv:0.11.7@sha256:240fb85ab0f263ef12f492d8476aa3a2e4e1e333f7d67fbdd923d00a506a516a AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS install

ARG RELEASE_TAG

COPY --from=uv /uv /usr/local/bin/uv

# unzip: install_channel.sh reads the debate_core wheel's Requires-Python with it.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends unzip ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Where the build goes, the same paths in the stage below: the console script names its
# interpreter by absolute path, and that interpreter is uv's Python under UV_PYTHON_INSTALL_DIR.
ENV UV_TOOL_DIR=/opt/debate-research/tools \
    UV_TOOL_BIN_DIR=/opt/debate-research/bin \
    UV_PYTHON_INSTALL_DIR=/opt/debate-research/python

COPY install_channel.sh /build/install_channel.sh
COPY assets/ /build/assets/

# The rehearsal and the real install resolve the same packages; uv's cache serves the second, and
# goes with this stage.
RUN test -n "${RELEASE_TAG}" \
 && sh /build/install_channel.sh --no-path-warning --dir /build/assets "${RELEASE_TAG}" \
 && rm -rf /build "$(uv cache dir)"

FROM python:${PYTHON_VERSION}-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70 AS run

COPY --from=install /opt/debate-research /opt/debate-research

# debate-research on PATH: the login task's entryPoint names it (v1-e40-t02), and the run's
# command runs it under `timeout`, which coreutils puts in this image already.
# The run's data directory lives under /var/lib/debate-research, on the task's ephemeral volume,
# owned by the user the tasks run as. Nobody logs in as that user.
RUN ln -s /opt/debate-research/bin/debate-research /usr/local/bin/debate-research \
 && groupadd --system --gid 10001 debate \
 && useradd --system --uid 10001 --gid debate --home-dir /var/lib/debate-research \
      --shell /usr/sbin/nologin debate \
 && mkdir -p /var/lib/debate-research \
 && chown debate:debate /var/lib/debate-research

USER 10001:10001
WORKDIR /var/lib/debate-research
ENV HOME=/var/lib/debate-research

ENTRYPOINT ["debate-research"]
