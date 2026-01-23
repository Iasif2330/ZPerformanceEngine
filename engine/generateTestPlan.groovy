import groovy.xml.MarkupBuilder

// Load SnakeYAML
this. class .classLoader.addURL(new File("lib/snakeyaml.jar").toURI().toURL())

// Load YAML Loader
GroovyClassLoader gcl = new GroovyClassLoader(this. class .classLoader)
def yamlClass = gcl.parseClass(new File("engine/loadYaml.groovy"))
def YamlLoader = yamlClass.newInstance()

// Load configs
def envConfig = YamlLoader.load("config/environments.yaml")
def headersConfig = YamlLoader.load("config/headers.yaml")
def apiConfig = YamlLoader.load("config/apis.yaml")
def profileConfig = YamlLoader.load("config/load-profile.yaml")
def apiGroupsConfig = YamlLoader.load("config/api-groups.yaml")

// =========================
// Load assertions config
// =========================
def assertionsConfig = YamlLoader.load("config/assertions.yaml") ?: [:]
def defaultAssertions = assertionsConfig.defaults ?: []
def apiAssertionsMap = assertionsConfig.apis ?: [:]

// ===================================================================
// Resolve environment with structured summary
// ===================================================================

// Read CLI override
def cliEnv = System.getProperty("env")

// Default environment = autoprod
def selectedEnv = cliEnv ?: "autoprod"

// Validate environment exists in YAML
if (!envConfig.containsKey(selectedEnv)) {
    throw new IllegalArgumentException(
        "ERROR: Environment '${selectedEnv}' not found in environments.yaml"
    )
}

println ""
println "================= ENVIRONMENT SETTINGS ================="
println "CLI Environment (env)       : ${cliEnv ?: '(none)'}"
println "Default Environment Used     : ${cliEnv ? 'NO' : 'YES'}"
println "Final Environment Selected   : ${selectedEnv}"
println "========================================================"
println ""

def envName = selectedEnv

// ===================================================================
// Load profile
// ===================================================================

// =========================
// Load universal settings (allow empty)
// =========================
def universal = profileConfig["universal"] ?: [:]

def yamlLoopLogin = (universal.containsKey("loopLogin")) ? universal.loopLogin: null
def yamlDebug = (universal.containsKey("debug")) ? universal.debug: null
def yamlDuration = (universal.containsKey("duration")) ? universal.duration: null

// =========================
// Load CLI overrides
// =========================
def cliLoopLogin = System.getProperty("loopLogin")
def cliDebug = System.getProperty("debug")
def cliDuration = System.getProperty("duration")

// =========================
// Final merged values
// Priority: CLI > YAML > Default
// =========================
def loopLogin = (cliLoopLogin != null) ? cliLoopLogin.toBoolean(): 
(yamlLoopLogin != null && yamlLoopLogin.toString().trim() != "") ? yamlLoopLogin.toBoolean(): 
true   // default

def debugMode = (cliDebug != null) ? cliDebug.toBoolean(): 
(yamlDebug != null && yamlDebug.toString().trim() != "") ? yamlDebug.toBoolean(): 
false  // default

def duration = (cliDuration != null && cliDuration.toString().trim() != "")
 ? cliDuration.toInteger()
: (yamlDuration != null && yamlDuration.toString().trim() != "")
 ? yamlDuration.toInteger()
: 10000


// ===================================================================
// Load selected profile (fallback = baseline-minimal)
// ===================================================================
def cliProfile = System.getProperty("profile")
def profileName = cliProfile ?: "baseline-minimal"

def profile = profileConfig["profiles"].find {
    it.name == profileName
}
if (!profile) {
    throw new IllegalArgumentException("Profile '${profileName}' not found in load-profile.yaml")
}

// Extract profile-specific values
def threads = profile.threads
def rampup = profile.rampup
def apiLoopCount = profile.apiLoopCount


// ===================================================================
// Print Summary
// ===================================================================
println ""
println "================= LOAD SETTINGS SUMMARY ================="
println "Profile Requested (CLI)     : ${cliProfile ?: '(none)'}"
println "Profile Selected             : ${profileName}"
println "Threads                      : ${threads}"
println "Ramp-up                      : ${rampup}"
println "API Loop Count               : ${apiLoopCount}"
println ""
println "------- Universal / CLI Overrides -------"

// loopLogin source
def loopLoginSource = (cliLoopLogin != null) ? "CLI override": 
(yamlLoopLogin != null && yamlLoopLogin.toString().trim() != "") ? "YAML universal": 
"DEFAULT (true)"

// debug source
def debugSource = (cliDebug != null) ? "CLI override": 
(yamlDebug != null && yamlDebug.toString().trim() != "") ? "YAML universal": 
"DEFAULT (false)"

// duration source
def durationSource = (cliDuration != null) ? "CLI override": 
(yamlDuration != null && yamlDuration.toString().trim() != "") ? "YAML universal": 
"DEFAULT (unlimited)"

println "loopLogin                    : ${loopLogin}   (${loopLoginSource})"
println "debugMode                    : ${debugMode}   (${debugSource})"
println "duration                     : ${duration ?: 'UNLIMITED'}   (${durationSource})"
println "==========================================================="
println ""

// ===================================================================
def usersFile = new File("config/users/${envName}.csv").getAbsolutePath()

// ===================================================================
def baseUrl = envConfig[envName].baseUrl
def parsed = baseUrl.replace("https://", "").replace("http://", "")
def domain = parsed.contains("/") ? parsed.substring(0, parsed.indexOf("/")): parsed
def basePath = parsed.contains("/") ? parsed.substring(parsed.indexOf("/")): ""

// ===================================================================
// def resultsDir = new File("output/results")
// if (resultsDir.exists()) {
//     println "Cleaning previous results..."
//     resultsDir.deleteDir()
// }
// resultsDir.mkdirs()

// ===================================================================
// API Selection Logic
// ===================================================================
def apis = apiConfig.apis

def cliGroup = System.getProperty("group")
def cliApis = System.getProperty("apis")

def selectedApiNames = []

// =========================
// Handle API Group override
// =========================
if (cliGroup) {
    def groupList = apiGroupsConfig.groups[cliGroup]
    if (!groupList) {
        throw new IllegalArgumentException("Group '${cliGroup}' not found in api-groups.yaml")
    }
    selectedApiNames.addAll(groupList)
}

// =========================
// Handle explicit API override
// =========================
if (cliApis) {
    selectedApiNames.addAll(cliApis.split(","))
}

// =========================
// If nothing selected → run ALL APIs
// =========================
def decisionMessage = ""
def isSpecificApiSelection = (cliApis != null)

if (selectedApiNames.isEmpty()) {
    selectedApiNames = apis.collect {
        it.name
    }
    decisionMessage = "No CLI group or API filters → Running ALL APIs"
} else {
    decisionMessage = "CLI filters applied → Running filtered API list"
}

// Filter actual API objects
apis = apis.findAll {
    selectedApiNames.contains(it.name)
}

// ⭐ otherApis MUST be defined AFTER login is forced FIRST
// def otherApis = apis.drop(1)

// ===================================================================
// ENSURE LOGIN API IS FIRST
// ===================================================================

// NOTE: loginApi already declared earlier → do NOT redeclare it
loginApi = apiConfig.apis.find {
    it.name.toLowerCase() == "login"
}

if (!loginApi) {
    throw new IllegalStateException("No 'login' API found in apis.yaml")
}

// Remove login if already present
apis = apis.findAll {
    it.name != loginApi.name
}

// Prepend login API
apis = [loginApi] + apis

// ⭐ Build otherApis correctly AFTER fixing order
def otherApis = apis.drop(1)

// Update final name list
selectedApiNames = apis.collect {
    it.name
}

// ===================================================================
// Structured API Selection Summary
// ===================================================================
println ""
println "================= API SELECTION ================="
println "API Group Requested (CLI)   : ${cliGroup ?: '(none)'}"
println "Specific APIs (CLI)         : ${cliApis ?: '(none)'}"
println "Decision                    : ${decisionMessage}"

// Show final list ONLY when user selected specific APIs
if (isSpecificApiSelection) {
    println "Final API List              :"
    selectedApiNames.each {
        apiName -> println "  - ${apiName}"
    }
} else {
    println "Final API List              : (hidden — only shown for specific API selection)"
}

println "================================================="
println ""

// =========================
// YAML-driven assertion helpers (JSR223 ONLY)
// =========================


// =======================================================
// 1) JSR223 Response Code Assertion
// =======================================================
def buildResponseCodeJSR223Assertion = {
    builder, apiName, expectedCodes -> builder.JSR223Assertion(
        guiclass: "TestBeanGUI",
        testclass: "JSR223Assertion",
        testname: "${apiName}: Response Code Assertion",
        enabled: "true"
    ) {
        stringProp(name: "scriptLanguage", "groovy")
        boolProp(name: "cacheKey", "false")
        stringProp(
            name: "script",
            """
def actual = prev.getResponseCode()
def expected = ${expectedCodes.collect { "\"$it\"" }}

if (!expected.contains(actual)) {
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage(
        "Expected response code(s): ${expectedCodes}, but got: " + actual
    )
}
"""
        )
    }
}


// =======================================================
// 2) JSR223 Response Size > N Assertion
// =======================================================
def buildResponseSizeJSR223Assertion = {
    builder, apiName, minSize -> builder.JSR223Assertion(
        guiclass: "TestBeanGUI",
        testclass: "JSR223Assertion",
        testname: "${apiName}: Response Size > ${minSize}",
        enabled: "true"
    ) {
        stringProp(name: "scriptLanguage", "groovy")
        boolProp(name: "cacheKey", "false")
        stringProp(
            name: "script",
            """
def size = prev.getResponseData()?.length ?: 0

if (size <= ${minSize}) {
    AssertionResult.setFailure(true)
    AssertionResult.setFailureMessage(
        "Expected response size > ${minSize}, but got: " + size
    )
}
"""
        )
    }
}


// =======================================================
// 3) JSR223 Body NOT Contains Assertion
// =======================================================
def buildBodyNotContainsJSR223Assertion = {
    builder, apiName, forbiddenValues -> builder.JSR223Assertion(
        guiclass: "TestBeanGUI",
        testclass: "JSR223Assertion",
        testname: "${apiName}: Body Not Contains",
        enabled: "true"
    ) {
        stringProp(name: "scriptLanguage", "groovy")
        boolProp(name: "cacheKey", "false")
        stringProp(
            name: "script",
            """
def body = prev.getResponseDataAsString()
def forbidden = ${forbiddenValues.collect { "\"$it\"" }}

for (val in forbidden) {
    if (body != null && body.contains(val)) {
        AssertionResult.setFailure(true)
        AssertionResult.setFailureMessage(
            "Response body contains forbidden value: '" + val + "'"
        )
        break
    }
}
"""
        )
    }
}


// =======================================================
// 4) JSR223 Response HEADER NOT Contains Assertion
// =======================================================
def buildHeaderNotContainsJSR223Assertion = {
    builder, apiName, headerName, forbiddenValues -> builder.JSR223Assertion(
        guiclass: "TestBeanGUI",
        testclass: "JSR223Assertion",
        testname: "${apiName}: Header '${headerName}' Not Contains",
        enabled: "true"
    ) {
        stringProp(name: "scriptLanguage", "groovy")
        boolProp(name: "cacheKey", "false")
        stringProp(
            name: "script",
            """
def headers = prev.getResponseHeaders()
def headerValue = null

headers?.split("\\n")?.each { line ->
    if (line.toLowerCase().startsWith("${headerName.toLowerCase()}:")) {
        headerValue = line.split(":", 2)[1]?.trim()
    }
}

def forbidden = ${forbiddenValues.collect { "\"$it\"" }}

if (headerValue != null) {
    for (val in forbidden) {
        if (headerValue.toLowerCase().contains(val.toLowerCase())) {
            AssertionResult.setFailure(true)
            AssertionResult.setFailureMessage(
                "Response header '${headerName}' contains forbidden value: '" + val + "'"
            )
            break
        }
    }
}
"""
        )
    }
}


// =======================================================
// 5) Resolve assertions for API (UNCHANGED LOGIC)
// =======================================================
def resolveAssertionsForApi = { apiName ->
    if (apiAssertionsMap.containsKey(apiName)) {
        return apiAssertionsMap[apiName]
    }
    return defaultAssertions
}


// =======================================================
// 6) Dispatcher: YAML → JSR223 Assertions (UPDATED)
// =======================================================
def buildAssertionFromSpec = { builder, apiName, spec ->
    switch (spec.type) {

        case "response_code":
            buildResponseCodeJSR223Assertion(
                builder,
                apiName,
                spec.values
            )
            break

        case "response_size_gt":
            buildResponseSizeJSR223Assertion(
                builder,
                apiName,
                spec.value
            )
            break

        case "body_not_contains":
            buildBodyNotContainsJSR223Assertion(
                builder,
                apiName,
                spec.values
            )
            break

        case "header_not_contains":
            buildHeaderNotContainsJSR223Assertion(
                builder,
                apiName,
                spec.name,
                spec.values
            )
            break

        default:
            throw new IllegalArgumentException(
                "Unknown assertion type '${spec.type}' for API '${apiName}'"
            )
    }
}


// ===================================================================
// CLEAN old dashboard folder BEFORE generating new JMX/report
def dashDir = new File("output/dashboard")
if (dashDir.exists()) {
    println "Cleaning old dashboard folder..."
    dashDir.deleteDir()
}
// ===================================================================
def output = new File("output/generated-test-plan.jmx")
output.parentFile.mkdirs()
def writer = output.newWriter("UTF-8")
def xml = new MarkupBuilder(writer)
xml.omitNullAttributes = true

xml.jmeterTestPlan(version: "1.2", properties: "5.0", jmeter: "5.6.3") {
    hashTree {
        TestPlan(
            guiclass: "TestPlanGui",
            testclass: "TestPlan",
            testname: "Dynamic Test Plan",
            enabled: "true"
        ) {
            stringProp(name: "TestPlan.comments", "Env-aware, Dynamic API JMX Framework")
            stringProp(name: "httpclient4.retrycount", "0")
            stringProp(name: "httpclient3.retrycount", "0")
        }
        hashTree {
            // =========================
            // PROMETHEUS BACKEND LISTENER (TEST-PLAN LEVEL)
            // =========================
            BackendListener(
                guiclass: "BackendListenerGui",
                testclass: "BackendListener",
                testname: "Prometheus Listener",
                enabled: "true"
            ) {
                stringProp(
                    name: "classname",
                    "org.apache.jmeter.visualizers.backend.prometheus.PrometheusBackendListenerClient"
                )

                elementProp(name: "arguments", elementType: "Arguments") {
                    collectionProp(name: "Arguments.arguments") {

                        elementProp(name: "port", elementType: "Argument") {
                            stringProp(name: "Argument.name", "port")
                            stringProp(name: "Argument.value", "9270")
                            stringProp(name: "Argument.metadata", "=")
                        }

                        elementProp(name: "metrics_path", elementType: "Argument") {
                            stringProp(name: "Argument.name", "metrics_path")
                            stringProp(name: "Argument.value", "/metrics")
                            stringProp(name: "Argument.metadata", "=")
                        }
                        // 🔥 THIS IS THE IMPORTANT FIX 🔥
                        elementProp(name: "host", elementType: "Argument") {
                            stringProp(name: "Argument.name", "host")
                            stringProp(name: "Argument.value", "0.0.0.0")
                            stringProp(name: "Argument.metadata", "=")
                        }

                        elementProp(name: "percentiles", elementType: "Argument") {
                            stringProp(name: "Argument.name", "percentiles")
                            stringProp(name: "Argument.value", "90;95;99")
                            stringProp(name: "Argument.metadata", "=")
                        }

                        elementProp(name: "summary_only", elementType: "Argument") {
                            stringProp(name: "Argument.name", "summary_only")
                            stringProp(name: "Argument.value", "false")
                            stringProp(name: "Argument.metadata", "=")
                        }
                    }
                }
            }
            hashTree()
            ThreadGroup(
                guiclass: "ThreadGroupGui",
                testclass: "ThreadGroup",
                testname: "Main Thread Group",
                enabled: "true"
            ) {
                stringProp(name: "ThreadGroup.num_threads", threads.toString())
                stringProp(name: "ThreadGroup.ramp_time", rampup.toString())
                // FIX: scheduler must be ON only if duration exists
                boolProp(name: "ThreadGroup.scheduler", (duration != null && duration > 0).toString())
                // Only apply duration when explicitly passed AND > 0
                if (duration != null && duration > 0) {
                    stringProp(name: "ThreadGroup.duration", duration.toString())
                }
                elementProp(name: "ThreadGroup.main_controller", elementType: "LoopController") {
                    boolProp(name: "LoopController.continue_forever", "false")
                    stringProp(name: "LoopController.loops", loopLogin ? apiLoopCount.toString(): "1")
                }
                stringProp(name: "ThreadGroup.loop_count", "-1")
            }
            hashTree {
                CSVDataSet(
                    guiclass: "TestBeanGUI",
                    testclass: "CSVDataSet",
                    testname: "Users Loader",
                    enabled: "true"
                ) {
                    stringProp(name: "filename", usersFile)
                    stringProp(name: "variableNames", "username,password")
                    boolProp(name: "ignoreFirstLine", "true")
                    boolProp(name: "recycle", "true")
                    boolProp(name: "stopThread", "false")
                }
                hashTree()
                CookieManager(
                    guiclass: "CookiePanel",
                    testclass: "CookieManager",
                    testname: "Cookie Manager",
                    enabled: "true"
                ) {
                    boolProp(name: "CookieManager.clearEachIteration", "false")
                }
                hashTree()
                // 🔥 WARM-UP SAMPLER — ADD HERE 🔥
                TestAction(
                    guiclass: "TestActionGui",
                    testclass: "TestAction",
                    testname: "warmup",
                    enabled: "true"
                ) {
                    intProp(name: "ActionProcessor.action", 1)
                    longProp(name: "ActionProcessor.duration", 1)
                }
                hashTree()
                // LOGIN SAMPLER
                def login = loginApi
                def loginPayloadFile = (login.payload == "useEnv")
 ? envConfig[envName]?.payloads?.get(login.name)
: login.payload
                if (!loginPayloadFile) {
                    throw new IllegalStateException(
                        "Missing payload for LOGIN API '${login.name}' in environment '${envName}'"
                    )
                }
                def loginPayloadText = new File(loginPayloadFile).text
                HTTPSamplerProxy(
                    guiclass: "HttpTestSampleGui",
                    testclass: "HTTPSamplerProxy",
                    testname: login.name,
                    enabled: "true"
                ) {
                    boolProp(name: "HTTPSampler.follow_redirects", "false")
                    boolProp(name: "HTTPSampler.auto_redirects", "false")
                    boolProp(name: "HTTPSampler.image_parser", "false")
                    boolProp(name: "HTTPSampler.concurrentDwn", "false")
                    stringProp(name: "HTTPSampler.domain", domain)
                    stringProp(name: "HTTPSampler.protocol", baseUrl.startsWith("https") ? "https": "http")
                    stringProp(name: "HTTPSampler.path", basePath + login.endpoint)
                    stringProp(name: "HTTPSampler.method", login.method)
                    boolProp(name: "HTTPSampler.postBodyRaw", "true")
                    elementProp(name: "HTTPsampler.Arguments", elementType: "Arguments") {
                        collectionProp(name: "Arguments.arguments") {
                            elementProp(name: "body", elementType: "HTTPArgument") {
                                boolProp(name: "HTTPArgument.always_encode", "false")
                                stringProp(name: "Argument.value", loginPayloadText)
                                stringProp(name: "Argument.metadata", "=")
                            }
                        }
                    }
                }
                hashTree {
                    // CORRECT HEADERMANAGER FOR LOGIN
                    HeaderManager(
                        guiclass: "HeaderPanel",
                        testclass: "HeaderManager",
                        testname: "Headers for login",
                        enabled: "true"
                    ) {
                        'collectionProp'(name: "HeaderManager.headers") {
                            headersConfig["loginHeaders"].each {
                                k, v -> def resolved = v.replace("__BASE_URL__", baseUrl)
                                'elementProp'(name: k, elementType: "Header") {
                                    'stringProp'(name: "Header.name", k)
                                    'stringProp'(name: "Header.value", resolved)
                                }
                            }
                        }
                    }
                    hashTree()
                    if (debugMode) {
                        DebugPostProcessor(
                            guiclass: "TestBeanGUI",
                            testclass: "DebugPostProcessor",
                            testname: "Debug After Login",
                            enabled: "true"
                        )
                        hashTree()
                    }
                    // === YAML-DRIVEN ASSERTIONS FOR LOGIN ===
                    resolveAssertionsForApi(login.name).each {
                        spec -> buildAssertionFromSpec(delegate, login.name, spec)
                        hashTree()
                    }
                }
                // OTHER APIs
                otherApis.each {
                    api -> def payloadFile = (api.payload == "useEnv")
 ? envConfig[envName]?.payloads?.get(api.name)
: api.payload
                    if (!payloadFile) {
                        throw new IllegalStateException(
                            "Missing payload for API '${api.name}' in environment '${envName}'"
                        )
                    }
                    def payloadText = new File(payloadFile).text
                    HTTPSamplerProxy(
                        guiclass: "HttpTestSampleGui",
                        testclass: "HTTPSamplerProxy",
                        testname: api.name,
                        enabled: "true"
                    ) {
                        boolProp(name: "HTTPSampler.follow_redirects", "false")
                        boolProp(name: "HTTPSampler.auto_redirects", "false")
                        boolProp(name: "HTTPSampler.image_parser", "false")
                        boolProp(name: "HTTPSampler.concurrentDwn", "false")
                        stringProp(name: "HTTPSampler.domain", domain)
                        stringProp(name: "HTTPSampler.protocol", baseUrl.startsWith("https") ? "https": "http")
                        stringProp(name: "HTTPSampler.path", basePath + api.endpoint)
                        stringProp(name: "HTTPSampler.method", api.method)
                        boolProp(name: "HTTPSampler.postBodyRaw", "true")
                        elementProp(name: "HTTPsampler.Arguments", elementType: "Arguments") {
                            collectionProp(name: "Arguments.arguments") {
                                elementProp(name: "body", elementType: "HTTPArgument") {
                                    boolProp(name: "HTTPArgument.always_encode", "false")
                                    stringProp(name: "Argument.value", payloadText)
                                    stringProp(name: "Argument.metadata", "=")
                                }
                            }
                        }
                    }
                    hashTree {
                        // CORRECT HEADERMANAGER FOR APIs
                        HeaderManager(
                            guiclass: "HeaderPanel",
                            testclass: "HeaderManager",
                            testname: "Headers for ${api.name}",
                            enabled: "true"
                        ) {
                            'collectionProp'(name: "HeaderManager.headers") {
                                headersConfig["apiHeaders"].each {
                                    k, v -> def resolved = v.replace("__BASE_URL__", baseUrl)
                                    'elementProp'(name: k, elementType: "Header") {
                                        'stringProp'(name: "Header.name", k)
                                        'stringProp'(name: "Header.value", resolved)
                                    }
                                }
                            }
                        }
                        hashTree()
                        if (debugMode) {
                            DebugPostProcessor(
                                guiclass: "TestBeanGUI",
                                testclass: "DebugPostProcessor",
                                testname: "Debug After ${api.name}",
                                enabled: "true"
                            )
                            hashTree()
                        }
                        // ============================
                        // === YAML-DRIVEN ASSERTIONS FOR THIS API ===
                        resolveAssertionsForApi(api.name).each {
                            spec -> buildAssertionFromSpec(delegate, api.name, spec)
                            hashTree()
                        }
                    }
                }
            }
        }
    }
}

writer.close()
println "SUCCESS: VALID JMX GENERATED → output/generated-test-plan.jmx"