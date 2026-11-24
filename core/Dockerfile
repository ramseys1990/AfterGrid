FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl kiwix-tools ca-certificates util-linux && rm -rf /var/lib/apt/lists/*
# Pinned upstream release, verified against GitHub release asset SHA-256.
RUN set -eux; \
    case "$(dpkg --print-architecture)" in \
      amd64) arch=x86_64; sha=3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f ;; \
      arm64) arch=arm64; sha=f8bd47e7ea866863489cad588fbaf2f31f42e5821f7a03f009b3769f05801cb1 ;; \
      *) exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles_1.31.2_Linux_${arch}.tar.gz" -o /tmp/pmtiles.tar.gz; \
    echo "$sha  /tmp/pmtiles.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/pmtiles.tar.gz -C /usr/local/bin pmtiles; \
    rm /tmp/pmtiles.tar.gz; pmtiles version
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -g 10001 aftergrid && useradd -u 10001 -g 10001 --no-create-home aftergrid
COPY app.py worker_client.py content.py downloads.py households.py inventory.py map_downloads.py index.html style.css app.js ./
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers"]
