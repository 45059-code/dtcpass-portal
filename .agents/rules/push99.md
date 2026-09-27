# Push99 Rule

Whenever the user writes `push99` or `push 99` (or mentions it):
1. Automatically run `git status` and `git diff`.
2. Stage all changed files (`git add -A`).
3. Commit with a meaningful, concise commit message (`git commit -m "..."`).
4. Push to remote repository (`git push origin main`).
5. Confirm the commit hash and push status to the user.
