FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_BUILD_SHA=unknown
ENV VITE_BUILD_SHA=${VITE_BUILD_SHA}
RUN npm run build
FROM nginx:alpine
ARG VITE_BUILD_SHA=unknown
ARG APEX_RELEASE_VERSION=unknown
LABEL org.opencontainers.image.revision=${VITE_BUILD_SHA} \
      org.opencontainers.image.version=${APEX_RELEASE_VERSION}
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
