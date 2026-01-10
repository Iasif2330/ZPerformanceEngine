FROM eclipse-temurin:11-jdk

# -------------------------------
# Install required OS tools
# -------------------------------
RUN apt-get update && apt-get install -y \
    groovy \
    python3 \
    python3-pip \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# Install Python dependencies
# -------------------------------
COPY requirements.txt /tmp/requirements.txt

RUN pip3 install --no-cache-dir --break-system-packages \
    -r /tmp/requirements.txt

# -------------------------------
# Install JMeter (HARDENED)
# -------------------------------
ENV JMETER_VERSION=5.6.3
ENV JMETER_BASE=/opt

RUN set -eux; \
    JMETER_TGZ="apache-jmeter-${JMETER_VERSION}.tgz"; \
    JMETER_URL="https://downloads.apache.org/jmeter/binaries/${JMETER_TGZ}"; \
    curl -fSL --retry 5 --retry-delay 5 --connect-timeout 15 \
         "${JMETER_URL}" -o "/tmp/${JMETER_TGZ}"; \
    tar -xzf "/tmp/${JMETER_TGZ}" -C "${JMETER_BASE}"; \
    rm "/tmp/${JMETER_TGZ}"

ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION}
ENV PATH=$PATH:$JMETER_HOME/bin

# -------------------------------
# Workspace
# -------------------------------
WORKDIR /workspace

# -------------------------------
# Copy project files
# -------------------------------
COPY . /workspace