FROM node:lts-bookworm-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --from=docker:26-cli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update && \
    apt-get install -y --fix-missing --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    apt-get install -y --no-install-recommends \
        git \
        bash \
        curl \
        wget \
        unzip \
        ripgrep \
        vim \
        sudo \
        g++ \
        locales

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen

RUN apt-get update && apt-get install -y --fix-missing --no-install-recommends \
        chromium \
        fonts-liberation \
        libappindicator3-1 \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        xdg-utils \
        fonts-dejavu \
        fonts-noto \
        fonts-noto-cjk \
        fonts-noto-cjk-extra \
        fonts-noto-color-emoji \
        fonts-freefont-ttf \
        fonts-urw-base35 \
        fonts-roboto \
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        fonts-arphic-ukai \
        fonts-arphic-uming \
        fonts-ipafont \
        fonts-ipaexfont \
        fonts-comic-neue \
        imagemagick \
        libreoffice \
        poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Clone project
RUN set -ex \
    && npm config set registry https://registry.npmmirror.com \
    && mkdir -p /usr/src/pptagent \
    && cd /usr/src/pptagent \
    && git clone https://github.com/icip-cas/PPTAgent.git .

WORKDIR /usr/src/pptagent

# Install node deps only where package.json exists
RUN npm install --prefix deeppresenter/html2pptx

ENV PATH="/opt/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV="/opt/.venv" \
    DEEPPRESENTER_WORKSPACE_BASE="/opt/workspace"

RUN uv venv --python 3.13 $VIRTUAL_ENV && \
    uv pip install -e . && \
    playwright install-deps && \
    playwright install chromium

WORKDIR /usr/src/pptagent/deeppresenter/html2pptx/

RUN npx playwright install

WORKDIR /usr/src/pptagent/

RUN npx playwright install

RUN fc-cache -f

CMD ["bash", "-c", "umask 000 && python webui.py 0.0.0.0"]