# Gradual Migration Guide: Declarative → Groovy Pipeline

## Current Status
✅ **Working**: Declarative pipeline (current Jenkinsfile)  
🔄 **Migrating to**: Groovy scripted pipeline with reusable functions

## 📚 Documentation

- **This file**: Quick reference guide
- **`DETAILED_MIGRATION_GUIDE.md`**: Complete step-by-step instructions with code examples

## Migration Strategy

The Jenkinsfile is structured to allow **gradual migration**:
1. ✅ Current pipeline remains **fully functional** (nothing commented out)
2. 📝 TODO comments show where to integrate groovy functions
3. 🔄 Easy to uncomment and replace stages one at a time

## ⚠️ Important Findings

After analyzing all 4 groovy files:

1. **GitLab vs GitHub**: All groovy files use GitLab-specific environment variables. You'll need to create GitHub-compatible wrappers.

2. **Checkout Inside Functions**: Each major function (`unitTestAndCodeCoverage`, `sonarQubeScan`, `buildService`) includes its own checkout stage. Remove your checkout stage when using these functions.

3. **Function Dependencies**: The groovy functions depend on:
   - GitLab env vars (`gitlabActionType`, `gitlabSourceBranch`, etc.)
   - Specific credentials (`vinhtx3-gitlab`, `vinhtx3-habor`)
   - External scripts (`cicd/build.sh`, `cicd/push.sh`)
   - SonarQube scanner at specific path
   - Harbor registry (not GCP Artifact Registry)

4. **Migration Approach**: 
   - Create NEW GitHub-compatible wrapper functions (don't modify existing groovy files yet)
   - Test each step individually
   - Keep fallbacks to current code

## Step-by-Step Migration Plan

### Phase 1: Load Groovy Files (Test Loading)
**Goal**: Verify groovy files can be loaded without breaking the pipeline

1. Uncomment at the top of Jenkinsfile:
```groovy
// Load groovy library files
jenkinsfile_CI = load 'setup/cicd/jenkinsfile_CI.groovy'
jenkinsfile_utils = load 'setup/cicd/jenkinsfile_utils.groovy'
jenkinsfile_CD = load 'setup/cicd/jenkinsfile_CD.groovy'
```

2. Test the pipeline - should still work (groovy files loaded but not used)

### Phase 2: Replace Checkout Stage
**Goal**: Use groovy checkout function

⚠️ **IMPORTANT**: Groovy functions already include their own checkout stages!
- `unitTestAndCodeCoverage()` has `stage("Checkout source code")`
- `sonarQubeScan()` has `stage("Checkout Source Code")`
- `buildService()` has `stage("Checkout Source Code")`

**So when migrating:**
1. When you uncomment a groovy function stage, **REMOVE** the separate `stage('Checkout')` above
2. Each groovy function handles its own checkout internally
3. **Note**: Need to adapt checkout for GitHub (currently uses GitLab env vars in `jenkinsfile_utils.checkoutSourceCode()`)

### Phase 3: Replace Test Stage with Groovy Function
**Goal**: Use groovy unitTestAndCodeCoverage() function

⚠️ **IMPORTANT**: This function includes checkout!

1. Find commented `stage('Unit Test & Code Coverage')`
2. **Remove** the `stage('Checkout')` above (function handles it)
3. Uncomment the entire `stage('Unit Test & Code Coverage')`
4. Comment out the current `stage('Test')` and `stage('Package')`
5. Test the new stage - it will checkout and run tests automatically

### Phase 4: Replace Build Stage
**Goal**: Use groovy buildService() function

1. Uncomment `stage('Build Service')`
2. Comment out current `stage('Package')`
3. Adapt the function for your build process

### Phase 5: Replace Docker Push Stage
**Goal**: Use groovy pushImageDocker() function

1. Uncomment `stage('Push Image To Harbor')`
2. Comment out current `stage('Build & Push Docker Image')`
3. Adapt for your Docker registry (currently uses Harbor)

### Phase 6: Replace Deploy Stage
**Goal**: Use groovy release2k8s() function

1. Uncomment `stage('Deploy to K8s')`
2. Comment out current `stage('Deploy to Kubernetes')`
3. Adapt function parameters for your K8s setup

### Phase 7: Add SonarQube Scan
**Goal**: Add code quality scanning

1. Uncomment `stage('SonarQube Scan')`
2. Configure SonarQube settings
3. Test the scan stage

### Phase 8: Add Security Scan
**Goal**: Add security scanning

1. Uncomment `stage('Security Scan')`
2. Configure Acunetix settings (if using)
3. Test the security scan

### Phase 9: Event-Based Routing (Full Migration)
**Goal**: Replace entire pipeline with event-based routing

1. Replace entire pipeline block with the scripted pipeline at bottom
2. Adapt `checkBuildType()` for GitHub (currently uses GitLab vars)
3. Map GitHub events to build types:
   - `PUSH` → `push_commit_build`
   - `PULL_REQUEST` → `merge_request_build`
   - `TAG_PUSH` → `deploy_production`

## GitHub vs GitLab Differences

The groovy files use **GitLab** environment variables:
- `env.gitlabActionType` (PUSH, MERGE, NOTE, TAG_PUSH)
- `env.gitlabSourceBranch`
- `env.gitlabTargetBranch`

**GitHub** uses different variables:
- `env.CHANGE_ID` (PR number, empty for push)
- `env.CHANGE_TARGET` (target branch for PR)
- `env.BRANCH_NAME` (current branch)
- `env.GIT_BRANCH` (full branch name)

### Adaptation Needed

Create a GitHub adapter function:
```groovy
def checkBuildTypeGitHub() {
    def buildType = "none"
    if (env.CHANGE_ID) {
        // It's a pull request
        buildType = "merge_request_build"
    } else if (env.BRANCH_NAME.startsWith("tags/")) {
        // It's a tag push
        buildType = "deploy_production"
    } else {
        // It's a regular push
        buildType = "push_commit_build"
    }
    return buildType
}
```

## Migration Checklist

- [ ] Phase 1: Load groovy files (test loading)
- [ ] Phase 2: Replace checkout stage
- [ ] Phase 3: Replace test stage with groovy function
- [ ] Phase 4: Replace build stage
- [ ] Phase 5: Replace Docker push stage
- [ ] Phase 6: Replace deploy stage
- [ ] Phase 7: Add SonarQube scan
- [ ] Phase 8: Add security scan
- [ ] Phase 9: Event-based routing (full migration)

## Testing Each Phase

After each phase:
1. Commit changes
2. Push to repository
3. Check Jenkins build runs successfully
4. Verify functionality matches previous phase
5. Fix any issues before proceeding

## Rollback Strategy

If something breaks:
1. Revert the uncommented sections
2. Re-enable the commented original stages
3. Fix issues and try again

All original code is preserved in comments for easy rollback!

