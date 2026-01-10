pipeline {
    agent any

    /* ============================
     * BUILD PARAMETERS
     * ============================ */
    parameters {
        string(
            name: 'ENVIRONMENT',
            defaultValue: 'autoprod',
            description: 'Logical environment (autoprod, staging, prod)'
        )
        string(
            name: 'LOAD_PROFILE',
            defaultValue: 'baseline-minimal',
            description: 'Load profile name'
        )
        string(
            name: 'TARGET_HOST',
            defaultValue: 'localhost',
            description: 'Target host / base URL for network health checks (e.g. api.mycompany.com)'
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
        string(
            name: 'DURATION',
            defaultValue: '',
            description: 'Test duration in ms (blank = default)'
        )
        string(
            name: 'SELECTED_APIS',
            defaultValue: '',
            description: 'Comma-separated API list'
        )
    }

    /* ============================
     * PIPELINE ENV
     * ============================ */
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
                sh "${DOCKER_CLI} build -t ${IMAGE_NAME} ."
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
                    // Promote parameters to environment
                    env.ENVIRONMENT  = params.ENVIRONMENT
                    env.LOAD_PROFILE = params.LOAD_PROFILE
                    env.TARGET_HOST  = params.TARGET_HOST

                    def loopVal  = params.LOOPLOGIN.toString().toLowerCase()
                    def debugVal = params.DEBUG.toString().toLowerCase()

                    def cliArgs = ""
                    cliArgs += "-Denv=${env.ENVIRONMENT} "
                    cliArgs += "-Dprofile=${env.LOAD_PROFILE} "
                    cliArgs += "-DloopLogin=${loopVal} "
                    cliArgs += "-Ddebug=${debugVal} "

                    if (params.DURATION?.trim()) {
                        cliArgs += "-Dduration=${params.DURATION} "
                    }

                    if (params.SELECTED_APIS?.trim()) {
                        cliArgs += "-Dapis=${params.SELECTED_APIS} "
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
                      jmeter -n \
                        -t output/generated-test-plan.jmx \
                        -l output/results.jtl \
                        -e -o output/dashboard
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
         * STAGE 9 — Archive Results
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