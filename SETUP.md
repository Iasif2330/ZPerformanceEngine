# Performance Testing Framework Setup Guide

_(Docker + Jenkins + ZPerformanceEngine)_

This document explains how to set up and run the Performance Testing Framework on a new Mac machine.

The framework uses:

- Docker (execution environment)
- Jenkins (pipeline orchestration)
- Groovy Active Choices (dynamic parameters)
- YAML configuration files
- JMeter inside Docker

## 1. Clone the Framework Repository

### Objective

Place the framework in a shared location accessible by Jenkins and the user.

### Step 1 — Navigate to Shared Folder

```bash
cd /Users/Shared
```

If the folder does not exist:

```bash
sudo mkdir -p /Users/Shared
```

### Step 2 — Clone the Repository

```bash
git clone <REPO_URL>
```

Example:

```bash
git clone https://github.com/your-org/ZPerformanceEngine.git
```

After cloning, the structure should be:

```
/Users/Shared/ZPerformanceEngine
```

Verify:

```bash
ls /Users/Shared
```

You should see:

```
ZPerformanceEngine
```

## 2. Install Docker Desktop

### Step 1 — Install Docker

Using Homebrew:

```bash
brew install --cask docker
```

If you see the message:

```
Error: It seems there is already an App at '/Applications/Docker.app'
```

Docker is already installed.

### Step 2 — Open Docker Desktop

Open Docker:

```bash
open -a Docker
```

Or from Applications → Docker

### Step 3 — Complete Default Setup

When Docker launches:

1. Accept terms
2. Login and complete default setup

### Step 4 — Verify Docker is Running

Ensure the Docker whale icon appears in the Mac menu bar.

Check Docker via terminal:

```bash
docker --version
```

Example output:

```
Docker version 27.x.x
```

## 3. Disable Docker Credential Store

### Why this is required

Some environments cause Docker credential helper errors during image builds.

Example error:

```
error getting credentials - err: exit status 1
```

To avoid this, disable the Docker credential helper.

### Step 1 — Open Docker Config

```bash
cat ~/.docker/config.json
```

Example content:

```json
{
  "auths": {},
  "credsStore": "desktop",
  "currentContext": "desktop-linux"
}
```

### Step 2 — Edit the File

```bash
nano ~/.docker/config.json
```

Remove:

```json
"credsStore": "desktop"
```

Final file should look like:

```json
{
  "auths": {},
  "currentContext": "desktop-linux"
}
```

Save and exit.

## 4. Install Jenkins

### Step 1 — Install Jenkins LTS

```bash
brew install jenkins-lts
```

### Step 2 — Start Jenkins

```bash
brew services start jenkins-lts
```

Verify:

```bash
brew services list
```

Expected output:

```
jenkins-lts started
```

### Step 3 — Open Jenkins

Open browser:

```
http://localhost:8080
```

## 5. Complete Default Jenkins Setup

When Jenkins opens:

1. Retrieve initial admin password.

Run:

```bash
cat ~/.jenkins/secrets/initialAdminPassword
```

Copy the password and paste it into Jenkins.

### Step 2 — Install Recommended Plugins

Choose:

- **Install Suggested Plugins**

Wait for installation.

## 6. Install Required Jenkins Plugin

### Active Choices Plugin

Go to:

- Manage Jenkins → Manage Plugins → Available Plugins

Search for:

```
Active Choices Plugin
```

Install it and restart Jenkins if prompted.

## 7. Add Required Jenkins Credential

The framework requires a Grafana read-only token.

### Step 1 — Navigate to Credentials

- Manage Jenkins → Manage Credentials → Global

### Step 2 — Add Credential

Select:

- **Add Credentials**

Configure:
| Field | Value |
|-------|-------|
| Kind | Secret Text |
| Secret | 976d959cc5dc4273a4eb9adce223715d |
| ID | grafana-readonly-token |

Save.

## 8. Create Jenkins Pipeline Job

### Step 1 — Create Job

Go to:

- **New Item**

Enter name:

```
ZPerformanceEngine
```

Select:

- **Pipeline**

Click **OK**

## 9. Enable Parameterized Build

Inside the job configuration:
Enable:

- **This project is parameterized**

## 10. Add Jenkins Parameters

The pipeline uses Active Choices parameters that dynamically read YAML configuration files from the repository.

### Parameter 1 — ENVIRONMENT

**Type:** Active Choices Parameter

**Configuration:**

- Disable: **Use Groovy Sandbox**
- Then approve the script.

**Groovy Script:**

```groovy
import org.yaml.snakeyaml.Yaml

def yamlFile = new File("/Users/Shared/ZPerformanceEngine/config/environments.yaml")

// Safety guard: file must exist
if (!yamlFile.exists()) {
    return ["autoprod"]
}

def yaml = new Yaml()
def data = yaml.load(yamlFile.text)

// Safety guard: must be a map
if (!(data instanceof Map)) {
    return ["autoprod"]
}

// Collect env names
def envs = data.keySet()
               .collect { it.toString() }
               .sort()

if (envs.isEmpty()) {
    return ["autoprod"]
}

return envs
```

### Parameter 2 — LOAD_PROFILE

**Type:** Active Choices Parameter

- Disable sandbox.

**Groovy Script:**

```groovy
import org.yaml.snakeyaml.Yaml

def yamlFile = new File("/Users/Shared/ZPerformanceEngine/config/load-profile.yaml")

if (!yamlFile.exists()) {
    return ["baseline-minimal"]
}

def yaml = new Yaml()
def data = yaml.load(yamlFile.text)

if (!(data instanceof Map) || !(data.profiles instanceof List)) {
    return ["baseline-minimal"]
}

def profiles = data.profiles
    .findAll { it instanceof Map && it.name }
    .collect { it.name.toString() }

if (profiles.isEmpty()) {
    return ["baseline-minimal"]
}

return profiles.sort()
```

### Parameter 3 — LOOP_LOGIN

**Type:** Active Choices Parameter

- Disable sandbox.

**Script:**

```groovy
return ['true', 'false']
```

### Parameter 4 — DURATION

**Type:** String Parameter

**Default Value:**

```
1000000
```

### Parameter 5 — API_GROUPS

**Type:** Active Choices Parameter

- Disable sandbox.

**Script:**

```groovy
import org.yaml.snakeyaml.Yaml

def yamlFile = new File("/Users/Shared/ZPerformanceEngine/config/api-groups.yaml")

if (!yamlFile.exists()) return []

def yaml = new Yaml()
def data = yaml.load(yamlFile.text)

return data.groups.keySet().toList()
```

### Parameter 6 — SELECTED_APIS

**Type:** Active Choices Parameter

- Disable sandbox.

**Script:**

```groovy
import org.yaml.snakeyaml.Yaml

def yamlFile = new File("/Users/Shared/ZPerformanceEngine/config/apis.yaml")

if (!yamlFile.exists()) return []

def yaml = new Yaml()
def data = yaml.load(yamlFile.text)

if (!(data instanceof Map) || !(data.apis instanceof List)) {
    return []
}

return data.apis
    .findAll { it instanceof Map && it.name }
    .collect { it.name.toString() }
```

## 11. Configure Pipeline Source

Scroll to Pipeline section.

Select:

- **Pipeline script from SCM**

**SCM:**

- Select: **Git**

**Repository URL:**

- Enter repository URL: `<REPO_URL>`

**Branch:**

- Example: `main`

**Script Path:**

- Example: `Jenkinsfile`

Click:

- **Apply**
- **Save**

## 12. Run the Pipeline

Go to the job.

Click:

- **Build with Parameters**

Select values for:

- ENVIRONMENT
- LOAD_PROFILE
- LOOP_LOGIN
- DURATION
- API_GROUPS
- SELECTED_APIS

Then click:

- **Build**

## 13. Pipeline Execution Flow

When the job runs:

1. Jenkins reads YAML configs
2. Parameters populate dynamically
3. Docker image builds (if needed)
4. JMeter runs inside Docker
5. Metrics exported to Grafana
6. Results stored in pipeline artifacts

## Final Setup Architecture

```
Developer Machine
      │
      │
      ▼
Jenkins Pipeline
      │
      │
      ▼
Docker Container
(Test Execution Environment)
      │
      ▼
Apache JMeter
(API Load Test Execution)
      │
      ▼
Test Metrics Generated
(Response time, throughput, error rate)
      │
      ▼
Grafana API (via Read-Only Token)
Programmatic retrieval of server metrics
(CPU, Memory, Network, etc.)
      │
      ▼
Combined Test + Server Metrics
      │
      ▼
Reports / Artifacts Generated by Pipeline
```
