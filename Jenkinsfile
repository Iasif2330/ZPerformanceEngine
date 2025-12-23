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

                    echo """
FINAL CLI ARGS
--------------
${cliArgs}
"""
                    env.CLI_ARGS = cliArgs
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
         * STAGE 5 — Run JMeter
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
         * STAGE 6 — Executive Summary
         * ============================ */
        stage('Generate Executive Summary') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                      -v "${WORKSPACE}:${WORKDIR}" \
                      -w ${WORKDIR} \
                      ${IMAGE_NAME} \
                      python3 scripts/generate_executive_report.py \
                        output/results.jtl \
                        output/executive
                """
            }
        }

        /* ============================
         * STAGE 7 — Package & Archive Reports
         * ============================ */
        stage('Archive Results') {
            steps {

                /* Create ONE distributable ZIP */
                sh '''
                    cd output
                    rm -f performance-reports.zip
                    zip -r performance-reports.zip dashboard executive
                '''

                /* Archive ONLY what users should download */
                archiveArtifacts artifacts: 'output/performance-reports.zip', fingerprint: true
                archiveArtifacts artifacts: 'output/results.jtl', fingerprint: true

                echo """
================= REPORT ACCESS =================

📦 DOWNLOAD:
   Artifacts → performance-reports.zip

📊 JMeter Dashboard:
   - Unzip
   - Open: dashboard/index.html (locally)

📄 Executive Summary:
   - Unzip
   - Open: executive/index.html (locally)

⚠️ IMPORTANT:
   Do NOT open reports inside Jenkins UI.
   Jenkins blocks JS/CSS for security reasons.

=================================================
"""
            }
        }
    }

    post {
        success {
            echo "🎉 Pipeline completed successfully (Docker-based)"
        }
        failure {
            echo "❌ Pipeline failed — check logs"
        }
    }
}
