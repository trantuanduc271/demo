# 🔧 Fixing the "mvn: not found" Error

## The Problem

Your build failed with:
```
mvn: not found
ERROR: script returned exit code 127
```

**Why?** Your Jenkinsfile is using the default Jenkins agent, which doesn't have Maven installed.

---

## ✅ Solution: Use the Correct Jenkinsfile

### Step 1: Update Your Jenkinsfile

Replace your current `jenkins/Jenkinsfile` in your repository with this:

```groovy
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
                    sh 'mvn -B -DskipTests clean package'
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
            post {
                always {
                    junit 'target/surefire-reports/*.xml'
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
```

### Step 2: Key Differences

**❌ Wrong (what you have now):**
```groovy
pipeline {
    agent any  // Uses default agent without Maven
    stages {
        stage('Build') {
            steps {
                sh 'mvn ...'  // Maven doesn't exist!
            }
        }
    }
}
```

**✅ Correct (what you need):**
```groovy
pipeline {
    agent {
        kubernetes {
            yaml '''...maven container...'''  // Creates pod with Maven!
        }
    }
    stages {
        stage('Build') {
            steps {
                container('maven') {  // Run inside Maven container
                    sh 'mvn ...'  // Maven exists here!
                }
            }
        }
    }
}
```

### Step 3: Push the Updated Jenkinsfile

```bash
cd D:\demo\simple-java-maven-app

# Edit jenkins/Jenkinsfile with the correct content above

# Commit and push
git add jenkins/Jenkinsfile
git commit -m "Fix: Use Kubernetes agent with Maven"
git push
```

### Step 4: Run Build Again

1. Go to Jenkins: https://jenkins.ducttdevops.com
2. Click your job: **my-java-app-demo**
3. Click **"Build Now"**
4. This time it will work! ✅

---

## 🔍 What Will Happen Now

### Before (Default Agent):
```
Agent: default-jtc9h
Container: jenkins/inbound-agent
Maven: ❌ Not installed
Result: ❌ FAILURE
```

### After (Kubernetes Maven Agent):
```
Agent: my-java-app-demo-1-xyz
Container: maven:3.8-jdk-11
Maven: ✅ Installed
Result: ✅ SUCCESS
```

---

## 👀 See the Difference

### During Your Next Build, Watch This:

```bash
# Watch pods being created
kubectl get pods -n jenkins -w
```

You'll see something like:
```
NAME                              READY   STATUS    RESTARTS   AGE
jenkins-0                         2/2     Running   0          3h
my-java-app-demo-1-abc123-xyz     0/2     Pending   0          1s    ← New!
my-java-app-demo-1-abc123-xyz     0/2     ContainerCreating   0     2s
my-java-app-demo-1-abc123-xyz     2/2     Running   0          45s   ← Maven ready!
```

In the console output, you'll see:
```
Agent my-java-app-demo-1-abc123-xyz is provisioned from template
...
containers:
  - name: maven
    image: maven:3.8-jdk-11  ← Maven container!
...
+ mvn --version
Apache Maven 3.8.6 ✅ Maven works!
```

---

## 🎯 Quick Fix Checklist

- [ ] Copy the correct Jenkinsfile (from above)
- [ ] Replace your current `jenkins/Jenkinsfile` in your repo
- [ ] Commit: `git commit -m "Fix: Use Maven agent"`
- [ ] Push: `git push`
- [ ] Go to Jenkins and click "Build Now"
- [ ] Watch it succeed! ✅

---

## Alternative: Use Declarative Agent (Simpler)

If you want a simpler approach, you can also use:

```groovy
pipeline {
    agent {
        docker {
            image 'maven:3.8-jdk-11'
        }
    }
    stages {
        stage('Build') {
            steps {
                sh 'mvn -B -DskipTests clean package'
            }
        }
    }
}
```

But the Kubernetes approach is better for your setup!

---

## 🎤 For Your Demo

When explaining why you use Kubernetes agents:

> "Traditional Jenkins agents need pre-installed tools like Maven, Node, Docker.
> With Kubernetes, we dynamically create agents with exactly the tools we need.
> Each build gets a fresh, isolated environment with the correct dependencies."

**Show this:**
```bash
# Show default agent has no Maven
kubectl exec -n jenkins jenkins-0 -c jenkins -- which mvn
# Returns: nothing (Maven not found)

# Show Kubernetes creates agents on-demand
kubectl get pods -n jenkins -w
# During build, you'll see new pods with Maven
```

---

## Understanding Agent Types

### 1. Default Agent (What you got)
```yaml
image: jenkins/inbound-agent
Tools: ❌ Basic shell only
Use case: Running Jenkins jobs that don't need special tools
```

### 2. Kubernetes Maven Agent (What you need)
```yaml
image: maven:3.8-jdk-11
Tools: ✅ Maven, JDK 11, Git
Use case: Building Java applications
```

### 3. Custom Agent Examples

**For Node.js:**
```groovy
agent {
    kubernetes {
        yaml '''
        spec:
          containers:
          - name: node
            image: node:16
'''
    }
}
```

**For Python:**
```groovy
agent {
    kubernetes {
        yaml '''
        spec:
          containers:
          - name: python
            image: python:3.9
'''
    }
}
```

**For Docker builds:**
```groovy
agent {
    kubernetes {
        yaml '''
        spec:
          containers:
          - name: docker
            image: docker:latest
'''
    }
}
```

---

## Summary

**Problem:** Default agent doesn't have Maven  
**Solution:** Use Kubernetes agent with Maven container  
**Action:** Update your Jenkinsfile and push to Git  
**Result:** Build will succeed! ✅

---

**Now go fix that Jenkinsfile and run your build again! 🚀**

