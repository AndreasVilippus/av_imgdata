FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/av-imgdata-worker

COPY bin/ ./bin/
COPY config/ ./config/
COPY jobs/ ./jobs/
COPY share/ ./share/
COPY models/ ./models/
COPY entrypoint.sh ./entrypoint.sh

RUN chmod +x ./entrypoint.sh ./bin/av-imgdata-worker

ENTRYPOINT ["./entrypoint.sh"]
CMD ["version"]
