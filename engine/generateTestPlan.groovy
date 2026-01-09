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
def assertionsConfig = YamlLoader.load("config/assertions.yaml") ?: [:]

def defaultAssertions = assertionsConfig.defaults ?: []
def apiAssertionsMap  = assertionsConfig.apis ?: [:]

// ===================================================================
// Environment resolution
// ===================================================================
def cliEnv = System.getProperty("env")
def envName = cliEnv ?: "autoprod"

if (!envConfig.containsKey(envName)) {
    throw new IllegalArgumentException("Environment '${envName}' not found")
}

// ===================================================================
// Profile resolution
// ===================================================================
def cliProfile  = System.getProperty("profile")
def profileName = cliProfile ?: "baseline-minimal"

def profile = profileConfig.profiles.find { it.name == profileName }
if (!profile) {
    throw new IllegalArgumentException("Profile '${profileName}' not found")
}

def threads      = profile.threads
def rampup       = profile.rampup
def apiLoopCount = profile.apiLoopCount

// Universal overrides
def universal = profileConfig.universal ?: [:]

def loopLogin =
    System.getProperty("loopLogin")?.toBoolean() ?:
    universal.loopLogin?.toBoolean() ?: true

def debugMode =
    System.getProperty("debug")?.toBoolean() ?:
    universal.debug?.toBoolean() ?: false

def duration =
    System.getProperty("duration")?.toInteger() ?:
    universal.duration?.toInteger() ?: 10000

// ===================================================================
// API selection (CLI + login enforced)
// ===================================================================
def apis = apiConfig.apis
def cliGroup = System.getProperty("group")
def cliApis  = System.getProperty("apis")

def selectedApiNames = []

if (cliGroup) {
    def groupList = apiGroupsConfig.groups[cliGroup]
    if (!groupList) {
        throw new IllegalArgumentException("Group '${cliGroup}' not found")
    }
    selectedApiNames.addAll(groupList)
}

if (cliApis) {
    selectedApiNames.addAll(cliApis.split(","))
}

if (selectedApiNames.isEmpty()) {
    selectedApiNames = apis.collect { it.name }
}

// Filter APIs
apis = apis.findAll { selectedApiNames.contains(it.name) }

// Ensure login first
def loginApi = apiConfig.apis.find { it.name.toLowerCase() == "login" }
apis = apis.findAll { it.name != loginApi.name }
apis = [loginApi] + apis

// ===================================================================
// Assertion helpers
// ===================================================================
def resolveAssertionsForApi = { apiName ->
    apiAssertionsMap.containsKey(apiName)
        ? apiAssertionsMap[apiName]
        : defaultAssertions
}

def buildResponseAssertion = { builder, name, field, type, values, negate = false ->
    builder.ResponseAssertion(
        guiclass:"AssertionGui",
        testclass:"ResponseAssertion",
        testname:name,
        enabled:"true"
    ) {
        boolProp(name:"Assertion.not", negate.toString())
        intProp(name:"Assertion.test_field", field)
        intProp(name:"Assertion.test_type", type)
        collectionProp(name:"Assertion.test_strings") {
            values.each { k, v -> stringProp(name:k, v) }
        }
    }
}

def buildAssertionFromSpec = { builder, apiName, spec ->
    if (spec.type == "response_code") {
        buildResponseAssertion(
            builder,
            "${apiName}: Response Code",
            2, 2,
            spec.values.collectEntries { [(it.toString()): it.toString()] }
        )
    } else {
        throw new IllegalArgumentException("Unknown assertion type ${spec.type}")
    }
}

// ===================================================================
// JMX generation
// ===================================================================
def baseUrl  = envConfig[envName].baseUrl
def parsed   = baseUrl.replace("https://","").replace("http://","")
def domain   = parsed.contains("/") ? parsed.substring(0, parsed.indexOf("/")) : parsed
def basePath = parsed.contains("/") ? parsed.substring(parsed.indexOf("/")) : ""

def output = new File("output/generated-test-plan.jmx")
output.parentFile.mkdirs()
def writer = output.newWriter("UTF-8")
def xml = new MarkupBuilder(writer)

xml.jmeterTestPlan(version:"1.2", properties:"5.0", jmeter:"5.6.3") {
  hashTree {
    TestPlan(
      guiclass:"TestPlanGui",
      testclass:"TestPlan",
      testname:"Dynamic Test Plan",
      enabled:"true"
    ) {}

    hashTree {
      ThreadGroup(
        guiclass:"ThreadGroupGui",
        testclass:"ThreadGroup",
        testname:"Main Thread Group",
        enabled:"true"
      ) {
        stringProp(name:"ThreadGroup.num_threads", threads.toString())
        stringProp(name:"ThreadGroup.ramp_time", rampup.toString())
        boolProp(name:"ThreadGroup.scheduler", (duration > 0).toString())
        if (duration > 0) {
            stringProp(name:"ThreadGroup.duration", duration.toString())
        }
      }

      hashTree {

        apis.each { api ->

          def payloadFile = (api.payload == "useEnv")
            ? envConfig[envName].payloads[api.name]
            : api.payload

          HTTPSamplerProxy(
            guiclass:"HttpTestSampleGui",
            testclass:"HTTPSamplerProxy",
            testname:api.name,
            enabled:"true"
          ) {
            stringProp(name:"HTTPSampler.domain", domain)
            stringProp(name:"HTTPSampler.protocol", baseUrl.startsWith("https") ? "https" : "http")
            stringProp(name:"HTTPSampler.path", basePath + api.endpoint)
            stringProp(name:"HTTPSampler.method", api.method)
            boolProp(name:"HTTPSampler.postBodyRaw","true")

            elementProp(name:"HTTPsampler.Arguments", elementType:"Arguments") {
              collectionProp(name:"Arguments.arguments") {
                elementProp(name:"body", elementType:"HTTPArgument") {
                  stringProp(name:"Argument.value", new File(payloadFile).text)
                  stringProp(name:"Argument.metadata","=")
                }
              }
            }
          }

          hashTree {

            HeaderManager(
              guiclass:"HeaderPanel",
              testclass:"HeaderManager",
              testname:"Headers",
              enabled:"true"
            ) {
              'collectionProp'(name:"HeaderManager.headers") {
                def headers = api.name.toLowerCase() == "login"
                  ? headersConfig.loginHeaders
                  : headersConfig.apiHeaders

                headers.each { k,v ->
                  'elementProp'(name:k, elementType:"Header") {
                    'stringProp'(name:"Header.name",k)
                    'stringProp'(name:"Header.value",v.replace("__BASE_URL__", baseUrl))
                  }
                }
              }
            }
            hashTree()

            if (debugMode) {
              DebugPostProcessor(
                guiclass:"TestBeanGUI",
                testclass:"DebugPostProcessor",
                testname:"Debug",
                enabled:"true"
              )
              hashTree()
            }

            resolveAssertionsForApi(api.name).each { spec ->
              buildAssertionFromSpec(delegate, api.name, spec)
              hashTree()
            }
          }
        }
      }
    }
  }
}

writer.close()
println "SUCCESS: VALID JMX GENERATED"