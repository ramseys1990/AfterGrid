FROM node:22-bookworm-slim AS map-assets
WORKDIR /build
RUN npm install --ignore-scripts --no-audit --no-fund --save-exact maplibre-gl@5.0.1 pmtiles@4.2.1 @protomaps/basemaps@5.7.2 && \
    mkdir -p /out/licenses && \
    cp node_modules/maplibre-gl/dist/maplibre-gl.js node_modules/maplibre-gl/dist/maplibre-gl.css /out/ && \
    cp node_modules/pmtiles/dist/pmtiles.js node_modules/@protomaps/basemaps/dist/basemaps.js /out/

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends curl kiwix-tools ca-certificates util-linux osmium-tool && rm -rf /var/lib/apt/lists/*
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
COPY --from=map-assets /out/ ./map-assets/
COPY map-licenses/ ./map-assets/licenses/
RUN curl -fsSL https://codeload.github.com/protomaps/basemaps-assets/tar.gz/028c18f713baecad011301ff7a69acc39bcc2ae7 -o /tmp/map-assets.tar.gz && \
    tar -xzf /tmp/map-assets.tar.gz -C /app/map-assets --strip-components=1 --wildcards '*/fonts/*' '*/sprites/v4/light*' && \
    cp /app/map-assets/fonts/OFL.txt /app/map-assets/licenses/fonts.txt && rm /tmp/map-assets.tar.gz
# Natural Earth public-domain geographic overview (pinned source).
RUN curl -fsSL https://raw.githubusercontent.com/nvkelso/natural-earth-vector/ca96624a56bd078437bca8184e78163e5039ad19/geojson/ne_110m_land.geojson -o /app/map-assets/land.geojson && \
    python -c 'import hashlib; p=open("/app/map-assets/land.geojson","rb").read(); assert hashlib.sha1(b"blob "+str(len(p)).encode()+b"\0"+p).hexdigest()=="04811d72fff2701ec67587e30ad8942675b511e3"'
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && groupadd -g 10001 aftergrid && useradd -u 10001 -g 10001 --no-create-home aftergrid
COPY app.py worker_client.py content.py downloads.py households.py inventory.py map_downloads.py routing.py routing_downloads.py place_search.py waypoints.py communications.py communications.html communications.js maps.html maps.js maps.css region.js index.html style.css app.js ./
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers"]
