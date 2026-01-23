pipeline {
    agent any

    /* ============================
     * AUTO TRIGGER (SAFE – DOES NOT AFFECT ACTIVE CHOICES)
     * ============================ */
    triggers {
        // Daily run at 02:00 (Jenkins controller timezone)
        cron('0 2 * * *')

        // For testing only (uncomment temporarily if needed)
        // cron('* * * * *')
    }

    environment {
        DOCKER_CLI = "/Applications/Docker.app/Contents/Resources/bin/docker"
        IMAGE_NAME = "zperformance-engine"
        WORKDIR    = "/workspace"
        GRAFANA_URL    = "https://grafana-prod.ontic.ai"
        GRAFANA_DS_UID = "prometheus"
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
                    mkdir -p reasoning/baselines/snapshots
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

                    // ============================
                    // Parse SELECTED_APIS (UI only)
                    // ============================
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

                    // ============================
                    // Build CLI Args
                    // ============================
                    def cliArgs = ""
                    cliArgs += "-Denv=${envValue} "
                    cliArgs += "-Dprofile=${profileValue} "
                    cliArgs += "-DloopLogin=${loopVal} "
                    cliArgs += "-Ddebug=${debugVal} "

                    if (durationVal != null) {
                        cliArgs += "-Dduration=${durationVal} "
                    }

                    if (onlyLoginSelected) {
                        cliArgs += "-Dapis=login "
                    }
                    else if (!nonLoginApis.isEmpty()) {
                        cliArgs += "-Dapis=${nonLoginApis.join(',')} "
                    }
                    // else: NO -Dapis → engine runs ALL APIs

                    // ============================
                    // Resolve TARGET_HOST
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
                        error "Failed to resolve host for ENVIRONMENT '${envValue}'"
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
         * STAGE 4A — Generate FUNCTIONAL JMX (1 User)
         * ============================ */
        stage('Generate Functional Test Plan') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                    -v "${WORKSPACE}:${WORKDIR}" \
                    -w ${WORKDIR} \
                    ${IMAGE_NAME} \
                    groovy \
                        -Denv=${env.ENVIRONMENT} \
                        -Dprofile=baseline-minimal \
                        -DloopLogin=true \
                        engine/generateTestPlan.groovy

                    mv output/generated-test-plan.jmx output/functional-test-plan.jmx
                """

                script {
                    if (!fileExists("output/functional-test-plan.jmx")) {
                        error "❌ Functional JMX generation failed!"
                    }
                }

                echo "Generated FUNCTIONAL JMX at: output/functional-test-plan.jmx"
            }
        }
        /* ============================
         * STAGE 4B — Run Functional Test (1 User)
         * ============================ */
        stage('Run Functional Test') {
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                    -v "${WORKSPACE}:${WORKDIR}" \
                    -w ${WORKDIR} \
                    ${IMAGE_NAME} \
                    sh -c '
                        jmeter -n \
                        -t output/functional-test-plan.jmx \
                        -l output/functional_results.jtl \
                        -Jjmeter.save.saveservice.output_format=csv \
                        -Jjmeter.save.saveservice.label=true \
                        -Jjmeter.save.saveservice.successful=true \
                        -Jjmeter.save.saveservice.response_code=true
                    '
                """
            }
        }
        /* ============================
         * STAGE 4C — Resolve Functional Eligibility
         * ============================ */
        stage('Resolve Functional Eligibility') {
            steps {
                script {
                    def eligibleApis = sh(
                        script: """
                            awk -F',' '
                                NR>1 {
                                    label=\$3
                                    success=\$8
                                    if (success=="true") ok[label]=1
                                }
                                END {
                                    for (k in ok) print k
                                }
                            ' output/functional_results.jtl | paste -sd "," -
                        """,
                        returnStdout: true
                    ).trim()

                    if (!eligibleApis) {
                        echo "⚠️ No APIs eligible after functional test — load will be skipped"
                        env.ELIGIBLE_APIS = ""
                    } else {
                        env.ELIGIBLE_APIS = eligibleApis
                        echo "✅ Eligible APIs for load: ${eligibleApis}"
                    }
                }
            }
        }

        /* ============================
         * STAGE 4D — Generate LOAD Test Plan (FINAL)
         * ============================ */
        stage('Generate Load Test Plan') {
            when {
                expression { return env.ELIGIBLE_APIS?.trim() }
            }
            steps {
                sh """
                    ${DOCKER_CLI} run --rm \
                    -v "${WORKSPACE}:${WORKDIR}" \
                    -w ${WORKDIR} \
                    ${IMAGE_NAME} \
                    groovy \
                        -Denv=${env.ENVIRONMENT} \
                        -Dprofile=${env.LOAD_PROFILE} \
                        -DloopLogin=true \
                        -Dapis=${env.ELIGIBLE_APIS} \
                        engine/generateTestPlan.groovy
                """

                script {
                    if (!fileExists("output/generated-test-plan.jmx")) {
                        error "❌ Load JMX generation failed!"
                    }
                }

                echo "Generated LOAD JMX at: output/generated-test-plan.jmx"
            }
        }


        /* ============================
         * STAGE 5 — Pre-flight Reasoning
         * ============================ */
        stage('Pre-flight Reasoning') {
            when {
                expression { return env.ELIGIBLE_APIS?.trim() }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'grafana-readonly-token', variable: 'GRAFANA_API_TOKEN')
                ]) {
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
                        -e GRAFANA_URL=${env.GRAFANA_URL} \
                        -e GRAFANA_DS_UID=${env.GRAFANA_DS_UID} \
                        -e GRAFANA_API_TOKEN=${env.GRAFANA_API_TOKEN} \
                        -e SERVICE_NAME=captain-api \
                        ${IMAGE_NAME} \
                        python3 -m reasoning.main
                    """
                }
            }
        }

        /* ============================
         * STAGE 6 — Run JMeter
         * ============================ */
        stage('Run JMeter') {
            when {
                expression { return env.ELIGIBLE_APIS?.trim() }
            }
            steps {
                sh """
                    # -------------------------------
                    # Capture test start time (epoch seconds)
                    # -------------------------------
                    date +%s > output/test_start_ts

                    ${DOCKER_CLI} run --rm \
                    -v "${WORKSPACE}:${WORKDIR}" \
                    -w ${WORKDIR} \
                    ${IMAGE_NAME} \
                    sh -c '
                        set -e

                        rm -rf output/dashboard

                        # -------------------------------
                        # Start JMeter in BACKGROUND
                        # -------------------------------
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
                        -e -o output/dashboard &

                        JMETER_PID=\$!

                        echo ""
                        echo "===== PROMETHEUS METRICS (LIVE POLL) ====="

                        # ------------------------------------------------
                        # Poll /metrics WHILE JMeter is still running
                        # ------------------------------------------------
                        for i in \$(seq 1 20); do
                            if ps -p \$JMETER_PID > /dev/null; then
                                METRICS=\$(curl -s http://localhost:9270/metrics | grep jmeter_ | head -n 5)
                                if [ -n "\$METRICS" ]; then
                                    echo "\$METRICS"
                                    break
                                fi
                                sleep 1
                            else
                                break
                            fi
                        done

                        echo "=========================================="
                        echo ""

                        # -------------------------------
                        # Wait for JMeter to finish
                        # -------------------------------
                        wait \$JMETER_PID
                    '

                    # -------------------------------
                    # Capture test end time (epoch seconds)
                    # -------------------------------
                    date +%s > output/test_end_ts
                """
            }
        }


        /* ============================
         * STAGE 7 — Post-run Reasoning
         * ============================ */
        stage('Post-run Reasoning') {
            steps {
                withCredentials([
                    string(credentialsId: 'grafana-readonly-token', variable: 'GRAFANA_API_TOKEN')
                ]) {
                    sh """
                        ${DOCKER_CLI} run --rm \
                        -p 9270:9270 \
                        -v "${WORKSPACE}:${WORKDIR}" \
                        -w ${WORKDIR} \
                        -e ENVIRONMENT=${env.ENVIRONMENT} \
                        -e LOAD_PROFILE=${env.LOAD_PROFILE} \
                        -e TARGET_HOST=${env.TARGET_HOST} \
                        -e REASONING_PHASE=postrun \
                        -e PYTHONPATH=${WORKDIR} \
                        -e GRAFANA_URL=${env.GRAFANA_URL} \
                        -e GRAFANA_DS_UID=${env.GRAFANA_DS_UID} \
                        -e GRAFANA_API_TOKEN=${env.GRAFANA_API_TOKEN} \
                        -e SERVICE_NAME=captain-api \
                        ${IMAGE_NAME} \
                        python3 -m reasoning.main
                    """
                }
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
                        generated-test-plan.jmx \
                        functional-test-plan.jmx
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
    always {
        mail(
            from: 'aansari_c@ontic.co',
            to: 'aansari_c@ontic.co',
            subject: "[Jenkins] ${env.JOB_NAME} #${env.BUILD_NUMBER} — ${currentBuild.currentResult}",
            body: """
Job: ${env.JOB_NAME}
Build: #${env.BUILD_NUMBER}
Result: ${currentBuild.currentResult}

Environment: ${env.ENVIRONMENT}
Load Profile: ${env.LOAD_PROFILE}

Build URL:
${env.BUILD_URL}
"""
        )
    }

    success {
        echo "🎉 Pipeline completed successfully"
    }

    failure {
        echo "❌ Pipeline failed — see reasoning report for explanation"
    }
}
}