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
    && rm -rf /var/lib/apt/lists/*

# -------------------------------
# Install Python dependencies
# -------------------------------
# Copy requirements first for Docker layer caching
COPY requirements.txt /tmp/requirements.txt

RUN pip3 install --no-cache-dir --break-system-packages \
    -r /tmp/requirements.txt

# -------------------------------
# Install JMeter
# -------------------------------
ENV JMETER_VERSION=5.6.3

RUN curl -L https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz \
    | tar -xz -C /opt

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