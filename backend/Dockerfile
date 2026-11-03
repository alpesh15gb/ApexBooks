FROM python:3.12-slim
ARG APEX_BUILD_SHA=unknown
ARG APEX_RELEASE_VERSION=unknown
ENV APEX_BUILD_SHA=${APEX_BUILD_SHA}
LABEL org.opencontainers.image.revision=${APEX_BUILD_SHA} \
      org.opencontainers.image.version=${APEX_RELEASE_VERSION}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "python migrate.py && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
