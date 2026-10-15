FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    bash \
    tini \
    tzdata \
    iputils-ping \
    snmp \
    libsnmp-dev \
    expect \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV TZ=Africa/Lagos

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8310

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "2_DumbOLT.py"]
