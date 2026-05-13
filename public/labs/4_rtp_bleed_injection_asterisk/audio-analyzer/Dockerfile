FROM python:3.11-slim

RUN pip install --no-cache-dir numpy scipy

WORKDIR /app
COPY verify.py .

ENTRYPOINT ["python", "verify.py"]