# Production web image: the Flutter web build served by Nginx, which also proxies /api/ to the API.
# Build from native/flutter:  docker build -f web.Dockerfile --build-arg APEX_BUILD_SHA=<sha> --build-arg APEX_RELEASE_VERSION=<version> .
FROM debian:bookworm-slim AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git unzip xz-utils \
 && rm -rf /var/lib/apt/lists/*
ARG FLUTTER_VERSION=3.50.0
RUN git clone --depth 1 --branch "${FLUTTER_VERSION}" https://github.com/flutter/flutter.git /opt/flutter \
 && useradd --create-home builder && chown -R builder /opt/flutter
USER builder
ENV PATH=/opt/flutter/bin:$PATH \
    FLUTTER_SUPPRESS_ANALYTICS=true \
    PUB_CACHE=/home/builder/.pub-cache
RUN flutter config --disable-analytics --no-cli-animations \
 && flutter precache --web --no-ios --no-linux --no-windows --no-macos
WORKDIR /home/builder/app
COPY --chown=builder pubspec.yaml pubspec.lock ./
RUN flutter pub get
COPY --chown=builder . .
ARG APEX_BUILD_SHA=unknown
RUN flutter build web --release --no-web-resources-cdn \
      "--dart-define=APEX_BUILD_SHA=${APEX_BUILD_SHA}"

FROM nginx:alpine
ARG APEX_BUILD_SHA=unknown
ARG APEX_RELEASE_VERSION=unknown
LABEL org.opencontainers.image.revision=${APEX_BUILD_SHA} \
      org.opencontainers.image.version=${APEX_RELEASE_VERSION}
COPY --from=build /home/builder/app/build/web /usr/share/nginx/html
COPY web.nginx.conf /etc/nginx/conf.d/default.conf
