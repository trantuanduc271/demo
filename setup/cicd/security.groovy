def security_list="admin,hienptt22"
env.security_list = security_list
def sendMailForUser(userRecevice,time,phone){
    try{
        def sendMailRetry = 0
        def sendMailComplete = false
        echo "Send SMS"
        def contentSMS = "Don vi cua dong chi vua nhan duoc yeu cau danh gia chat luong cho du an ETC_V2. Thong tin chi tiet ket qua tai $JOB_NAME. De nghi dong chi kiem tra ket qua chi tiet gui kem tu email vtsjenkinsadmin@viettel.com.vn. Dong chi co $time de xu ly yeu cau nay. Tran trong."
        sh """
           source ~/.bashrc
           sms "$phone" "$contentSMS"
        """
        while (!sendMailComplete) {
            try {
                sleep 10
                mail([
                    bcc: '', 
                    body: "Kính gửi bộ phận ATTT! <br/>" +
                        "Đơn vị của đồng chí nhận được một yêu cầu đánh giá ATTT cho dự án ETC </strong><br/>" +
                        "Đề nghị đồng chí vào kiểm tra kết quả theo link kết quả cho tiết trên hệ thống CI/CD. <br/>" +
                        "Đồng chí có <strong> $time </strong>để thực hiện yêu cầu đánh giá. <br/>" +
                        "Đề nghị PM dự án bổ sung tài liệu đánh giá theo đúng yêu cầu. <br/>" +
                        "Kính gửi đồng chí kết quả chi tiết đính kèm. <br/>" +
                        "<br/> </summary> <br/> <h4><i><a href='${env.BUILD_URL}display/redirect'>" + 
                        "Kết quả build chi tiết...</a></i></h4><br/>",
                    mimeType: 'text/html', 
                    cc: "${env.mailCC}", 
                    from: 'vtsjenkinsadmin@viettel.com.vn', 
                    replyTo: '', 
                    subject: "PYC - Đánh giá ATTT trước triển khai cho dự án ETC. Vui lòng kiểm tra và đánh giá  $JOB_NAME - Build # $BUILD_NUMBER!", 
                    to: "${userRecevice}"
                ])
                sendMailComplete = true
            }catch (err) {
                echo "Send mail fail due to $err"
            }
        }
    }catch(err){
        throw err
    }
}
def checkoutSource(){
    checkout changelog: true, poll: true, scm: [
                $class                           : 'GitSCM',
                branches                         : [[name: "master"]],
                doGenerateSubmoduleConfigurations: false,
                extensions                       : [[$class: 'UserIdentity', email: 'cicdBot@viettel.com.vn', name: 'cicdBot']],
                submoduleCfg                     : [],
                userRemoteConfigs                : [[credentialsId: 'a5eedd9f-332d-4575-9756-c358bbd808eb',
                                                     name         : 'origin',
                                                     url          : "http://10.60.156.11/hienptt22/demo_security" + ".git"]]
        ]
}
def convertFile(fileNameSide,fileNameLsr){
    stage("Checkout source code"){
        checkoutSource()
    }
    stage("Convert file"){
        sh """
           cd /home/acunetix/.acunetix/v_210503151/ui
           ../scanner/node lsr generate --sourcetype selenium --source $WORKSPACE/ATTT/$fileNameSide  --destination $WORKSPACE/ATTT/$fileNameLsr
           cd $WORKSPACE/ATTT
        """
        stash name: "$fileNameLsr", includes: "ATTT/$fileNameLsr"
    }
}
def acunetixScan(projectName,urlScan,fileNameLsr,fileUrl){
    stage("Checkout source code"){
        checkoutSource()
    }
    stage("Acunetix Scan"){
        dir("$WORKSPACE/ATTT"){
            unstash "$fileNameLsr"
            sh """
               ls -la ATTT
               mv ATTT/* .
               sudo python acu_api.py -p $projectName -u $urlScan -f $WORKSPACE/ATTT/$fileNameLsr -i $WORKSPACE/ATTT/${fileUrl}.txt
            """ 
        }
    }
}
def acunetixScanBackend(){
    stage("Checkout source code"){
        checkoutSource()
    }
    stage("Acunetix Scan"){
        dir("$WORKSPACE/ATTT"){
            sh """
               sudo python APItoken.py -u https://camera-api.demo.thinghub.vn/api/login -n demo2020 -p 123456aA@
               sudo python acu_api.py -p VMS -u https://camera-api.demo.thinghub.vn -i ${WORKSPACE}/ATTT/camera_api.xml
            """ 
        }
    }
}
def nessuScan(){
    stage("Checkout source code"){
        checkoutSource()
    }
    stage("NessuScan"){
        dir("$WORKSPACE/ATTT"){
            sh """
               sudo python ness_api.py -t vms_targets.xls -p VMS
            """ 
        }
    }
}
node("slave_43"){
    node("Acunetix"){
        convertFile("vms_cms_login_selenium.side","vms_cms_login_selenium.lsr")
        convertFile("vms_demo_login_selenium.side","vms_demo_login_selenium.lsr")
    }
    def tasks= [:]
    tasks["Run Scan Acunetix Demo"] = {
        node("slave_43"){
            acunetixScan("VMS","https://camera.demo.thinghub.vn","vms_demo_login_selenium.lsr","cam_demo_url")
        }
    }
    tasks["Run Scan Acunetix CMS"] = {
        node("slave_116"){
            acunetixScan("VMS","https://camera-cms.demo.thinghub.vn/site/login","vms_cms_login_selenium.lsr","cam_cms_url")
        }
    }
    tasks["Run Scan Acunetix VMS backend"] = {
        node("slave_116"){
            acunetixScanBackend()
        }
    }
    tasks["Run Scan security Acunetix"] = {
        node("slave_43"){
             nessuScan()
        }
    }
    tasks["Run Scan Fortyfi"] = {
        node("Fortify"){
            environment {
                FORTIFY_HOME = 'C:\\Program Files\\Fortify\\Fortify_SCA_and_Apps_20.1.1\\bin'
            }
            stage("Checkout source code"){
                checkoutSource()
            } 
            stage('Fortify') {
                bat 'dir'
                fortifyClean addJVMOptions: '', buildID: 'test', debug: true, logFile: '', maxHeap: '', verbose: true
                fortifyTranslate addJVMOptions: '', buildID: 'test', debug: true, logFile: '', maxHeap: '', projectScanType: fortifyOther(otherIncludesList: './**/*', otherOptions: ''), verbose: true
                fortifyScan addJVMOptions: '', addOptions: '', buildID: 'test', customRulepacks: '', debug: true, logFile: '', maxHeap: '', resultsFile: 'scan.fpr', verbose: true
                        
            }
        }
    }
    parallel tasks
//     stage("Send mail result"){
//         sendMailForUser("hienptt22@viettel.com.vn","24h","84347173624")
//     }
//     stage("Wait For Security confirm result"){
//         try {
//             deployer = env.security_list
//             echo "project_maintainer_list: ${env.project_maintainer_list}"
//             timeout(time: 24, unit: 'HOURS') {
//                         deployInput = input(
//                             submitter: "${deployer}",
//                             submitterParameter: 'submitter',
//                             message: 'Pause for wait maintainer selection', ok: "Execute", parameters: [
//                             choice(choices: ['Deploy', 'Abort'], 
//                             description: 'Deploy to production or abort deploy process?', name: 'DEPLOY_CHOICES')
//                         ])
//             }
//         } catch (err) { // timeout reached or input false
//             echo "Exception"
//             def user = err.getCauses()[0].getUser()
//             if ('SYSTEM' == user.toString()) { // SYSTEM means timeout.
//                 echo "Timeout is exceeded!"
//             } else {
//                 echo "Aborted by: [${user}]"
//             }
//             deployInput= "Abort"
//         }
//         echo "Input value: $deployInput"
// 		echo "Submitter: ${deployInput['submitter']}"
// 		echo "Input: ${deployInput['DEPLOY_CHOICES']}"
//     }
//     stage("Clean Enviroment"){
//         echo "clean"
//     }
}