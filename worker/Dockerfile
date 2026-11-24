FROM docker:28-cli
RUN apk add --no-cache python3
WORKDIR /app
COPY worker.py .
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
LABEL org.aftergrid.recovery-core-only="1" org.aftergrid.recovery-offline="1"
CMD ["python3", "/app/worker.py"]
