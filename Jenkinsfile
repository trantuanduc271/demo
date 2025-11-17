pipeline {
    agent {
        kubernetes {
            yaml '''
apiVersion: v1
kind: Pod
metadata:
  labels:
    jenkins: agent
spec:
  containers:
  - name: maven
    image: maven:3.8-jdk-11
    command:
    - cat
    tty: true
    resources:
      requests:
        memory: "1Gi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "1000m"
'''
        }
    }
    
    stages {
        stage('Checkout') {
            steps {
                echo '📥 Checking out source code...'
                checkout scm
            }
        }
        
        stage('Build') {
            steps {
                container('maven') {
                    echo '🔨 Building application...'
                    sh 'mvn --version'
                    sh 'mvn clean compile'
                }
            }
        }
        
        stage('Test') {
            steps {
                container('maven') {
                    echo '🧪 Running tests...'
                    sh 'mvn test'
                }
            }
        }
        
        stage('Package') {
            steps {
                container('maven') {
                    echo '📦 Packaging application...'
                    sh 'mvn package -DskipTests'
                }
            }
        }
        
        stage('Archive') {
            steps {
                echo '💾 Archiving artifacts...'
                archiveArtifacts artifacts: 'target/*.jar', allowEmptyArchive: true
            }
        }
    }
    
    post {
        success {
            echo '✅ BUILD SUCCESSFUL!'
            echo '================================'
            echo 'All stages completed successfully'
            echo '================================'
        }
        failure {
            echo '❌ BUILD FAILED!'
        }
        always {
            echo '🧹 Pipeline finished'
        }
    }
}

