FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends bash ca-certificates git jq ripgrep libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s /usr/local/bin/python3 /usr/bin/python3 \
    && mkdir -p /home/agent /work /results /run/bench
COPY client.py /usr/bin/az
COPY entry.py /opt/client/entry.py
COPY client.py curl kubectl /opt/client/
RUN chmod 755 /usr/bin/az /opt/client/curl /opt/client/kubectl
ENV HOME=/home/agent PATH=/opt/client:/usr/local/bin:/usr/bin:/bin
WORKDIR /work
ENTRYPOINT ["/usr/bin/python3", "/opt/client/entry.py"]
