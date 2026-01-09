import groovy.xml.MarkupBuilder

// --------------------------------------------------
// Dynamic JMX generator for environment-aware API testing
// - Reads YAML configs via `engine/loadYaml.groovy`
// - Produces `output/generated-test-plan.jmx`
// --------------------------------------------------

// Load SnakeYAML jar for YAML parsing
this.class.classLoader.addURL(new File('lib/snakeyaml.jar').toURI().toURL())

// Load YAML loader helper
GroovyClassLoader gcl = new GroovyClassLoader(this.class.classLoader)
def yamlClass = gcl.parseClass(new File('engine/loadYaml.groovy'))
def YamlLoader = yamlClass.newInstance()

// Load configuration files
def envConfig = YamlLoader.load('config/environments.yaml')
def headersConfig = YamlLoader.load('config/headers.yaml')
def apiConfig = YamlLoader.load('config/apis.yaml')
def profileConfig = YamlLoader.load('config/load-profile.yaml')
def apiGroupsConfig = YamlLoader.load('config/api-groups.yaml')

// -----------------------------
// Environment selection & summary
// -----------------------------
def cliEnv = System.getProperty('env')
def selectedEnv = cliEnv ?: 'autoprod'

if (!envConfig.containsKey(selectedEnv)) {
  throw new IllegalArgumentException("ERROR: Environment '${selectedEnv}' not found in environments.yaml")
}

println ''
println '================= ENVIRONMENT SETTINGS ================='
println "CLI Environment (env)       : ${cliEnv ?: '(none)'}"
println "Default Environment Used     : ${cliEnv ? 'NO' : 'YES'}"
println "Final Environment Selected   : ${selectedEnv}"
println '========================================================'
println ''

def envName = selectedEnv

// -----------------------------
// Load profile defaults and overrides
// -----------------------------
def universal = profileConfig['universal'] ?: [:]

def yamlLoopLogin = universal.containsKey('loopLogin') ? universal.loopLogin : null
def yamlDebug = universal.containsKey('debug') ? universal.debug : null
def yamlDuration = universal.containsKey('duration') ? universal.duration : null

def cliLoopLogin = System.getProperty('loopLogin')
def cliDebug = System.getProperty('debug')
def cliDuration = System.getProperty('duration')

// Merge priority: CLI > YAML > Default
def loopLogin = (cliLoopLogin != null) ? cliLoopLogin.toBoolean() :
  (yamlLoopLogin != null && yamlLoopLogin.toString().trim() != '') ? yamlLoopLogin.toBoolean() :
  true

def debugMode = (cliDebug != null) ? cliDebug.toBoolean() :
  (yamlDebug != null && yamlDebug.toString().trim() != '') ? yamlDebug.toBoolean() :
  false

def duration = (cliDuration != null && cliDuration.toString().trim() != '')
  ? cliDuration.toInteger()
  : (yamlDuration != null && yamlDuration.toString().trim() != '')
    ? yamlDuration.toInteger()
    : 10000

// -----------------------------
// Selected load profile
// -----------------------------
def cliProfile = System.getProperty('profile')
def profileName = cliProfile ?: 'baseline-minimal'

def profile = profileConfig['profiles'].find { it.name == profileName }
if (!profile) {
  throw new IllegalArgumentException("Profile '${profileName}' not found in load-profile.yaml")
}

def threads = profile.threads
def rampup = profile.rampup
def apiLoopCount = profile.apiLoopCount

// -----------------------------
// Print summary
// -----------------------------
println ''
println '================= LOAD SETTINGS SUMMARY ================='
println "Profile Requested (CLI)     : ${cliProfile ?: '(none)'}"
println "Profile Selected             : ${profileName}"
println "Threads                      : ${threads}"
println "Ramp-up                      : ${rampup}"
println "API Loop Count               : ${apiLoopCount}"
println ''
println '------- Universal / CLI Overrides -------'

def loopLoginSource = (cliLoopLogin != null) ? 'CLI override' :
  (yamlLoopLogin != null && yamlLoopLogin.toString().trim() != '') ? 'YAML universal' :
  'DEFAULT (true)'

def debugSource = (cliDebug != null) ? 'CLI override' :
  (yamlDebug != null && yamlDebug.toString().trim() != '') ? 'YAML universal' :
  'DEFAULT (false)'

def durationSource = (cliDuration != null) ? 'CLI override' :
  (yamlDuration != null && yamlDuration.toString().trim() != '') ? 'YAML universal' :
  'DEFAULT (unlimited)'

println "loopLogin                    : ${loopLogin}   (${loopLoginSource})"
println "debugMode                    : ${debugMode}   (${debugSource})"
println "duration                     : ${duration ?: 'UNLIMITED'}   (${durationSource})"
println '==========================================================='
println ''

// -----------------------------
// Basic derived values
// -----------------------------
def usersFile = new File("config/users/${envName}.csv").getAbsolutePath()

def baseUrl = envConfig[envName].baseUrl
def parsed = baseUrl.replace('https://', '').replace('http://', '')
def domain = parsed.contains('/') ? parsed.substring(0, parsed.indexOf('/')) : parsed
def basePath = parsed.contains('/') ? parsed.substring(parsed.indexOf('/')) : ''

// -----------------------------
// API selection
// -----------------------------
def apis = apiConfig.apis
def cliGroup = System.getProperty('group')
def cliApis = System.getProperty('apis')

def selectedApiNames = []

if (cliGroup) {
  def groupList = apiGroupsConfig.groups[cliGroup]
  if (!groupList) {
    throw new IllegalArgumentException("Group '${cliGroup}' not found in api-groups.yaml")
  }
  selectedApiNames.addAll(groupList)
}

if (cliApis) {
  selectedApiNames.addAll(cliApis.split(','))
}

def decisionMessage = ''
def isSpecificApiSelection = (cliApis != null)

if (selectedApiNames.isEmpty()) {
  selectedApiNames = apis.collect { it.name }
  decisionMessage = 'No CLI group or API filters → Running ALL APIs'
} else {
  decisionMessage = 'CLI filters applied → Running filtered API list'
}

// Keep only selected APIs
apis = apis.findAll { selectedApiNames.contains(it.name) }

// Ensure login API is first
loginApi = apiConfig.apis.find { it.name.toLowerCase() == 'login' }
if (!loginApi) {
  throw new IllegalStateException("No 'login' API found in apis.yaml")
}

apis = apis.findAll { it.name != loginApi.name }
apis = [loginApi] + apis
def otherApis = apis.drop(1)
selectedApiNames = apis.collect { it.name }

// Print API selection
println ''
println '================= API SELECTION ================='
println "API Group Requested (CLI)   : ${cliGroup ?: '(none)'}"
println "Specific APIs (CLI)         : ${cliApis ?: '(none)'}"
println "Decision                    : ${decisionMessage}"

if (isSpecificApiSelection) {
  println 'Final API List              :'
  selectedApiNames.each { apiName -> println "  - ${apiName}" }
} else {
  println 'Final API List              : (hidden — only shown for specific API selection)'
}

println '================================================='
println ''

// -----------------------------
// Assertion builder helper
// -----------------------------
def buildResponseAssertion = { builder, assertionName, testField, matchType, patternsMap, negate = false ->
  builder.ResponseAssertion(
    guiclass: 'AssertionGui',
    testclass: 'ResponseAssertion',
    testname: assertionName,
    enabled: 'true'
  ) {
    boolProp(name: 'Assertion.not', negate.toString())
    intProp(name: 'Assertion.test_type', matchType)
    intProp(name: 'Assertion.test_field', testField)

    collectionProp(name: 'Assertion.test_strings') {
      patternsMap.each { key, val -> stringProp(name: key, val) }
    }

    stringProp(name: 'Assertion.custom_message', '')
    boolProp(name: 'Assertion.assume_success', 'false')
  }
}

// -----------------------------
// Clean previous dashboard (if present)
// -----------------------------
def dashDir = new File('output/dashboard')
if (dashDir.exists()) {
  println 'Cleaning old dashboard folder...'
  dashDir.deleteDir()
}

// -----------------------------
// Build JMX using MarkupBuilder
// -----------------------------
def output = new File('output/generated-test-plan.jmx')
output.parentFile.mkdirs()
def writer = output.newWriter('UTF-8')
def xml = new MarkupBuilder(writer)
xml.omitNullAttributes = true

xml.jmeterTestPlan(version: '1.2', properties: '5.0', jmeter: '5.6.3') {
  hashTree {
    TestPlan(
      guiclass: 'TestPlanGui',
      testclass: 'TestPlan',
      testname: 'Dynamic Test Plan',
      enabled: 'true'
    ) {
      stringProp(name: 'TestPlan.comments', 'Env-aware, Dynamic API JMX Framework')
      stringProp(name: 'httpclient4.retrycount', '0')
      stringProp(name: 'httpclient3.retrycount', '0')
    }

    hashTree {
      ThreadGroup(
        guiclass: 'ThreadGroupGui',
        testclass: 'ThreadGroup',
        testname: 'Main Thread Group',
        enabled: 'true'
      ) {
        stringProp(name: 'ThreadGroup.num_threads', threads.toString())
        stringProp(name: 'ThreadGroup.ramp_time', rampup.toString())

        // scheduler ON only if duration is provided and > 0
        boolProp(name: 'ThreadGroup.scheduler', (duration != null && duration > 0).toString())
        if (duration != null && duration > 0) {
          stringProp(name: 'ThreadGroup.duration', duration.toString())
        }

        elementProp(name: 'ThreadGroup.main_controller', elementType: 'LoopController') {
          boolProp(name: 'LoopController.continue_forever', 'false')
          stringProp(name: 'LoopController.loops', loopLogin ? apiLoopCount.toString() : '1')
        }

        stringProp(name: 'ThreadGroup.loop_count', '-1')
      }

      hashTree {
        CSVDataSet(
          guiclass: 'TestBeanGUI',
          testclass: 'CSVDataSet',
          testname: 'Users Loader',
          enabled: 'true'
        ) {
          stringProp(name: 'filename', usersFile)
          stringProp(name: 'variableNames', 'username,password')
          boolProp(name: 'ignoreFirstLine', 'true')
          boolProp(name: 'recycle', 'true')
          boolProp(name: 'stopThread', 'false')
        }
        hashTree()

        CookieManager(
          guiclass: 'CookiePanel',
          testclass: 'CookieManager',
          testname: 'Cookie Manager',
          enabled: 'true'
        ) {
          boolProp(name: 'CookieManager.clearEachIteration', 'false')
        }
        hashTree()

        // LOGIN SAMPLER
        def login = loginApi
        def loginPayloadFile = (login.payload == 'useEnv') ? envConfig[envName].payloads[login.name] : login.payload

        HTTPSamplerProxy(
          guiclass: 'HttpTestSampleGui',
          testclass: 'HTTPSamplerProxy',
          testname: login.name,
          enabled: 'true'
        ) {
          boolProp(name: 'HTTPSampler.follow_redirects', 'false')
          boolProp(name: 'HTTPSampler.auto_redirects', 'false')
          boolProp(name: 'HTTPSampler.image_parser', 'false')
          boolProp(name: 'HTTPSampler.concurrentDwn', 'false')
          stringProp(name: 'HTTPSampler.domain', domain)
          stringProp(name: 'HTTPSampler.protocol', baseUrl.startsWith('https') ? 'https' : 'http')
          stringProp(name: 'HTTPSampler.path', basePath + login.endpoint)
          stringProp(name: 'HTTPSampler.method', login.method)
          boolProp(name: 'HTTPSampler.postBodyRaw', 'true')

          elementProp(name: 'HTTPsampler.Arguments', elementType: 'Arguments') {
            collectionProp(name: 'Arguments.arguments') {
              elementProp(name: 'body', elementType: 'HTTPArgument') {
                boolProp(name: 'HTTPArgument.always_encode', 'false')
                stringProp(name: 'Argument.value', new File(loginPayloadFile).text)
                stringProp(name: 'Argument.metadata', '=')
              }
            }
          }
        }

        hashTree {
          // Headers for login
          HeaderManager(
            guiclass: 'HeaderPanel',
            testclass: 'HeaderManager',
            testname: 'Headers for login',
            enabled: 'true'
          ) {
            'collectionProp'(name: 'HeaderManager.headers') {
              headersConfig['loginHeaders'].each { k, v ->
                def resolved = v.replace('__BASE_URL__', baseUrl)
                'elementProp'(name: k, elementType: 'Header') {
                  'stringProp'(name: 'Header.name', k)
                  'stringProp'(name: 'Header.value', resolved)
                }
              }
            }
          }
          hashTree()

          if (debugMode) {
            DebugPostProcessor(
              guiclass: 'TestBeanGUI',
              testclass: 'DebugPostProcessor',
              testname: 'Debug After Login',
              enabled: 'true'
            )
            hashTree()
          }

          // Assertions for LOGIN
          buildResponseAssertion(
            delegate,
            'Login Response Code Assertion',
            2,
            2,
            [code302: '302']
          )
          hashTree()
        }

        // OTHER APIs
        otherApis.each { api ->
          def payloadFile = (api.payload == 'useEnv') ? envConfig[envName].payloads[api.name] : api.payload

          HTTPSamplerProxy(
            guiclass: 'HttpTestSampleGui',
            testclass: 'HTTPSamplerProxy',
            testname: api.name,
            enabled: 'true'
          ) {
            boolProp(name: 'HTTPSampler.follow_redirects', 'false')
            boolProp(name: 'HTTPSampler.auto_redirects', 'false')
            boolProp(name: 'HTTPSampler.image_parser', 'false')
            boolProp(name: 'HTTPSampler.concurrentDwn', 'false')
            stringProp(name: 'HTTPSampler.domain', domain)
            stringProp(name: 'HTTPSampler.protocol', baseUrl.startsWith('https') ? 'https' : 'http')
            stringProp(name: 'HTTPSampler.path', basePath + api.endpoint)
            stringProp(name: 'HTTPSampler.method', api.method)
            boolProp(name: 'HTTPSampler.postBodyRaw', 'true')

            elementProp(name: 'HTTPsampler.Arguments', elementType: 'Arguments') {
              collectionProp(name: 'Arguments.arguments') {
                elementProp(name: 'body', elementType: 'HTTPArgument') {
                  boolProp(name: 'HTTPArgument.always_encode', 'false')
                  stringProp(name: 'Argument.value', new File(payloadFile).text)
                  stringProp(name: 'Argument.metadata', '=')
                }
              }
            }
          }

          hashTree {
            // Header manager for API
            HeaderManager(
              guiclass: 'HeaderPanel',
              testclass: 'HeaderManager',
              testname: "Headers for ${api.name}",
              enabled: 'true'
            ) {
              'collectionProp'(name: 'HeaderManager.headers') {
                headersConfig['apiHeaders'].each { k, v ->
                  def resolved = v.replace('__BASE_URL__', baseUrl)
                  'elementProp'(name: k, elementType: 'Header') {
                    'stringProp'(name: 'Header.name', k)
                    'stringProp'(name: 'Header.value', resolved)
                  }
                }
              }
            }
            hashTree()

            if (debugMode) {
              DebugPostProcessor(
                guiclass: 'TestBeanGUI',
                testclass: 'DebugPostProcessor',
                testname: "Debug After ${api.name}",
                enabled: 'true'
              )
              hashTree()
            }

            // ============================
            // ASSERTIONS FOR API: ${api.name}
            // ============================

            // 1) Response code must be 200
            ResponseAssertion(
              guiclass: 'AssertionGui',
              testclass: 'ResponseAssertion',
              testname: "${api.name}: Response Code = 200",
              enabled: 'true'
            ) {
              intProp(name: 'Assertion.test_field', 2)
              collectionProp(name: 'Assertion.test_strings') { stringProp(name: '200', '200') }
            }
            hashTree()

            // 2) Response body must not be empty
            SizeAssertion(
              guiclass: 'SizeAssertionGui',
              testclass: 'SizeAssertion',
              testname: "${api.name}: Response Body Not Empty",
              enabled: 'true'
            ) {
              stringProp(name: 'SizeAssertion.size', '0')
              stringProp(name: 'SizeAssertion.operator', '2')
            }
            hashTree()

            // 3) Response body must not contain "error"
            ResponseAssertion(
              guiclass: 'AssertionGui',
              testclass: 'ResponseAssertion',
              testname: "${api.name}: No 'error' in Body",
              enabled: 'true'
            ) {
              intProp(name: 'Assertion.test_field', 4)
              boolProp(name: 'Assertion.not', 'true')
              collectionProp(name: 'Assertion.test_strings') { stringProp(name: 'error', 'error') }
            }
            hashTree()
          }
        }
      }
    }
  }
}

writer.close()
println 'SUCCESS: VALID JMX GENERATED → output/generated-test-plan.jmx'
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