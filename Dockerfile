FROM eclipse-temurin:11-jdk

# Install required tools
RUN apt-get update && apt-get install -y \
    groovy \
    python3 \
    python3-pip \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install JMeter
ENV JMETER_VERSION=5.6.3
RUN curl -L https://archive.apache.org/dist/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz \
    | tar -xz -C /opt

ENV JMETER_HOME=/opt/apache-jmeter-${JMETER_VERSION}
ENV PATH=$PATH:$JMETER_HOME/bin

WORKDIR /workspace
