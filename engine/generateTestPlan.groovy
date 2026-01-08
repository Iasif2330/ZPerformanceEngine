import groovy.xml.MarkupBuilder

// Load SnakeYAML
this.class.classLoader.addURL(new File("lib/snakeyaml.jar").toURI().toURL())

// Load YAML Loader
GroovyClassLoader gcl = new GroovyClassLoader(this.class.classLoader)
def yamlClass = gcl.parseClass(new File("engine/loadYaml.groovy"))
def YamlLoader = yamlClass.newInstance()

// Load configs
def envConfig        = YamlLoader.load("config/environments.yaml")
def headersConfig    = YamlLoader.load("config/headers.yaml")
def apiConfig        = YamlLoader.load("config/apis.yaml")
def profileConfig    = YamlLoader.load("config/load-profile.yaml")
def apiGroupsConfig  = YamlLoader.load("config/api-groups.yaml")

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

def yamlLoopLogin = (universal.containsKey("loopLogin")) ? universal.loopLogin : null
def yamlDebug     = (universal.containsKey("debug"))     ? universal.debug     : null
def yamlDuration  = (universal.containsKey("duration"))  ? universal.duration  : null

// =========================
// Load CLI overrides
// =========================
def cliLoopLogin = System.getProperty("loopLogin")
def cliDebug     = System.getProperty("debug")
def cliDuration  = System.getProperty("duration")

// =========================
// Final merged values
// Priority: CLI > YAML > Default
// =========================
def loopLogin =
    (cliLoopLogin != null) ? cliLoopLogin.toBoolean() :
    (yamlLoopLogin != null && yamlLoopLogin.toString().trim() != "") ? yamlLoopLogin.toBoolean() :
    true   // default

def debugMode =
    (cliDebug != null) ? cliDebug.toBoolean() :
    (yamlDebug != null && yamlDebug.toString().trim() != "") ? yamlDebug.toBoolean() :
    false  // default

def duration =
    (cliDuration != null && cliDuration.toString().trim() != "")
        ? cliDuration.toInteger()
        : (yamlDuration != null && yamlDuration.toString().trim() != "")
            ? yamlDuration.toInteger()
            : 10000


// ===================================================================
// Load selected profile (fallback = baseline-minimal)
// ===================================================================
def cliProfile = System.getProperty("profile")
def profileName = cliProfile ?: "baseline-minimal"

def profile = profileConfig["profiles"].find { it.name == profileName }
if (!profile) {
    throw new IllegalArgumentException("Profile '${profileName}' not found in load-profile.yaml")
}

// Extract profile-specific values
def threads      = profile.threads
def rampup       = profile.rampup
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
def loopLoginSource =
    (cliLoopLogin != null) ? "CLI override" :
    (yamlLoopLogin != null && yamlLoopLogin.toString().trim() != "") ? "YAML universal" :
    "DEFAULT (true)"

// debug source
def debugSource =
    (cliDebug != null) ? "CLI override" :
    (yamlDebug != null && yamlDebug.toString().trim() != "") ? "YAML universal" :
    "DEFAULT (false)"

// duration source
def durationSource =
    (cliDuration != null) ? "CLI override" :
    (yamlDuration != null && yamlDuration.toString().trim() != "") ? "YAML universal" :
    "DEFAULT (unlimited)"

println "loopLogin                    : ${loopLogin}   (${loopLoginSource})"
println "debugMode                    : ${debugMode}   (${debugSource})"
println "duration                     : ${duration ?: 'UNLIMITED'}   (${durationSource})"
println "==========================================================="
println ""

// ===================================================================
def usersFile = new File("config/users/${envName}.csv").getAbsolutePath()

// ===================================================================
def baseUrl  = envConfig[envName].baseUrl
def parsed   = baseUrl.replace("https://","").replace("http://","")
def domain   = parsed.contains("/") ? parsed.substring(0, parsed.indexOf("/")) : parsed
def basePath = parsed.contains("/") ? parsed.substring(parsed.indexOf("/")) : ""
// ===================================================================
// Resolve OCSC cookie value (must match apiHeaders.ocsh)
// ===================================================================
def ocscValue = headersConfig["apiHeaders"]?.ocsh
if (ocscValue != null && ocscValue.toString().trim() == "") {
    ocscValue = null
}

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
def cliApis  = System.getProperty("apis")

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
    selectedApiNames = apis.collect { it.name }
    decisionMessage = "No CLI group or API filters → Running ALL APIs"
} else {
    decisionMessage = "CLI filters applied → Running filtered API list"
}

// Filter actual API objects
apis = apis.findAll { selectedApiNames.contains(it.name) }

// ⭐ otherApis MUST be defined AFTER login is forced FIRST
// def otherApis = apis.drop(1)

// ===================================================================
// ENSURE LOGIN API IS FIRST
// ===================================================================

// NOTE: loginApi already declared earlier → do NOT redeclare it
loginApi = apiConfig.apis.find { it.name.toLowerCase() == "login" }

if (!loginApi) {
    throw new IllegalStateException("No 'login' API found in apis.yaml")
}

// Remove login if already present
apis = apis.findAll { it.name != loginApi.name }

// Prepend login API
apis = [loginApi] + apis

// ⭐ Build otherApis correctly AFTER fixing order
def otherApis = apis.drop(1)
// ===================================================================
// Determine if OCSC cookie is required for this run
// ===================================================================
def requiresOcsc =
    (loginApi?.requiresOcsc == true) ||
    otherApis.any { it.requiresOcsc == true }

if (requiresOcsc && !ocscValue) {
    throw new IllegalStateException(
        "API requires OCSC cookie, but apiHeaders.ocsh is missing"
    )
}

// Update final name list
selectedApiNames = apis.collect { it.name }

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
    selectedApiNames.each { apiName ->
        println "  - ${apiName}"
    }
} else {
    println "Final API List              : (hidden — only shown for specific API selection)"
}

println "================================================="
println ""

// ---------- ASSERTION BUILDER (PATCH) ----------
def buildResponseAssertion = { builder, assertionName, testField, matchType, patternsMap, negate = false ->

    builder.ResponseAssertion(
        guiclass: "AssertionGui",
        testclass: "ResponseAssertion",
        testname: assertionName,
        enabled: "true"
    ) {

        boolProp(name: "Assertion.not", negate.toString())
        intProp(name: "Assertion.test_type", matchType)
        intProp(name: "Assertion.test_field", testField)

        collectionProp(name: "Assertion.test_strings") {
            patternsMap.each { key, val ->
                stringProp(name: key, val)
            }
        }

        stringProp(name: "Assertion.custom_message", "")
        boolProp(name: "Assertion.assume_success", "false")
    }
}
// ---------- END PATCH ----------

// ===================================================================
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

xml.jmeterTestPlan(version:"1.2", properties:"5.0", jmeter:"5.6.3") {
  hashTree {

    TestPlan(
      guiclass:"TestPlanGui",
      testclass:"TestPlan",
      testname:"Dynamic Test Plan",
      enabled:"true"
    ) {
      stringProp(name:"TestPlan.comments","Env-aware, Dynamic API JMX Framework")
      stringProp(name:"httpclient4.retrycount","0")
      stringProp(name:"httpclient3.retrycount","0")
    }

    hashTree {

      ThreadGroup(
    guiclass:"ThreadGroupGui",
    testclass:"ThreadGroup",
    testname:"Main Thread Group",
    enabled:"true"
) {
    stringProp(name:"ThreadGroup.num_threads", threads.toString())
    stringProp(name:"ThreadGroup.ramp_time",  rampup.toString())

    // FIX: scheduler must be ON only if duration exists
    boolProp(name:"ThreadGroup.scheduler", (duration != null && duration > 0).toString())

    // Only apply duration when explicitly passed AND > 0
    if (duration != null && duration > 0) {
        stringProp(name:"ThreadGroup.duration", duration.toString())
    }

    elementProp(name:"ThreadGroup.main_controller", elementType:"LoopController") {
        boolProp(name:"LoopController.continue_forever","false")
        stringProp(name:"LoopController.loops", loopLogin ? apiLoopCount.toString() : "1")
    }

    stringProp(name:"ThreadGroup.loop_count","-1")
}

      hashTree {

        CSVDataSet(
          guiclass:"TestBeanGUI",
          testclass:"CSVDataSet",
          testname:"Users Loader",
          enabled:"true"
        ) {
          stringProp(name:"filename", usersFile)
          stringProp(name:"variableNames","username,password")
          boolProp(name:"ignoreFirstLine","true")
          boolProp(name:"recycle","true")
          boolProp(name:"stopThread","false")
        }
        hashTree()

        CookieManager(
          guiclass:"CookiePanel",
          testclass:"CookieManager",
          testname:"Cookie Manager",
          enabled:"true"
      ) {
        boolProp(name:"CookieManager.clearEachIteration","false")

        if (requiresOcsc && ocscValue) {
          collectionProp(name:"CookieManager.cookies") {
            elementProp(name:"ocsc", elementType:"Cookie") {
              stringProp(name:"Cookie.name",  "ocsc")
              stringProp(name:"Cookie.value", ocscValue)
              stringProp(name:"Cookie.domain", domain)
              stringProp(name:"Cookie.path",   "/rest/web/current/action/execute")
              boolProp(name:"Cookie.secure",   "false")
              boolProp(name:"Cookie.httpOnly","false")
            }
          }
        }
      }
    hashTree()

        // LOGIN SAMPLER
        def login = loginApi
        def loginPayloadFile = (login.payload == "useEnv")
          ? envConfig[envName].payloads[login.name]
          : login.payload

        HTTPSamplerProxy(
          guiclass:"HttpTestSampleGui",
          testclass:"HTTPSamplerProxy",
          testname: login.name,
          enabled:"true"
        ) {
          boolProp(name:"HTTPSampler.follow_redirects", "true")
          boolProp(name:"HTTPSampler.auto_redirects",  "true")
          boolProp(name:"HTTPSampler.image_parser", "false")
          boolProp(name:"HTTPSampler.concurrentDwn", "false")
          stringProp(name:"HTTPSampler.domain", domain)
          stringProp(name:"HTTPSampler.protocol", baseUrl.startsWith("https") ? "https" : "http")
          stringProp(name:"HTTPSampler.path", basePath + login.endpoint)
          stringProp(name:"HTTPSampler.method", login.method)
          boolProp(name:"HTTPSampler.postBodyRaw","true")

          elementProp(name:"HTTPsampler.Arguments", elementType:"Arguments") {
            collectionProp(name:"Arguments.arguments") {
              elementProp(name:"body", elementType:"HTTPArgument") {
                boolProp(name:"HTTPArgument.always_encode","false")
                stringProp(name:"Argument.value", new File(loginPayloadFile).text)
                stringProp(name:"Argument.metadata","=")
              }
            }
          }
        }

        hashTree {

          // CORRECT HEADERMANAGER FOR LOGIN
          HeaderManager(
            guiclass:"HeaderPanel",
            testclass:"HeaderManager",
            testname:"Headers for login",
            enabled:"true"
          ) {
            'collectionProp'(name:"HeaderManager.headers") {
              headersConfig["loginHeaders"].each { k, v ->
  def resolved = v.replace("__BASE_URL__", baseUrl)

  'elementProp'(name:k, elementType:"Header") {
    'stringProp'(name:"Header.name",  k)
    'stringProp'(name:"Header.value", resolved)
  }
}
            }
          }
          hashTree()

          if (debugMode) {
            DebugPostProcessor(
              guiclass:"TestBeanGUI",
              testclass:"DebugPostProcessor",
              testname:"Debug After Login",
              enabled:"true"
            )
            hashTree()
          }
          // === Assertions for LOGIN ===
            buildResponseAssertion(
        delegate,
        "Login Response Code Assertion",
        2,
        2,
        [code302: "302"]
      )
            hashTree()

            // ============================================================
            // FORCE COPY LOGIN RESPONSE COOKIES INTO COOKIE MANAGER
            // ============================================================
            JSR223PostProcessor(
            guiclass:"TestBeanGUI",
            testclass:"JSR223PostProcessor",
            testname:"Persist Login Cookies",
            enabled:"true"
            ) {
            stringProp(name:"scriptLanguage", "groovy")
            stringProp(name:"script", '''
        import org.apache.jmeter.protocol.http.control.Cookie
        import org.apache.jmeter.protocol.http.control.CookieManager

        // Find CookieManager in test plan
        CookieManager cm = null
        ctx.getEngine().getTestPlan().traverse { el ->
          if (el instanceof CookieManager) {
            cm = el
          }
        }

        if (cm == null) {
          log.error("❌ CookieManager not found")
          return
        }

        // Read Set-Cookie headers from LOGIN response
        def headers = prev.getResponseHeaders()
        headers.readLines()
          .findAll { it.toLowerCase().startsWith("set-cookie:") }
          .each { line ->

            // Strip "Set-Cookie:"
            def cookieDef = line.substring(11).trim()

            // Split name=value
            def parts = cookieDef.split(";", 2)
            def nameValue = parts[0].split("=", 2)

            if (nameValue.length != 2) return

            def name  = nameValue[0].trim()
            def value = nameValue[1].trim()

            def cookie = new Cookie(
              name,
              value,
              prev.getURL().getHost(),
              "/rest/web/current/action/execute",
              prev.isSecure(),
              0
            )

            cm.add(cookie)
            log.info("✅ Persisted login cookie: " + name)
          }
        ''')
            }
            hashTree()

            // LOGIN SAMPLER

          }

        // OTHER APIs
        otherApis.each { api ->

          def payloadFile = (api.payload == "useEnv")
            ? envConfig[envName].payloads[api.name]
            : api.payload

          HTTPSamplerProxy(
            guiclass:"HttpTestSampleGui",
            testclass:"HTTPSamplerProxy",
            testname: api.name,
            enabled:"true"
          ) {
            boolProp(name:"HTTPSampler.follow_redirects", "false")
            boolProp(name:"HTTPSampler.auto_redirects",  "false")
            boolProp(name:"HTTPSampler.image_parser", "false")
            boolProp(name:"HTTPSampler.concurrentDwn", "false")
            stringProp(name:"HTTPSampler.domain", domain)
            stringProp(name:"HTTPSampler.protocol", baseUrl.startsWith("https") ? "https" : "http")
            stringProp(name:"HTTPSampler.path", basePath + api.endpoint)
            stringProp(name:"HTTPSampler.method", api.method)
            boolProp(name:"HTTPSampler.postBodyRaw","true")

            elementProp(name:"HTTPsampler.Arguments", elementType:"Arguments") {
              collectionProp(name:"Arguments.arguments") {
                elementProp(name:"body",elementType:"HTTPArgument") {
                  boolProp(name:"HTTPArgument.always_encode","false")
                  stringProp(name:"Argument.value", new File(payloadFile).text)
                  stringProp(name:"Argument.metadata","=")
                }
              }
            }
          }

          hashTree {

            // CORRECT HEADERMANAGER FOR APIs
            HeaderManager(
              guiclass:"HeaderPanel",
              testclass:"HeaderManager",
              testname:"Headers for ${api.name}",
              enabled:"true"
            ) {
              'collectionProp'(name:"HeaderManager.headers") {
                headersConfig["apiHeaders"].each { k, v ->
  def resolved = v.replace("__BASE_URL__", baseUrl)

  'elementProp'(name:k, elementType:"Header") {
    'stringProp'(name:"Header.name",  k)
    'stringProp'(name:"Header.value", resolved)
  }
}
              }
            }
            hashTree()

            if (debugMode) {
              DebugPostProcessor(
                guiclass:"TestBeanGUI",
                testclass:"DebugPostProcessor",
                testname:"Debug After ${api.name}",
                enabled:"true"
              )
              hashTree()
            }
            // ============================
          // ASSERTIONS FOR API: ${api.name}
          // ============================

          // -----------------------------------------
          // 1) RESPONSE CODE MUST BE 200
          // -----------------------------------------
          ResponseAssertion(
            guiclass:"AssertionGui",
            testclass:"ResponseAssertion",
            testname:"${api.name}: Response Code = 200",
            enabled:"true"
          ) {
            intProp(name:"Assertion.test_field", 2)   // 2 = Response Code
            collectionProp(name:"Assertion.test_strings") {
              stringProp(name:"200", "200")
            }
          }
          hashTree()

          // -----------------------------------------
          // 2) RESPONSE BODY MUST NOT BE EMPTY
          // operator "2" means ">" in JMeter
          // -----------------------------------------
          SizeAssertion(
            guiclass:"SizeAssertionGui",
            testclass:"SizeAssertion",
            testname:"${api.name}: Response Body Not Empty",
            enabled:"true"
          ) {
            stringProp(name:"SizeAssertion.size", "0")
            stringProp(name:"SizeAssertion.operator", "2")  // > 0
          }
          hashTree()

          // -----------------------------------------
          // 3) RESPONSE BODY MUST NOT CONTAIN "error"
          // test_field "4" = Response Body
          // Assertion.not=true → NEGATE MATCH
          // -----------------------------------------
          ResponseAssertion(
            guiclass:"AssertionGui",
            testclass:"ResponseAssertion",
            testname:"${api.name}: No 'error' in Body",
            enabled:"true"
          ) {
            intProp(name:"Assertion.test_field", 4)   // 4 = BODY
            boolProp(name:"Assertion.not", "true")   // NEGATE
            collectionProp(name:"Assertion.test_strings") {
              stringProp(name:"error", "error")
            }
          }
          hashTree()
          }

        }

      }
    }
  }
}

writer.close()
println "SUCCESS: VALID JMX GENERATED → output/generated-test-plan.jmx"