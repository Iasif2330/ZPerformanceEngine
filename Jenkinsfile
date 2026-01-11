pipeline {
    agent any

    environment {
        DOCKER_CLI = "/Applications/Docker.app/Contents/Resources/bin/docker"
        IMAGE_NAME = "zperformance-engine"
        WORKDIR    = "/workspace"
    }

    stages {

        /* ============================
         * STAGE 1 — Build Docker Image
         * ============================ */
        stage('Build Docker Image') {
            steps {
                sh """
                    ${DOCKER_CLI} build -t ${IMAGE_NAME} .
                """
            }
        }

        /* ============================
         * STAGE 2 — Prepare Workspace
         * ============================ */
        stage('Prepare Workspace') {
            steps {
                sh '''
                    rm -rf output
                    mkdir -p output
                '''
            }
        }

        /* ============================
         * STAGE 3 — Build CLI Arguments
         * ============================ */
        stage('Build CLI Args') {
            steps {
                script {
                    def envValue     = params.ENVIRONMENT ?: "autoprod"
                    def profileValue = params.LOAD_PROFILE ?: "baseline-minimal"
                    def loopVal      = params.LOOPLOGIN?.toString()?.toLowerCase() ?: "true"
                    def debugVal     = params.DEBUG?.toString()?.toLowerCase() ?: "false"

                    def durRaw = params.DURATION ?: ""
                    def durationVal =
                        (durRaw.trim() == "" || durRaw.trim() == "0")
                            ? null
                            : durRaw.toInteger()

                    def apisValueRaw = params.SELECTED_APIS ?: ""
                    def apisValue = []
                    if (apisValueRaw instanceof String && apisValueRaw.trim() != "") {
                        apisValue = apisValueRaw.split(",") as List
                    } else if (apisValueRaw instanceof List) {
                        apisValue = apisValueRaw
                    }

                    apisValue = apisValue.collect { it.trim() }

                    def loginSelected     = apisValue.any { it.equalsIgnoreCase("login") }
                    def nonLoginApis      = apisValue.findAll { !it.equalsIgnoreCase("login") }
                    def onlyLoginSelected = loginSelected && nonLoginApis.isEmpty()

                    def cliArgs = ""
                    cliArgs += "-Denv=${envValue} "
                    cliArgs += "-Dprofile=${profileValue} "
                    cliArgs += "-DloopLogin=${loopVal} "
                    cliArgs += "-Ddebug=${debugVal} "

                    if (durationVal != null)
                        cliArgs += "-Dduration=${durationVal} "

                    if (onlyLoginSelected) {
                        cliArgs += "-Dapis=login "
                    } else if (!nonLoginApis.isEmpty()) {
                        cliArgs += "-Dapis=${nonLoginApis.join(',')} "
                    }
                    // Resolve TARGET_HOST from environments.yaml
                    // ============================
                    def envYaml = readYaml file: 'config/environments.yaml'

                    if (!envYaml.containsKey(envValue)) {
                        error "ENVIRONMENT '${envValue}' not found in config/environments.yaml"
                    }

                    def host = envYaml[envValue].host
                    if (!host) {
                        error "No 'host' defined for ENVIRONMENT '${envValue}' in environments.yaml"
                    }

                    // Export for later stages
                    env.TARGET_HOST = host

                    echo """
FINAL CLI ARGS
--------------
${cliArgs}
"""
                    env.CLI_ARGS = cliArgs
                    env.ENVIRONMENT = envValue
                    env.LOAD_PROFILE = profileValue
                }
            }
        }

        /* ============================
         * STAGE 4 — Generate Dynamic JMX
         * ============================ */
        stage('Generate Test Plan') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      ${IMAGE_NAME} \
                      groovy ${CLI_ARGS} engine/generateTestPlan.groovy
                """

                script {
                    if (!fileExists("output/generated-test-plan.jmx")) {
                        error "❌ JMX generation failed!"
                    }
                }

                echo "Generated JMX at: output/generated-test-plan.jmx"
            }
        }

        /* ============================
         * STAGE 5 — Pre-flight Reasoning
         * ============================ */
        stage('Pre-flight Reasoning') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      -e ENVIRONMENT=${env.ENVIRONMENT} \
                      -e LOAD_PROFILE=${env.LOAD_PROFILE} \
                      -e TARGET_HOST=${params.TARGET_HOST ?: 'localhost'} \
                      -e REASONING_PHASE=preflight \
                      -e PYTHONPATH=${WORKDIR} \
                      ${IMAGE_NAME} \
                      python3 -m reasoning.main
                """
            }
        }

        /* ============================
         * STAGE 6 — Run JMeter
         * ============================ */
        stage('Run JMeter') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      ${IMAGE_NAME} \
                      sh -c '
                        rm -rf output/dashboard &&
                        jmeter -n \
                          -t output/generated-test-plan.jmx \
                          -l output/results.jtl \
                          -Jjmeter.save.saveservice.output_format=csv \
                          -Jjmeter.save.saveservice.assertion_results=none \
                          -Jjmeter.save.saveservice.data_type=true \
                          -Jjmeter.save.saveservice.label=true \
                          -Jjmeter.save.saveservice.response_code=true \
                          -Jjmeter.save.saveservice.response_message=true \
                          -Jjmeter.save.saveservice.successful=true \
                          -Jjmeter.save.saveservice.thread_name=true \
                          -Jjmeter.save.saveservice.time=true \
                          -Jjmeter.save.saveservice.latency=true \
                          -Jjmeter.save.saveservice.connect_time=true \
                          -Jjmeter.save.saveservice.bytes=true \
                          -Jjmeter.save.saveservice.sent_bytes=true \
                          -Jjmeter.save.saveservice.sample_count=true \
                          -Jjmeter.save.saveservice.error_count=true \
                          -Jjmeter.save.saveservice.hostname=true \
                          -Jjmeter.save.saveservice.timestamp=true \
                          -Jjmeter.save.saveservice.thread_counts=true \
                          -e -o output/dashboard
                      '
                """
            }
        }

        /* ============================
         * STAGE 7 — Post-run Reasoning
         * ============================ */
        stage('Post-run Reasoning') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      -e ENVIRONMENT=${env.ENVIRONMENT} \
                      -e LOAD_PROFILE=${env.LOAD_PROFILE} \
                      -e TARGET_HOST=${params.TARGET_HOST ?: 'localhost'} \
                      -e REASONING_PHASE=postrun \
                      -e PYTHONPATH=${WORKDIR} \
                      ${IMAGE_NAME} \
                      python3 -m reasoning.main
                """
            }
        }

        /* ============================
         * STAGE 8 — Executive Summary
         * ============================ */
        stage('Generate Executive Summary') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      ${IMAGE_NAME} \
                      python3 scripts/generate_executive_report.py \
                        output/dashboard/statistics.json \
                        output/executive
                """
            }
        }

        /* ============================
         * STAGE 9 — Package & Archive Reports
         * ============================ */
        stage('Archive Results') {
            steps {
                sh '''
                    cd output
                    rm -f performance-reports.zip
                    zip -r performance-reports.zip \
                        dashboard \
                        executive \
                        reasoning \
                        generated-test-plan.jmx
                '''

                archiveArtifacts artifacts: 'output/performance-reports.zip', fingerprint: true
                archiveArtifacts artifacts: 'output/results.jtl', fingerprint: true

                echo """
================= REPORT ACCESS =================

📦 DOWNLOAD:
   Artifacts → performance-reports.zip

📊 JMeter Dashboard:
   dashboard/index.html

📄 Executive Summary:
   executive/index.html

🧠 Performance Reasoning:
   reasoning/

⚠️ IMPORTANT:
   Do NOT open reports inside Jenkins UI.

=================================================
"""
            }
        }
    }

    post {
        success {
            echo "🎉 Pipeline completed successfully"
        }
        failure {
            echo "❌ Pipeline failed — see reasoning report for explanation"
        }
    }
}