import org.jenkinsci.plugins.workflow.steps.FlowInterruptedException
import java.text.DecimalFormat
import hudson.tasks.test.AbstractTestResultAction
import groovy.json.*


//functions scan source code
def getSonarQubeAnalysisResult(sonarQubeURL, projectKey) {
    def metricKeys = "bugs,vulnerabilities,code_smells"
    def measureResp = httpRequest([
        acceptType : 'APPLICATION_JSON',
        httpMode   : 'GET',
        contentType: 'APPLICATION_JSON',
        url        : "${sonarQubeURL}/api/measures/component?metricKeys=${metricKeys}&component=${projectKey}"
    ])
    def measureInfo = jenkinsfile_utils.jsonParse(measureResp.content)
    def metricResultList = measureInfo['component']['measures']
    echo "${metricResultList}"
    int bugsEntry = getMetricEntryByKey(metricResultList, "bugs")['value'] as Integer
    int vulnerabilitiesEntry = getMetricEntryByKey(metricResultList, "vulnerabilities")['value'] as Integer
    int codeSmellEntry = getMetricEntryByKey(metricResultList, "code_smells")['value'] as Integer
    return ["bugs": bugsEntry, "vulnerabilities": vulnerabilitiesEntry, "code_smells" : codeSmellEntry ]
}

def getMetricEntryByKey(metricResultList, metricKey) {
    for (metricEntry in metricResultList) {
        if (metricEntry["metric"] == metricKey) {
            echo "${metricEntry}"
            return metricEntry
        }
    }
    return null
}

@NonCPS
def genSonarQubeProjectKey() {
    def sonarqubeProjectKey = ""
    if ("${env.gitlabActionType}".toString() == "PUSH" || "${env.gitlabActionType}".toString() == "TAG_PUSH") {
        sonarqubeProjectKey = "${env.groupName}:${env.gitlabSourceRepoName}:${env.gitlabSourceBranch}"
    } else if ("${env.gitlabActionType}".toString() == "MERGE" || "${env.gitlabActionType}".toString() == "NOTE") {
        sonarqubeProjectKey = "MR-${env.gitlabSourceRepoName}:${env.gitlabSourceBranch}-to-" +
            "${env.gitlabTargetBranch}"
    }
    return sonarqubeProjectKey.replace('/', '-')
}
@NonCPS
def getProjectCodeCoverageInfo(coverageInfoXmlStr) {
    def coverageInfoXml = jenkinsfile_utils.parseXml(coverageInfoXmlStr)
    def coverageResult=[:]
    def coverageInfoStr = ""
    int coveragePercentLine
    coverageInfoXml.counter.each {
        def coverageType = it.@type as String
        int missed = (it.@missed as String) as Integer
        int covered = (it.@covered as String) as Integer
        int total = missed + covered

        def coveragePercent = 0.00
        if (total > 0) {
            coveragePercent = Double.parseDouble(
                new DecimalFormat("###.##").format(covered * 100.0 / total))
        }
        coverageInfoStr += "- <b>${coverageType}</b>: <i>${covered}</i>/<i>${total}</i> (<b>${coveragePercent}%</b>)<br/>"
        if(coverageType == 'LINE'){
            coveragePercentLine = coveragePercent as Integer
            echo "Line Coverage: $coveragePercentLine"
        }
    }
    coverageResult["coverageInfoStr"] = coverageInfoStr
    coverageResult["LineCoverage"] = coveragePercentLine
    return coverageResult
}
@NonCPS
def getTestResultFromJenkins() {
    def testResult = [:]
    AbstractTestResultAction testResultAction = currentBuild.rawBuild.getAction(AbstractTestResultAction.class)
    testResult["total"] = testResultAction.totalCount
    testResult["failed"] = testResultAction.failCount
    testResult["skipped"] = testResultAction.skipCount
    testResult["passed"] = testResultAction.totalCount - testResultAction.failCount - testResultAction.skipCount
    return testResult
}
//
def sonarQubeScan(buildType) {
    stage("Checkout Source Code") {
        jenkinsfile_utils.checkoutSourceCode(buildType)
        echo  'Checkout source code'
    }
    stage('SonarQube analysis') {
        env.SONAR_QUBE_PROJECT_KEY = genSonarQubeProjectKey()
        withSonarQubeEnv('SONARQ_V6'){
            sh(returnStatus: true, script: 
                "/home/app/server/sonar-scanner/bin/sonar-scanner " +
                "-Dsonar.projectName=${env.SONAR_QUBE_PROJECT_KEY} " +
                "-Dsonar.projectKey=${env.SONAR_QUBE_PROJECT_KEY} " +
                "-Dsonar.java.binaries=. " +
                "-Dsonar.sources=. " +
                "-Dsonar.exclusions=**/target/**,**/Libs/**"
            )
                sh 'ls -al'
                sh 'cat .scannerwork/report-task.txt'
                def props = readProperties file: '.scannerwork/report-task.txt'
                env.SONAR_CE_TASK_ID = props['ceTaskId']
                env.SONAR_PROJECT_KEY = props['projectKey']
                env.SONAR_SERVER_URL = props['serverUrl']
                env.SONAR_DASHBOARD_URL = props['dashboardUrl']

                echo "SONAR_SERVER_URL: ${env.SONAR_SERVER_URL}"
                echo "SONAR_PROJECT_KEY: ${env.SONAR_PROJECT_KEY}"
                echo "SONAR_DASHBOARD_URL: ${env.SONAR_DASHBOARD_URL}"
            }
    }

    stage("3.3. Quality Gate") {
        def qg = null
        try {
            def sonarQubeRetry = 0
            def sonarScanCompleted = false
            while (!sonarScanCompleted) {
                try {
                    sleep 10
                    timeout(time: 1, unit: 'MINUTES') {
                        script {
                            qg = waitForQualityGate()
                            sonarScanCompleted = true
                            if (qg.status != 'OK') {
                                if (env.bypass == 'true') {
                                    echo "Sonar contain error"
                                }else {
                                    error "Pipeline failed due to quality gate failure: ${qg.status}"
                                }
                            }
                        }
                    }
                } catch (FlowInterruptedException interruptEx) {
                    // check if exception is system timeout
                    if (interruptEx.getCauses()[0] instanceof org.jenkinsci.plugins.workflow.steps.TimeoutStepExecution.ExceededTimeout) {
                        if (sonarQubeRetry <= 10) {
                            sonarQubeRetry += 1
                        } else {
                            if (env.bypass == 'true') {
                                echo "Sonar contain error"
                            } else {
                                error "Cannot get result from Sonarqube server. Build Failed."
                            } 
                        }
                    } else {
                        throw interruptEx
                    }
                }
                catch (err) {
                    throw err
                }
            }
        }
        catch (err) {
            throw err
        } finally {
            def codeAnalysisResult = getSonarQubeAnalysisResult(env.SONAR_SERVER_URL, env.SONAR_PROJECT_KEY)
            def sonarQubeAnalysisStr = "- Vulnerabilities: <b>${codeAnalysisResult["vulnerabilities"]}</b> <br/>" +
                "- Bugs: <b>${codeAnalysisResult["bugs"]}</b> <br/>" +
                "- Code Smell: <b>${codeAnalysisResult["code_smells"]}</b> <br/>"
            def sonarQubeAnalysisComment = "<b>SonarQube Code Analysis Result: ${qg.status}</b> <br/><br/>${sonarQubeAnalysisStr} " +
                "<i><a href='${SONAR_DASHBOARD_URL}'>" +
                "Details SonarQube Code Analysis Report...</a></i><br/><br/>"
            env.SONAR_QUBE_SCAN_RESULT_STR = sonarQubeAnalysisComment
            if ("${env.gitlabActionType}".toString() == "MERGE" || "${env.gitlabActionType}".toString() == "NOTE") {
                echo "check vulnerabilities, code smell and bugs"
                int maximumAllowedVulnerabilities = env.MAXIMUM_ALLOWED_VUNERABILITIES as Integer
                int maximumAllowedBugs = env.MAXIMUM_ALLOWED_BUGS as Integer
                int maximumAllowedCodeSmell = env.MAXIMUM_ALLOWED_CODE_SMELL as Integer
                echo "maximum allow vulnerabilities:  ${maximumAllowedVulnerabilities} "
                echo "maximum allow bugs:  ${maximumAllowedBugs}"
                echo "maximum allow code smell:  ${maximumAllowedCodeSmell}"
                if (codeAnalysisResult["vulnerabilities"] > maximumAllowedVulnerabilities ||
                    codeAnalysisResult["bugs"] > maximumAllowedBugs || codeAnalysisResult["code_smells"] > maximumAllowedCodeSmell) {
                    if (env.bypass == 'true') {
                        echo "Vulnerability, code smell or bug number overs allowed limits!"
                    } else {
                        error "Vulnerability, code smell or bug number overs allowed limits!"
                    } 
                    
                }
            }
        }
    }
}
def unitTestAndCodeCoverage(buildType){
    stage("Checkout source code"){
        jenkinsfile_utils.checkoutSourceCode(buildType)
    }
	stage("Unit Test & Code Coverage"){
        try {
            sh """
            mvn clean test org.jacoco:jacoco-maven-plugin:0.8.5:report-aggregate
            """
            echo "code coverage done"
            jacoco([
                classPattern: 'target/classes',
                sourcePattern: 'src/main/java'
            ])
            def coverageResultStrComment = "<b>Coverage Test Result:</b> <br/><br/>"
            def coverageInfoXmlStr = readFile "target/jacoco-aggregate-report/jacoco.xml"
            def getCoverageResult = getProjectCodeCoverageInfo(coverageInfoXmlStr)
            echo "Coverage Info: ${getCoverageResult["coverageInfoStr"]} "
            coverageResultStrComment += getCoverageResult["coverageInfoStr"]
            echo "Coverage Info: ${getProjectCodeCoverageInfo(coverageInfoXmlStr)} "
            coverageResultStrComment += "<i><a href='${env.BUILD_URL}Code-Coverage-Report/jacoco'>" +
                                        "Details Code Coverage Test Report...</a></i><br/><br/>"
            env.CODE_COVERAGE_RESULT_STR = coverageResultStrComment
            env.LINE_COVERAGE= getCoverageResult["LineCoverage"]
	    } catch (err) {
            echo "Error when test Unit Test"
            throw err
	    } finally {
            sh 'ls -al'
            //junit '*/target/*-results/test/TEST-*.xml'
            junit 'target/surefire-reports/TEST-*.xml'
            def unitTestResult = getTestResultFromJenkins()

            env.UNIT_TEST_PASSED = unitTestResult["passed"]
            env.UNIT_TEST_FAILED = unitTestResult["failed"]
            env.UNIT_TEST_SKIPPED = unitTestResult["skipped"]
            env.UNIT_TEST_TOTAL = unitTestResult["total"]

            def testResultContent = "- Passed: <b>${unitTestResult['passed']}</b> <br/>" +
                                    "- Failed: <b>${unitTestResult['failed']}</b> <br/>" +
                                    "- Skipped: <b>${unitTestResult['skipped']}</b> <br/>"

            def testResultString = 	"<b> Unit Test Result:</b> <br/><br/>${testResultContent} " +
                                    "<i><a href='${env.BUILD_URL}testReport/'>Details Unit Test Report...</a></i><br/><br/>"
            env.UNIT_TEST_RESULT_STR = testResultString
            int lineCoverage= env.LINE_COVERAGE as Integer
            // int lineCoverage= 100
            int maxAllowLineCoverage = env.MAXIMUM_ALLOWED_LINE_COVERAGE as Integer
            // if(lineCoverage < maxAllowLineCoverage){
            //     error "Line Coverage < 50%"
            //     env.CODE_COVERAGE_RESULT_STR += "Failed Line Coverage: $lineCoverage < $smaxAllowLineCoverag %"
            // }
            if (unitTestResult['failed'] > 0) {
                error "Failed ${unitTestResult['failed']} unit tests"
                env.UNIT_TEST_RESULT_STR += "Failed ${unitTestResult['failed']} unit tests"
            }
	    }
    }
}
/*
    - Build all module.
    - change module to build in def buildService
*/
def buildService(buildType) {
    stage("Checkout Source Code") {
        jenkinsfile_utils.checkoutSourceCode(buildType)
        echo  'Checkout source code'
    }
    stage('Build module back end'){
        try{
            def folder = sh(script: 'pwd', returnStdout: true)
            env.buildFolderResult = folder.trim()
            sh """
                sh ./cicd/build.sh ${env.project_version}
            """
        } catch(err){
            error "Build Failure"   
        }
       
    }
}
def pushImageDocker(){

    withCredentials([usernamePassword(credentialsId: 'vinhtx3-habor', usernameVariable: 'username',
        passwordVariable: 'password')]){
        sh """
            docker --config ~/.docker/.vinhtx3 login -u ${username} -p '${password}' 10.60.156.72
        """
    }
    dir("$env.buildFolderResult"){
        echo "Push image to habor"
        /*
          enable start push image tới docker bằng cách bỏ comment các dòng dưới đây:
        */
        sh """
            sh cicd/push.sh ${env.project_version}
        """
    }
   
}
/*
  Fuctions dùng để deploy lên server test dùng ansible--- 
*/
/*
def deploy_module_web(server,groupId,artifactId){
    echo "deploy to server ${server}"
    sh """
        pwd
        ansible-playbook cicd/deploy/deploy_file_${server}.yml -e groupId=${groupId} -e artifactId=${artifactId} -e BUILD_NUMBER=${BUILD_NUMBER}
    """
}
*/
def release2k8s(enviroment,service,configFile){
    sh """
        if [ -d "${service}-release" ]; then
            echo "file exits";
        else mkdir ${service}-release && echo "create folder"
        fi;
        cd ${service}-release
    """
    checkout changelog: true, poll: true, scm: [
            $class                           :  'GitSCM',
            branches                         : [[name: "master"]],
            doGenerateSubmoduleConfigurations: false,
            extensions                       : [[$class: 'UserIdentity',
                                                email : 'hienptt22@viettel.com.vn', name: 'hienptt22'],
                                                [$class: 'CleanBeforeCheckout']],
            submoduleCfg                     : [],
            userRemoteConfigs                : [[credentialsId: "63265de3-8396-40f9-803e-5cd0b694e519",
                                                url          : "http://10.60.156.11/telecare/telecare-deployment" +".git"]]
    ]
    sleep(10)
    def folderDeploy= sh(script: 'pwd', returnStdout: true)
    env.buildFolderDeployResult = folderDeploy.trim()
    echo "env.buildFolderDeployResult: $env.buildFolderDeployResult"
    try {
        sh """
            pwd
            ls -la
            cd ${enviroment}/telecare
            sed -i -e "s,__VERSION__,${env.project_version},g" ${service}-deployment.yml
            kubectl -n telecare apply -f ${service}-deployment.yml --kubeconfig=telecare-k8s-config
            kubectl -n telecare apply -f telecare-configMap.yml --kubeconfig=telecare-k8s-config
            
            sleep 90
        """
        // sudo kubectl -n telecare apply -f ${service}-service.yml --kubeconfig=telecare-k8s-config
        //     sudo kubectl -n telecare apply -f ${service}-ingress.yml --kubeconfig=telecare-k8s-config
        dir("${env.buildFolderDeployResult}/${enviroment}/telecare"){
            echo "Get Pods, service detail"
            sh """
            kubectl -n telecare get pods,svc --kubeconfig=${configFile}
            """
            def checkProcessRunning = sh(returnStdout: true, script: "kubectl -n telecare --kubeconfig='${configFile}' get pods --sort-by=.status.startTime | grep '${service}-backend' | tail -n 1 | awk '{print \$3}'").trim()
            echo "checkProcessRunning: $checkProcessRunning ${service}"
            if(checkProcessRunning == "Running") {
                env.STAGING_PORT = sh(returnStdout: true, script: "kubectl -n telecare --kubeconfig='${configFile}' get svc | grep '${service}' | awk '{print \$5}' | grep -o '[[:digit:]]*' | tail -n 1").trim()
                echo "port: $env.STAGING_PORT"
                env.STAGING_IP = sh(returnStdout: true, script: "kubectl -n telecare --kubeconfig='${configFile}' get node -o wide | head -2 | tail -1 | awk '{print \$6'}").trim()
                echo "ip: $env.STAGING_IP"
            } else {
                error "Deploy service ${service} version ${env.project_version} to k8s ${enviroment} failure open port $env.STAGING_PORT"
            }
        }   
    }catch(err){
        error "Deploy to k8s failure"
    }
}
// config scan url with acunetix
def acunetixScan(url){
    sleep(30)
    def target_id = null
    withCredentials([string(credentialsId: 'acunetix-api-token', variable: 'accunetix')]) {
        // get info scan list in acunetix
        def scanListsResults = httpRequest([
            acceptType   : 'APPLICATION_JSON',
            httpMode     : 'GET',
            contentType  : 'APPLICATION_JSON',
            customHeaders: [[name: "X-Auth", value: accunetix]],
            url          : "${env.ACUNETIX_API_URL}/scans",
            ignoreSslErrors: true
        ])
        // get target ID with address link project
        for (scanListsResult in jenkinsfile_utils.jsonParse(scanListsResults.content)['scans']) {
            if(scanListsResult['target']['address'] == "http://${url}"){
                println "Target added get target ID to delete target"
                def target_id_remove=scanListsResult['target_id']
                // delete target with targetID in accunetix
                def removeTarget = httpRequest([
                    acceptType   : 'APPLICATION_JSON',
                    httpMode     : 'DELETE',
                    contentType  : 'APPLICATION_JSON',
                    customHeaders: [[name: "X-Auth", value: accunetix]],
                    url          : "${env.ACUNETIX_API_URL}/targets/${target_id_remove}",
                    ignoreSslErrors: true
                ])

            }
        }
        // content target json
        def targetContentJson = """
            {
                "address": "http://${url}",
                "description": "http://${url}",
                "criticality": "10"
            }
        """
        // add target to acunetix
        def addTarget= httpRequest([
            acceptType   : 'APPLICATION_JSON',
            httpMode     : 'POST',
            contentType  : 'APPLICATION_JSON',
            customHeaders: [[name: "X-Auth", value: accunetix]],
            url          : "${env.ACUNETIX_API_URL}/targets",
            requestBody  : targetContentJson,
            ignoreSslErrors: true
        ])
        // get target_id after add
        target_id= jenkinsfile_utils.jsonParse(addTarget.content)['target_id']
        println ("Result Add Target : " + jenkinsfile_utils.jsonParse(addTarget.content)['target_id'])

        // data scan
        def scanContentJson= """
            {
                "profile_id":"$env.modeScan",
                "incremental":false,
                "schedule":{
                    "disable":false,
                    "start_date":null,
                    "time_sensitive":false
                },
                "target_id":"$target_id"
            }
        """
        // "report_template_id":"11111111-1111-1111-1111-111111111111",
        // scan target
        def scan = httpRequest([
            acceptType   : 'APPLICATION_JSON',
            httpMode     : 'POST',
            contentType  : 'APPLICATION_JSON',
            customHeaders: [[name: "X-Auth", value: accunetix]],
            url          : "${env.ACUNETIX_API_URL}/scans",
            requestBody  : scanContentJson,
            timeout: 5,
            ignoreSslErrors: true
        ])
        print("Status: " + jenkinsfile_utils.jsonParse(scan.content))
        def scanAcunetixRetry = 0
        def scanAcunetixCompleted = false
        def scan_id
        //variable to generate report
        def last_scan_session_id
        def getResults
        while (!scanAcunetixCompleted) {
            try {
                timeout(time: 1, unit: 'MINUTES') {
                    script {
                        // request search target to get status
                        def searchResultByTarget = httpRequest([
                            acceptType   : 'APPLICATION_JSON',
                            httpMode     : 'GET',
                            contentType  : 'APPLICATION_JSON',
                            customHeaders: [[name: "X-Auth", value: accunetix]],
                            url          : "${env.ACUNETIX_API_URL}/targets?l=20&q=text_search:*${url}",
                            ignoreSslErrors: true
                        ])
                        def targets = jenkinsfile_utils.jsonParse(searchResultByTarget.content)['targets']
                            for(target in targets){
                                println ("target: " + target)
                                def results = target['last_scan_session_status']
                                    println("Result: "+results)
                                    if( results== "completed"){
                                        scanAcunetixCompleted = true
                                        scan_id = target['last_scan_id']
                                        println ("scan_id: " + scan_id)
                                        last_scan_session_id = target['last_scan_session_id']
                                        println ("last_scan_session_id: "+ last_scan_session_id)
                                        // get result scan target
                                        getResults = httpRequest([
                                            acceptType   : 'APPLICATION_JSON',
                                            httpMode     : 'GET',
                                            contentType  : 'APPLICATION_JSON',
                                            customHeaders: [[name: "X-Auth", value: accunetix]],
                                            url          : "${env.ACUNETIX_API_URL}/scans/$scan_id",
                                            ignoreSslErrors: true
                                        ])
                                        println ("Result: " + jenkinsfile_utils.jsonParse(getResults.content))
                                    }
                            }
                    }
                }
            } catch (FlowInterruptedException interruptEx) {
                // check if exception is system timeout
                if (interruptEx.getCauses()[0] instanceof org.jenkinsci.plugins.workflow.steps.TimeoutStepExecution.ExceededTimeout) {
                    if (scanAcunetixRetry <= 10) {
                        scanAcunetixRetry += 1
                    } else {
                        error "Cannot get result from acunetix server. Build Failed."
                        }
                } else {
                    throw interruptEx
                }
            }
            catch (err) {
                throw err
            }
        }
        def severity_counts_high = jenkinsfile_utils.jsonParse(getResults.content)['current_session']['severity_counts']['high']
        println ("severity_counts_high: " + severity_counts_high)
        def severity_counts_info = jenkinsfile_utils.jsonParse(getResults.content)['current_session']['severity_counts']['info']
        println ("severity_counts_info: " + severity_counts_info)
        def severity_counts_low = jenkinsfile_utils.jsonParse(getResults.content)['current_session']['severity_counts']['low']
        println ("severity_counts_low: " + severity_counts_low)
        def severity_counts_medium = jenkinsfile_utils.jsonParse(getResults.content)['current_session']['severity_counts']['medium']
        println ("severity_counts_medium: " + severity_counts_medium)
        
        env.SECURITY_ALERT_HIGH = severity_counts_high
        env.SECURITY_ALERT_INFO = severity_counts_info
        env.SECURITY_ALERT_LOW = severity_counts_low
        env.SECURITY_ALERT_MEDIUM= severity_counts_medium
        
        // config data for generate report
        def reportContentJson = """
            {
                "template_id":"11111111-1111-1111-1111-111111111111",
                "source":
                    {
                        "list_type":"scan_result",
                        "id_list":["$last_scan_session_id"]
                    }
            }
        """
        println ("reportContentJson : " +reportContentJson)
        
        def folder = sh(returnStdout: true, script :'pwd').trim()
        def reportId=""
        dir("$folder"){
            def genReports = sh(returnStdout: true, script : """
            curl -i -d '$reportContentJson' '${env.ACUNETIX_API_URL}/reports' \
            -H 'Content-Type: application/json;charset=utf8' -H 'X-Auth: $accunetix' \
            --insecure -o responeHeader.txt
            """).trim().tokenize("\n")
            reportId = sh(returnStdout: true, script: 'cat responeHeader.txt | grep \'Location:\' | sed \'s/.*://\' | sed \'s/.*\\///\'')
            println("ReportID: " + reportId)
        }
        def genReportCompleted = false
        def genReportRetry = 0

        while (!genReportCompleted) {
            try {
                sleep 10
                timeout(time: 1, unit: 'MINUTES') {
                    script {
                        def getLinkDownload = httpRequest([
                            acceptType   : 'APPLICATION_JSON',
                            httpMode     : 'GET',
                            contentType  : 'APPLICATION_JSON',
                            customHeaders: [[name: "X-Auth", value: accunetix]],
                            url          : "${env.ACUNETIX_API_URL}/reports/$reportId",
                            ignoreSslErrors: true
                        ])
                        def resultGenReport = jenkinsfile_utils.jsonParse(getLinkDownload.content)
                        if(resultGenReport['status'] == "completed"){
                            genReportCompleted = true
                            def downloadLink = resultGenReport['download'][0]
                            println downloadLink
                            def getFileDownload = httpRequest([
                                acceptType   : 'APPLICATION_JSON',
                                httpMode     : 'GET',
                                contentType  : 'APPLICATION_JSON',
                                customHeaders: [[name: "X-Auth", value: accunetix]],
                                url          : "${env.ACUNETIX_URL}/$downloadLink",
                                ignoreSslErrors: true
                            ])
                            writeFile file: 'fileScanResult.html', text: getFileDownload.content
                            stash name: "fileScanResult.html", includes: "fileScanResult.html"
                            publishHTML([
                                allowMissing         : false,
                                alwaysLinkToLastBuild: false,
                                keepAll              : true,
                                reportDir            : './',
                                reportFiles          : 'fileScanResult.html',
                                reportName           : 'Security-Report',
                                reportTitles         : 'Security-Report'
                            ])
                            sh """
                                ls -la
                            """
                            def removeReport = httpRequest([
                                acceptType   : 'APPLICATION_JSON',
                                httpMode     : 'DELETE',
                                contentType  : 'APPLICATION_JSON',
                                customHeaders: [[name: "X-Auth", value: accunetix]],
                                url          : "${env.ACUNETIX_API_URL}/reports/$reportId",
                                ignoreSslErrors: true
                            ])
                        }
                        
                    }
                }
            } catch (FlowInterruptedException interruptEx) {
                // check if exception is system timeout
                if (interruptEx.getCauses()[0] instanceof org.jenkinsci.plugins.workflow.steps.TimeoutStepExecution.ExceededTimeout) {
                    if (genReportRetry <= 10) {
                        genReportRetry += 1
                    } else {
                        error "Cannot get result from acunetix server. Build Failed."
                    }
                } else {
                    throw interruptEx
                }
            } finally {
                def testSecurityResultContent = "- Alert level high: <b>${severity_counts_high}</b> <br/>" +
                                    "- Alert level info: <b>${severity_counts_info}</b> <br/>" +
                                    "- Alert level low: <b>${severity_counts_low}</b> <br/>" +
                                    "- Alert level medium: <b>${severity_counts_medium}</b> <br/>"

                
                def testSecurityResultString = 	"<b> Security Scan Acunetix Result:</b> <br/><br/>${testSecurityResultContent} " +
                                    "<i><a href='${env.BUILD_URL}Security-Report/'>Details Scan Acunetix Report...</a></i><br/><br/>"
                env.SECURITY_RESULT_STR = testSecurityResultString
                println env.SECURITY_RESULT_STR
                if(severity_counts_info > 0 || severity_counts_low > 0 || severity_counts_medium > 0){
                    if(enableBypassSec == 'true'){
                        echo "Security scan alert found high, low or medium"
                    } else {
                        error "Security scan alert found high, low or medium"
                    }
                }
            }
        }
        
    }
}
// config run automations test serenity
def autoTest(){
    if(env.jobAutoTest == ""){
        echo "skip automations test"
    } else {
        sleep(30)
        build job: "${env.jobAutoTest}"
    }
}
def autoPerfomance(){
    if(env.jobAutoPerform == ""){
        echo "skip automations test"
    } else {
        sleep(30)
        build job: "${env.jobAutoPerform}"
    }
}
/*
    - Config các stage run when push commit
    - SonarQube
    - Build
    - Deploy
*/
def buildPushCommit() {
    echo "gitlabBranch: $env.gitlabBranch"
    def backendPom = readMavenPom([file: "pom.xml"])
    def backendVersion = backendPom.getVersion()
    def version = "${backendVersion}_${env.gitlabBranch}_u${BUILD_NUMBER}"
    env.project_version=version
    echo " Version project : $version"
    def tasks = [:]
    tasks['unitTestAndCodeCoverage'] = {
        node("$env.node_slave") {
            echo "Unit Test"
            unitTestAndCodeCoverage("PUSH")
        }
    }
    tasks['SonarQubeScan'] = {
        node("$env.node_slave") {
            sonarQubeScan("PUSH")
        }
    }
    tasks['Package and Build Artifact'] = {
        node("$env.node_slave") {
            buildService("PUSH")
        }
    }
    parallel tasks
    stage("Push Image To Habor"){
        node("$env.node_slave"){
            pushImageDocker()
        }
    }
     def deploys=[:]
    if(env.gitlabBranch == env.STAGING_BRANCH){
        deploys['Execute update DB Staging'] = {
            if(env.enableDB == 'true'){
                build job: "$env.jobDBVersioning", parameters: [
                    string(name: 'DB_TYPE', value: 'mariadb'), 
                    string(name: 'ENVIRONMENT_RUN', value: "${env.ENVIRONMENT_RUN}"), 
                    string(name: 'GITLABURL', value: "$env.GITLABURL"), 
                    string(name: 'SCHEMA', value: "$env.SCHEMA"), 
                    string(name: 'defaultFile', value: "$env.defaultFile"),
                    string(name: 'VERSION', value: "${env.project_version}")
                ]
            } else{
                echo "Skip"
            }
        }
        deploys['Deploy to K8s'] = {
            node("$env.node_slave"){
               stage("Deploy to K8s"){
                    release2k8s("k8s-test-performance","patient","telecare-k8s-config")
               }
            }
        }
        parallel deploys
        def tests = [:]
        tests["Run Automations Test"] = {
            stage("Run Automations Test"){
                autoTest()
            }
        }
        tests["Run Security Test"] = {
            stage("Run Security Test"){
                acunetixScan("${env.STAGING_IP}:${env.STAGING_PORT}")
            }
        }
        parallel tests
        stage("Run Auto Performance Test"){
            autoPerfomance()
        }

    }else {
        stage("Deploy to K8s"){
            node("$env.node_slave"){
                release2k8s("k8s","patient","telecare-k8s-config")
            }   
        }
    }
    currentBuild.result = "SUCCESS"

}
/*
  Sửa các stage cho phù hợp với dự án
*/
def buildMergeRequest() {
    echo "gitlabBranch: $env.gitlabBranch"
    def backendPom = readMavenPom([file: "pom.xml"])
    def backendVersion = backendPom.getVersion()
    def version = "${backendVersion}_${env.gitlabTargetBranch}_u${BUILD_NUMBER}"
    env.project_version=version
    echo " Version project : $version"
    def tasks = [:]
    tasks['unitTestAndCodeCoverage'] = {
        node("$env.node_slave") {
            echo "Unit Test"
            unitTestAndCodeCoverage("MERGE")
        }
    }
    tasks['SonarQube Scan'] = {
        node("$env.node_slave") {
           echo "test sonar1"
          sonarQubeScan("MERGE")
        }
    }
    tasks['Package and Build Artifact'] = {
        node("$env.node_slave") {
            buildService("MERGE")
        }
    }
    parallel tasks

    stage("Push Image To Habor"){
        node("$env.node_slave"){
            pushImageDocker()
        }
    }
    def deploys = [:]
    if(env.gitlabTargetBranch == env.STAGING_BRANCH){
        /*
           -- Deploy lên k8s or server staging
        */
        deploys['Execute update DB Staging'] = {
            if(env.enableDB == 'true'){
                build job: "$env.jobDBVersioning", parameters: [
                    string(name: 'DB_TYPE', value: 'mariadb'), 
                    string(name: 'ENVIRONMENT_RUN', value: "${env.ENVIRONMENT_RUN}"), 
                    string(name: 'GITLABURL', value: "$env.GITLABURL"), 
                    string(name: 'SCHEMA', value: "$env.SCHEMA"), 
                    string(name: 'defaultFile', value: "$env.defaultFile"),
                    string(name: 'VERSION', value: "${env.project_version}")
                ]
            } else{
                echo "Skip"
            }
            
        }
        deploys['Deploy to K8s'] = {
            node("$env.node_slave"){
               stage("Deploy to K8s"){
                    release2k8s("k8s-test-performance","patient","telecare-k8s-config")
               }
            }
        }
        parallel deploys
        def tests = [:]
        tests["Run Automations Test"] = {
            stage("Run Automations Test"){
                autoTest()
            }
        }
        tests["Run Security Test"] = {
            stage("Run Security Test"){
                acunetixScan("${env.STAGING_IP}:${env.STAGING_PORT}")
            }
        }
        parallel tests
        stage("Run Auto Performance Test"){
            autoPerfomance()
        }
    }else{
        /*
           -- Deploy lên k8s or server none staging
        */
        stage("Deploy to K8s"){
            node("$env.node_slave"){
                release2k8s("k8s","patient","telecare-k8s-config")
            }   
        }
    }
    
    currentBuild.result = "SUCCESS"
}


return [
    buildPushCommit      : this.&buildPushCommit,
    buildMergeRequest    : this.&buildMergeRequest,
    buildAcceptAndCloseMR: this.&buildAcceptAndCloseMR,
    sonarQubeScan        : this.&sonarQubeScan,
    buildService        : this.&buildService,
    release2k8s          : this.&release2k8s

]
