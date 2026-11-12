FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git jq ripgrep libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/local/bin/python3 /usr/bin/python3 \
    && mkdir -p /home/agent /work /results /run/bench
COPY client.py /usr/bin/az
COPY entry.py /opt/client/entry.py
RUN chmod 755 /usr/bin/az
ENV HOME=/home/agent PATH=/usr/local/bin:/usr/bin:/bin
WORKDIR /work
ENTRYPOINT ["/usr/bin/python3", "/opt/client/entry.py"]
