pipeline {
    agent any

    /* ============================
     * AUTO TRIGGER (SCHEDULING)
     * ============================ */
    triggers {
        // 🔹 FIXED DAILY RUN (Jenkins controller timezone)
        cron('23 15 * * *')   // runs daily at 02:00

        // 🔹 FOR TESTING ONLY (uncomment temporarily)
        cron('* * * * *')   // runs every minute
    }

    /* ============================
     * PARAMETERS (REQUIRED)
     * ============================ */
    parameters {
        choice(
            name: 'ENVIRONMENT',
            choices: ['autoprod', 'staging', 'dev'],
            description: 'Target environment'
        )

        choice(
            name: 'LOAD_PROFILE',
            choices: ['baseline-minimal', 'baseline', 'stress'],
            description: 'Load profile'
        )

        string(
            name: 'DURATION',
            defaultValue: '',
            description: 'Duration in seconds (empty or 0 = profile default)'
        )

        string(
            name: 'SELECTED_APIS',
            defaultValue: '',
            description: 'Comma-separated APIs (empty = all)'
        )

        booleanParam(
            name: 'LOOPLOGIN',
            defaultValue: true,
            description: 'Loop login requests'
        )

        booleanParam(
            name: 'DEBUG',
            defaultValue: false,
            description: 'Enable debug logging'
        )
    }

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
                    def loopVal      = params.LOOPLOGIN.toString().toLowerCase()
                    def debugVal     = params.DEBUG.toString().toLowerCase()

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

                    // ============================
                    // Resolve TARGET_HOST from environments.yaml
                    // ============================
                    def host = sh(
                        script: """
                            awk '
                                \$1 == "${envValue}:" { in_env=1; next }
                                in_env && \$1 == "host:" { print \$2; exit }
                                in_env && /^[^ ]/ { exit }
                            ' config/environments.yaml
                        """,
                        returnStdout: true
                    ).trim()

                    if (!host) {
                        error "Failed to resolve host for ENVIRONMENT '${envValue}' from config/environments.yaml"
                    }

                    env.TARGET_HOST  = host
                    env.CLI_ARGS     = cliArgs
                    env.ENVIRONMENT  = envValue
                    env.LOAD_PROFILE = profileValue

                    echo """
FINAL CLI ARGS
--------------
${cliArgs}
"""
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
                      -e BUILD_NUMBER=${env.BUILD_NUMBER} \
                      -e ENVIRONMENT=${env.ENVIRONMENT} \
                      -e LOAD_PROFILE=${env.LOAD_PROFILE} \
                      -e TARGET_HOST=${env.TARGET_HOST} \
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
                      -e BUILD_NUMBER=${env.BUILD_NUMBER} \
                      -e ENVIRONMENT=${env.ENVIRONMENT} \
                      -e LOAD_PROFILE=${env.LOAD_PROFILE} \
                      -e TARGET_HOST=${env.TARGET_HOST} \
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