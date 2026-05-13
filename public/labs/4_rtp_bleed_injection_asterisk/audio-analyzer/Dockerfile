FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy scipy soundfile

WORKDIR /app
COPY verify.py .

ENTRYPOINT ["python", "verify.py"]
