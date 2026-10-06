# Task: Address Container Privilege Escalation Risk in Dockerfile

## Context & Issue Description
The application build context currently lacks a declared `USER` instruction, meaning the Gunicorn process defaults to executing tasks with absolute `root` permissions inside the container. If an application dependency or web framework exploit is uncovered, an attacker could achieve immediate container escape or compromise the host filesystem.

## Target Project Assets
- **Container Workspace:** `Dockerfile`
- **Deployment Build Validation:** Local Docker build check

## Execution Steps

### Step 1: Secure Container Context Configuration
1. Inspect the lower execution layer of the root `Dockerfile`.
2. Right before the final application entry point/execution `CMD` block, inject a non-root system user and group framework to drop privileges safely:
   ```dockerfile
   RUN addgroup --system app && adduser --system --ingroup app app
   USER app
   ```

### Step 2: Filesystem Access Audit
1. Verify that the newly created `app` user maintains appropriate read/write context over application source directories and local dashboard asset routes.

### Step 3: Local Quality Gate Check
1. Run a local build check to confirm the image compiles cleanly with the new permission layout without causing downstream boot failures.
