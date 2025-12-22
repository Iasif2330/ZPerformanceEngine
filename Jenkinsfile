pipeline {
    agent any

    environment {
        PROJECT_DIR = "/Users/Shared/ZPerformanceEngine"
        ENGINE_DIR  = "${PROJECT_DIR}/engine"
        OUTPUT_DIR  = "${PROJECT_DIR}/output"
        JMETER_HOME = "/Users/Shared/jmeter"
    }

    stages {

        /* ============================
         * STAGE 1 — Prepare Workspace
         * ============================ */
        stage('Prepare Workspace') {
            steps {
                script {
                    sh "mkdir -p ${OUTPUT_DIR}"
                    sh "rm -rf ${OUTPUT_DIR}/*"

                    sh "rm -rf $WORKSPACE/output"
                    sh "mkdir -p $WORKSPACE/output"
                }
            }
        }

        /* ============================
         * STAGE 2 — Build CLI Arguments
         * ============================ */
        stage('Build CLI Args') {
            steps {
                script {

                    def envValue     = params.ENVIRONMENT ?: "autoprod"
                    def profileValue = params.LOAD_PROFILE ?: "baseline-minimal"
                    def loopVal      = (params.LOOPLOGIN ?: "true").toString().toLowerCase()
                    def debugVal     = (params.DEBUG ?: "false").toString().toLowerCase()

                    def durRaw = params.DURATION ?: ""
                    def durationVal = (durRaw.trim() == "" || durRaw.trim() == "0")
                            ? null
                            : durRaw.toInteger()

                    def groupsValueRaw = params.API_GROUPS ?: ""
                    def groupsValue = []
                    if (groupsValueRaw instanceof String && groupsValueRaw.trim() != "") {
                        groupsValue = groupsValueRaw.split(",") as List
                    } else if (groupsValueRaw instanceof List) {
                        groupsValue = groupsValueRaw
                    }

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

                    if (!groupsValue.isEmpty())
                        cliArgs += "-Dgroup=${groupsValue.join(',')} "

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
         * STAGE 3 — Generate Dynamic JMX
         * ============================ */
        stage('Generate Test Plan') {
            steps {
                script {
                    sh """
                        cd ${PROJECT_DIR}
                        groovy ${env.CLI_ARGS} ${ENGINE_DIR}/generateTestPlan.groovy
                    """

                    if (!fileExists("${OUTPUT_DIR}/generated-test-plan.jmx")) {
                        error "❌ JMX generation failed!"
                    }

                    echo "Generated JMX at: ${OUTPUT_DIR}/generated-test-plan.jmx"
                }
            }
        }

        /* ============================
         * STAGE 4 — Run JMeter
         * ============================ */
        stage('Run JMeter') {
            steps {
                script {
                    sh "rm -rf ${OUTPUT_DIR}/dashboard"

                    sh """
                        ${JMETER_HOME}/bin/jmeter -n \
                        -t ${OUTPUT_DIR}/generated-test-plan.jmx \
                        -l ${OUTPUT_DIR}/results.jtl \
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
                        -e -o ${OUTPUT_DIR}/dashboard
                    """
                }
            }
        }

        /* ============================
         * STAGE 5 — Executive Summary (NEW)
         * ============================ */
        stage('Generate Executive Summary') {
            steps {
                script {
                    sh """
                        python3 ${PROJECT_DIR}/scripts/generate_executive_report.py \
                        ${OUTPUT_DIR}/results.jtl \
                        ${OUTPUT_DIR}/executive
                    """
                }
            }
        }

        /* ============================
         * STAGE 6 — Archive & Publish
         * ============================ */
        stage('Archive Results') {
            steps {
                script {
                    sh "rm -rf $WORKSPACE/output"
                    sh "mkdir -p $WORKSPACE/output"

                    sh """
                        cp ${OUTPUT_DIR}/results.jtl $WORKSPACE/output/
                        cp ${OUTPUT_DIR}/generated-test-plan.jmx $WORKSPACE/output/
                        cp -R ${OUTPUT_DIR}/dashboard $WORKSPACE/output/
                        cp -R ${OUTPUT_DIR}/executive $WORKSPACE/output/
                    """

                    archiveArtifacts artifacts: 'output/results.jtl', fingerprint: true
                    archiveArtifacts artifacts: 'output/generated-test-plan.jmx', fingerprint: true
                    archiveArtifacts artifacts: 'output/dashboard/**', fingerprint: true
                    archiveArtifacts artifacts: 'output/executive/**', fingerprint: true

                    /* Engineers */
                    publishHTML(target: [
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'output/dashboard',
                        reportFiles: 'index.html',
                        reportName: 'JMeter HTML Report'
                    ])

                    /* Clients */
                    publishHTML(target: [
                        allowMissing: false,
                        alwaysLinkToLastBuild: true,
                        keepAll: true,
                        reportDir: 'output/executive',
                        reportFiles: 'index.html',
                        reportName: 'Performance Summary'
                    ])
                }
            }
        }
    }

    post {
        success { echo "🎉 Pipeline completed successfully!" }
        failure { echo "❌ Pipeline failed — check logs" }
    }
}