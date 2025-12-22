pipeline {
    agent any

    /* ============================
     * PARAMETERS (JENKINS UI)
     * ============================ */
    parameters {
        choice(name: 'ENVIRONMENT', choices: ['autoprod','qa','dev'], description: 'Target environment')
        choice(name: 'LOAD_PROFILE', choices: ['baseline-minimal','baseline','stress'], description: 'Load profile')
        booleanParam(name: 'LOOPLOGIN', defaultValue: true, description: 'Loop login requests')
        booleanParam(name: 'DEBUG', defaultValue: false, description: 'Enable debug mode')
        string(name: 'DURATION', defaultValue: '', description: 'Duration override (optional)')
        string(name: 'API_GROUPS', defaultValue: '', description: 'API groups (comma-separated)')
        string(name: 'SELECTED_APIS', defaultValue: '', description: 'Specific APIs (comma-separated)')
    }

    environment {
        DOCKER_CLI = "/Applications/Docker.app/Contents/Resources/bin/docker"
    }

    stages {

        /* ============================
         * STAGE 1 — Build Docker Image
         * ============================ */
        stage('Build Docker Image') {
            steps {
                script {
                    env.IMAGE_ID = sh(
                        script: "${DOCKER_CLI} build -q .",
                        returnStdout: true
                    ).trim()
                }
            }
        }

        /* ============================
         * STAGE 2 — Run Pipeline Inside Docker
         * ============================ */
        stage('Run Inside Docker') {
            steps {
                script {
                    docker.image(env.IMAGE_ID).inside("--entrypoint=''") {

                        /* ============================
                         * Prepare Workspace
                         * ============================ */
                        sh '''
                            rm -rf output
                            mkdir -p output
                        '''

                        /* ============================
                         * Build CLI Args
                         * ============================ */
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

                            def groupsValue = []
                            if (params.API_GROUPS?.trim()) {
                                groupsValue = params.API_GROUPS.split(",") as List
                            }

                            def apisValue = []
                            if (params.SELECTED_APIS?.trim()) {
                                apisValue = params.SELECTED_APIS.split(",") as List
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

                            env.CLI_ARGS = cliArgs

                            echo """
FINAL CLI ARGS
--------------
${cliArgs}
"""
                        }

                        /* ============================
                         * Generate Dynamic JMX
                         * ============================ */
                        sh '''
                            groovy ${CLI_ARGS} engine/generateTestPlan.groovy
                        '''

                        script {
                            if (!fileExists("output/generated-test-plan.jmx")) {
                                error "❌ JMX generation failed!"
                            }
                        }

                        /* ============================
                         * Run JMeter
                         * ============================ */
                        sh '''
                            rm -rf output/dashboard

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
                        '''

                        /* ============================
                         * Executive Summary
                         * ============================ */
                        sh '''
                            python3 scripts/generate_executive_report.py \
                              output/results.jtl \
                              output/executive
                        '''
                    }
                }
            }
        }

        /* ============================
         * STAGE 3 — Archive & Publish
         * ============================ */
        stage('Archive Results') {
            steps {
                archiveArtifacts artifacts: 'output/results.jtl', fingerprint: true
                archiveArtifacts artifacts: 'output/generated-test-plan.jmx', fingerprint: true
                archiveArtifacts artifacts: 'output/dashboard/**', fingerprint: true
                archiveArtifacts artifacts: 'output/executive/**', fingerprint: true

                publishHTML(target: [
                    allowMissing: false,
                    alwaysLinkToLastBuild: true,
                    keepAll: true,
                    reportDir: 'output/dashboard',
                    reportFiles: 'index.html',
                    reportName: 'JMeter HTML Report'
                ])

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

    post {
        success {
            echo "🎉 Pipeline completed successfully (Docker-based)"
        }
        failure {
            echo "❌ Pipeline failed — check logs"
        }
    }
}
