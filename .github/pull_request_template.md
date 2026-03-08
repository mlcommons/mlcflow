## ✅ PR Checklist

- [ ] Target branch is `dev`

📌 Note: PRs must be raised against `dev`. Do not commit directly to `main`.

### ✅ Testing & CI
- [ ] Have tested the changes in my local environment, else have properly conveyed in the PR description
- [ ] The change includes a GitHub Action to test the script(if it is possible to be added).
- [ ] No existing GitHub Actions are failing because of this change.

### 📚 Documentation
- [ ] README or help docs are updated for new features or changes.
- [ ] CLI help messages are meaningful and complete.

### 📁 File Hygiene & Output Handling
- [ ] No unintended files (e.g., logs, cache, temp files, __pycache__, output folders) are committed.

### 🛡️ Safety & Security
- [ ] No secrets or credentials are committed.
- [ ] Paths, shell commands, and environment handling are safe and portable.

### 🙌 Contribution Hygiene
- [ ] PR title and description are concise and clearly state the purpose of the change.
- [ ] Related issues (if any) are properly referenced using `Fixes #` or `Closes #`.
- [ ] All reviewer feedback has been addressed.

### 🤖 Contributor Attestation for LLM-Assisted Code
- [ ] If this PR includes LLM-generated or assisted code, I confirm that I have reviewed the code, take responsibility for it, and to the best of my knowledge it does not contain proprietary or improperly sourced material and can be contributed under the project’s license.
