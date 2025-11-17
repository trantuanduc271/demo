# Detailed Step-by-Step Migration Guide

## 📋 Analysis of Groovy Files

### File Structure Overview

1. **`jenkinsfile_utils.groovy`** - Utility functions
   - `checkoutSourceCode(checkoutType)` - Handles checkout (PUSH/MERGE)
   - `parseXml()`, `jsonParse()`, `toJSONString()` - Parsers
   - `getProjectMember()` - GitLab API integration
   - Returns map of utility functions

2. **`jenkinsfile_CI.groovy`** - CI pipeline functions
   - `sonarQubeScan(buildType)` - SonarQube analysis (includes checkout)
   - `unitTestAndCodeCoverage(buildType)` - Tests + coverage (includes checkout)
   - `buildService(buildType)` - Build artifact (includes checkout)
   - `pushImageDocker()` - Push to Harbor registry
   - `release2k8s()` - Deploy to Kubernetes
   - `buildPushCommit()` - Main push commit orchestrator
   - `buildMergeRequest()` - Main merge request orchestrator
   - Returns map of CI functions

3. **`jenkinsfile_CD.groovy`** - CD pipeline functions
   - `deployToProduction()` - Production deployment with approval
   - `deployToPreRelease()` - Pre-release deployment
   - Returns map of CD functions

4. **`jenkinsfile_bootstrap.groovy`** - Main entry point
   - `checkBuildType()` - Determines build type from GitLab events
   - `bootstrap_build()` - Routes to appropriate function
   - Handles: push_commit_build, merge_request_build, deploy_production

---

## ⚠️ Key Differences: GitLab vs GitHub

### GitLab Environment Variables (Used in Groovy Files)
```groovy
env.gitlabActionType        // PUSH, MERGE, NOTE, TAG_PUSH
env.gitlabAfter             // Branch SHA for push
env.gitlabSourceBranch      // Source branch name
env.gitlabTargetBranch      // Target branch name
env.gitlabSourceRepoHomepage // Repository URL
env.gitlabMergeRequestIid   // Merge request ID
env.gitlabMergeRequestState // opened, closed, merged
env.gitlabBranch            // Current branch
env.gitlabMergeRequestLastCommit // Last commit SHA
```

### GitHub Environment Variables (What We Need)
```groovy
env.CHANGE_ID               // PR number (empty for push)
env.CHANGE_TARGET           // Target branch (for PR)
env.CHANGE_FORK             // Is fork PR?
env.BRANCH_NAME             // Current branch (origin/name for PR)
env.GIT_BRANCH              // Full branch name
env.GIT_COMMIT              // Current commit SHA
env.GIT_URL                 // Repository URL
```

### Required Adaptations

1. **Checkout Function** - Must adapt `checkoutSourceCode()` for GitHub
2. **Build Type Detection** - Must adapt `checkBuildType()` for GitHub
3. **Event Routing** - Map GitHub webhook events to build types
4. **Credentials** - Change from GitLab credentials to GitHub credentials
5. **API Calls** - Replace GitLab API calls with GitHub API calls

---

## 🚀 Migration Steps (VERY SLOW & CAREFUL)

### Step 0: Preparation (No Code Changes)
**Goal**: Understand what we're working with

1. ✅ Review all groovy files (done)
2. ✅ Understand current Jenkinsfile structure (done)
3. ⏳ Document current pipeline stages
4. ⏳ List all environment variables used

**Action**: Create a mapping document:
- Current stage → Groovy function replacement
- Current env vars → GitHub equivalent
- Current credentials → GitHub credentials needed

---

### Step 1: Test Groovy File Loading (SAFEST FIRST STEP)
**Goal**: Verify groovy files can be loaded without breaking pipeline

**Changes to `jenkins/Jenkinsfile`**:

1. Uncomment groovy file loading at top:
```groovy
// Load groovy library files
jenkinsfile_CI = load 'setup/cicd/jenkinsfile_CI.groovy'
jenkinsfile_utils = load 'setup/cicd/jenkinsfile_utils.groovy'
jenkinsfile_CD = load 'setup/cicd/jenkinsfile_CD.groovy'
```

2. Add a simple test stage (optional):
```groovy
stage('Test Groovy Loading') {
    steps {
        script {
            echo "Groovy files loaded successfully!"
            echo "Available functions: ${jenkinsfile_CI.keySet()}"
            // Don't call any functions yet - just verify they load
        }
    }
}
```

3. **Test**: Run pipeline - should still work exactly as before (groovy files loaded but not used)

**Rollback Plan**: If this fails, comment out the loading lines

---

### Step 2: Create GitHub-Compatible Checkout Function (NEW FILE)
**Goal**: Create a GitHub version of checkout without breaking current pipeline

**Create**: `setup/cicd/jenkinsfile_utils_github.groovy` (new file)

```groovy
// GitHub-compatible checkout function
def checkoutSourceCodeGitHub(checkoutType) {
    if (checkoutType == "PUSH") {
        // Regular push - use default checkout
        checkout scm
    } else if (checkoutType == "MERGE") {
        // Pull request - checkout PR branch
        checkout scm
        // GitHub automatically checks out PR branch when CHANGE_ID is set
    }
}

return [
    checkoutSourceCodeGitHub: this.&checkoutSourceCodeGitHub
]
```

**Test**: Load this file in Jenkinsfile, but don't use it yet

---

### Step 3: Create GitHub Build Type Detection (NEW FILE)
**Goal**: Create GitHub version of checkBuildType()

**Create**: `setup/cicd/jenkinsfile_bootstrap_github.groovy` (new file)

```groovy
// GitHub-compatible build type detection
def checkBuildTypeGitHub() {
    def buildType = "none"
    
    // If CHANGE_ID exists, it's a Pull Request
    if (env.CHANGE_ID) {
        buildType = "merge_request_build"
    }
    // Check if it's a tag push (GitHub sets GIT_BRANCH to tags/name)
    else if (env.GIT_BRANCH && env.GIT_BRANCH.startsWith("tags/")) {
        buildType = "deploy_production"
    }
    // Otherwise it's a regular push
    else {
        buildType = "push_commit_build"
    }
    
    return buildType
}

return [
    checkBuildTypeGitHub: this.&checkBuildTypeGitHub
]
```

**Test**: Load this file, test the function with echo statements

---

### Step 4: Replace Checkout Stage (FIRST FUNCTIONAL REPLACEMENT)
**Goal**: Replace checkout stage with groovy function (but keep current checkout as fallback)

**Changes to `jenkins/Jenkinsfile`**:

```groovy
stage('Checkout') {
    steps {
        script {
            // Try GitHub checkout function if available
            if (jenkinsfile_utils_github) {
                echo '📥 Using GitHub checkout function...'
                jenkinsfile_utils_github.checkoutSourceCodeGitHub("PUSH")
            } else {
                // Fallback to standard checkout
                echo '📥 Using standard checkout...'
                checkout scm
            }
        }
    }
}
```

**Test**: Verify checkout still works
**Rollback**: Revert to `checkout scm` if issues

---

### Step 5: Replace Test Stage with Groovy Function (CAREFUL!)
**Goal**: Use `unitTestAndCodeCoverage()` function

**IMPORTANT NOTES**:
- This function includes its own checkout stage
- It uses GitLab env vars (will need adaptation)
- It runs: `mvn clean test org.jacoco:jacoco-maven-plugin:0.8.5:report-aggregate`
- It publishes JaCoCo reports

**Changes to `jenkins/Jenkinsfile`**:

1. **Remove** `stage('Checkout')` (function handles it)
2. **Comment out** current `stage('Test')`
3. **Uncomment** and modify groovy stage:

```groovy
stage('Unit Test & Code Coverage') {
    steps {
        script {
            // Use groovy function - but adapt for GitHub
            // NOTE: This function expects GitLab env vars, may fail initially
            try {
                jenkinsfile_CI.unitTestAndCodeCoverage("PUSH")
            } catch (Exception e) {
                echo "Groovy function failed: ${e.message}"
                echo "Falling back to standard test..."
                container('maven') {
                    sh 'mvn test'
                }
                throw e  // Re-throw to see the error
            }
        }
    }
    post {
        always {
            junit 'target/surefire-reports/TEST-*.xml'
        }
    }
}
```

**Expected Issues**:
- GitLab env vars missing → function will fail
- Need to set GitHub equivalents or modify function

**Test**: 
- First test with try/catch to see errors
- Gradually fix env var issues
- Once working, remove fallback

---

### Step 6: Adapt Groovy Functions for GitHub (MODIFY EXISTING FILES)
**Goal**: Make groovy functions work with GitHub

**Option A: Create wrapper functions (SAFER)**
- Create new GitHub-specific functions that wrap existing ones
- Gradually replace GitLab-specific code

**Option B: Modify existing functions (RISKIER)**
- Update `jenkinsfile_utils.groovy` to detect GitHub vs GitLab
- Make checkout function work with both

**Recommended Approach**: Option A (wrapper functions)

Create `setup/cicd/jenkinsfile_CI_github.groovy`:

```groovy
// Load original CI functions
jenkinsfile_CI = load 'setup/cicd/jenkinsfile_CI.groovy'
jenkinsfile_utils = load 'setup/cicd/jenkinsfile_utils.groovy'
jenkinsfile_utils_github = load 'setup/cicd/jenkinsfile_utils_github.groovy'

// GitHub wrapper for unitTestAndCodeCoverage
def unitTestAndCodeCoverageGitHub(buildType) {
    // Set GitHub env vars as GitLab equivalents (for compatibility)
    env.gitlabActionType = buildType == "PUSH" ? "PUSH" : "MERGE"
    
    // Use GitHub checkout
    stage("Checkout source code") {
        jenkinsfile_utils_github.checkoutSourceCodeGitHub(buildType)
    }
    
    // Call original function for test/coverage logic
    stage("Unit Test & Code Coverage") {
        try {
            sh """
            mvn clean test org.jacoco:jacoco-maven-plugin:0.8.5:report-aggregate
            """
            echo "code coverage done"
            // ... rest of original function logic
        } catch (err) {
            echo "Error when test Unit Test"
            throw err
        } finally {
            // ... test result processing
        }
    }
}

return [
    unitTestAndCodeCoverageGitHub: this.&unitTestAndCodeCoverageGitHub
]
```

---

### Step 7: Replace Build Stage
**Goal**: Use `buildService()` function

**IMPORTANT**: 
- This function runs `sh ./cicd/build.sh` - you may not have this script
- It expects specific project structure
- You may need to adapt or skip this

**Decision Point**:
- **Skip** if you don't have `cicd/build.sh`
- **Adapt** to use your Maven build instead
- **Create** the script if needed

---

### Step 8: Replace Docker Push Stage
**Goal**: Use `pushImageDocker()` function

**IMPORTANT**:
- Function pushes to Harbor registry (`10.60.156.72`)
- You're using GCP Artifact Registry
- Function uses Docker, you're using Kaniko

**Options**:
1. **Skip** - Keep your Kaniko stage
2. **Adapt** - Create GitHub/GCP version of push function
3. **Replace** - Use function but change registry settings

**Recommended**: Keep Kaniko for now, create wrapper later if needed

---

### Step 9: Replace Deploy Stage
**Goal**: Use `release2k8s()` function

**IMPORTANT**:
- Function checks out separate deployment repo (`telecare-deployment`)
- Function uses specific K8s config files
- Function deploys to specific namespace (`telecare`)

**Your Current**:
- Uses `k8s-deployment.yaml` in same repo
- Deploys to `default` namespace

**Options**:
1. **Adapt** - Modify function to use your YAML structure
2. **Create** - New function that matches your deployment pattern
3. **Skip** - Keep current deployment for now

---

### Step 10: Add SonarQube Scan (OPTIONAL)
**Goal**: Add `sonarQubeScan()` function

**Requirements**:
- SonarQube server configured in Jenkins
- SonarQube plugin installed
- SonarQube scanner available at `/home/app/server/sonar-scanner/bin/sonar-scanner`

**If you don't have SonarQube**:
- Skip this step
- Uncomment when ready to add SonarQube

---

### Step 11: Add Security Scan (OPTIONAL)
**Goal**: Add `acunetixScan()` function

**Requirements**:
- Acunetix server configured
- `env.ACUNETIX_API_URL` set
- Acunetix credentials configured

**If you don't have Acunetix**:
- Skip this step

---

### Step 12: Full Event-Based Routing (FINAL STEP)
**Goal**: Replace entire pipeline with event-based routing

**Only do this after ALL above steps work!**

Replace entire `pipeline {}` block with:

```groovy
node {
    // Load groovy files
    jenkinsfile_bootstrap_github = load 'setup/cicd/jenkinsfile_bootstrap_github.groovy'
    jenkinsfile_CI_github = load 'setup/cicd/jenkinsfile_CI_github.groovy'
    // ... other loads
    
    // Determine build type
    def buildType = jenkinsfile_bootstrap_github.checkBuildTypeGitHub()
    echo "Build type: ${buildType}"
    
    // Route to appropriate pipeline
    switch(buildType) {
        case "push_commit_build":
            // Call adapted buildPushCommit function
            break
        case "merge_request_build":
            // Call adapted buildMergeRequest function
            break
        case "deploy_production":
            // Call deployToProduction function
            break
        default:
            // Fallback to standard pipeline
            break
    }
}
```

---

## 📝 Migration Checklist

- [ ] **Step 0**: Preparation and documentation
- [ ] **Step 1**: Test groovy file loading (NO FUNCTIONAL CHANGES)
- [ ] **Step 2**: Create GitHub checkout function (NEW FILE)
- [ ] **Step 3**: Create GitHub build type detection (NEW FILE)
- [ ] **Step 4**: Replace checkout stage (WITH FALLBACK)
- [ ] **Step 5**: Replace test stage (WITH ERROR HANDLING)
- [ ] **Step 6**: Adapt functions for GitHub (CREATE WRAPPERS)
- [ ] **Step 7**: Replace build stage (OR SKIP IF NOT APPLICABLE)
- [ ] **Step 8**: Replace Docker push (OR KEEP KANIKO)
- [ ] **Step 9**: Replace deploy stage (OR ADAPT)
- [ ] **Step 10**: Add SonarQube (OPTIONAL)
- [ ] **Step 11**: Add security scan (OPTIONAL)
- [ ] **Step 12**: Full event-based routing (FINAL)

---

## 🛡️ Safety Rules

1. **ONE STEP AT A TIME** - Complete and test each step before moving on
2. **ALWAYS HAVE ROLLBACK** - Keep commented old code until new code works
3. **TEST THOROUGHLY** - Run pipeline multiple times after each change
4. **MONITOR ERRORS** - Check Jenkins console output carefully
5. **KEEP FALLBACKS** - Use try/catch to fall back to old code if needed
6. **DON'T RUSH** - Take breaks between steps, especially after Step 5

---

## 🎯 Recommended Starting Point

**Start with Step 1** - Just load the groovy files without using them. This is the safest possible first step.

If Step 1 works, proceed to Step 2 (create GitHub-compatible functions in NEW files).

**DO NOT** modify existing groovy files until you fully understand them!

