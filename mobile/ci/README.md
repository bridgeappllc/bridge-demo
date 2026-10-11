# iOS CI workflow (to install)

`ios-build.yml` builds the Capacitor iOS app for the iOS Simulator, unsigned, on GitHub's macos-26 runner (Xcode 26). It proves the project compiles.

It lives here because the bot's GitHub token has no `workflow` scope, and GitHub refuses pushes that add files under `.github/workflows/` without that scope. To enable it, use either option:

- **Option 1: GitHub web.** On branch `store-ready`, choose Add file → Create new file and name it `.github/workflows/ios-build.yml`. Paste the contents of this file and commit.
- **Option 2: grant the scope.** Run `gh auth refresh -h github.com -s workflow` on the box (this needs a browser login by Paul). Then the bot can move the file and push.

The workflow then runs on every push to `store-ready` that touches the app, and on demand from Actions → "iOS build" → Run workflow.
