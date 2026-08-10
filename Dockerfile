# prosaic — the whole dependency set, assembled and pinned.
#
# What this is for: `pleading/requirements.txt` and
# `connectors/package.json` declare the language dependencies, but the
# programs the pipeline shells out to — ocrmypdf, tesseract, poppler,
# a browser — were prose in docs/ until `system-dependencies.yaml`.
# This image is that manifest, resolved.
#
# On Linux it is the deployment artifact. On macOS it is for
# development and CI only: a Linux container there runs inside a VM
# that cannot reach Metal, so audio transcription belongs on the host
# and is deliberately absent from the image (see the `in_container`
# field in the manifest).
#
# Build:
#     docker build -t prosaic .
#
# Run against a matter on the host, as yourself so the files it writes
# are yours and not root's:
#     docker run --rm -v ~/cases/smith:/matter \
#         --user "$(id -u):$(id -g)" prosaic build responsive_declaration
#
# Credentials come from the environment, per ADR-0012 — there is no
# Keychain in here:
#     docker run --rm -v ~/cases/smith:/matter \
#         -e PROSAIC_OFW_USERNAME -e PROSAIC_OFW_PASSWORD \
#         prosaic sync /matter

FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    # Puppeteer drives the distro browser rather than downloading its
    # own: that download needs the same shared libraries the package
    # already pulls in, and one browser is easier to reason about than
    # two.
    PUPPETEER_SKIP_DOWNLOAD=1 \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    PATH=/opt/venv/bin:/opt/prosaic/cli:$PATH

# Bootstrap: only enough to read the manifest that names everything
# else. PEP 668 marks the distro interpreter externally managed, so
# the application's Python dependencies live in their own venv.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates python3 python3-venv \
 && python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install pyyaml \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/prosaic

# The package list is not transcribed into this file. It is computed
# from system-dependencies.yaml, so adding a dependency there is the
# only edit needed and this layer cannot fall out of step with it.
COPY system-dependencies.yaml ./
COPY cli/sc ./cli/sc
RUN apt-get update \
 && apt-get install -y --no-install-recommends $(sc deps --format apt) \
 && rm -rf /var/lib/apt/lists/*

# Language dependencies next, before the source, so editing a Python
# file does not reinstall reportlab.
COPY pleading/requirements.txt ./pleading/requirements.txt
RUN pip install -r pleading/requirements.txt

COPY connectors/package.json connectors/package-lock.json ./connectors/
RUN cd connectors && npm ci --omit=dev && npm cache clean --force

COPY . .

# A named user so a bind-mounted matter does not fill with root-owned
# files. Override with --user "$(id -u):$(id -g)" to match the host.
RUN useradd --create-home --uid 1000 prosaic \
 && chown -R prosaic:prosaic /opt/prosaic
USER prosaic

# Matters are mounted, never baked in: privileged material does not
# belong in an image layer.
WORKDIR /matter
ENTRYPOINT ["sc"]
CMD ["deps"]
