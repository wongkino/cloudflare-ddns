FROM python:3.12-alpine

WORKDIR /app
RUN pip install --no-cache-dir apprise \
 && adduser -D -u 10001 app
COPY updater.py .
USER app

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import time; age=time.time()-float(open('/tmp/healthy').read()); raise SystemExit(0 if age<120 else 1)"

CMD ["python", "-u", "updater.py"]
