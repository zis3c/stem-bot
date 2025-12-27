# Contributing to Eligible STEM Bot

Thank you for your interest in contributing! We welcome bug reports, feature requests, and pull requests.

## How to Contribute

### 1. Reporting Bugs
- Check the [Issues](https://github.com/zis3c/stem-bot/issues) tab to see if the bug has already been reported.
- If not, open a new issue with a clear title and description.
- Include steps to reproduce the bug.

### 2. Suggesting Features
- Open a new issue and tag it as `enhancement`.
- Explain why the feature would be useful and how it should work.

### 3. Pull Requests (Code Contributions)
1.  **Fork** the repository.
2.  **Clone** your fork locally.
3.  Create a new branch: `git checkout -b my-new-feature`
4.  Make your changes and commit: `git commit -m 'Add some feature'`
5.  Push to your fork: `git push origin my-new-feature`
6.  Open a **Pull Request** on the main repository.

## Coding Standards
- Use Python 3.10+.
- Follow PEP 8 style guidelines.
- Ensure your code allows for high concurrency (async/await).

### Testing Logic
When modifying `database.py` or `admin.py`, strictly adhere to the 18-column structure (A-R) of the Google Sheet.
*   **Google Apps Script**: If you change the logic for ID generation, update `google_apps_script.js` accordingly.
*   **Verification**: Always verify that "Detailed View" in Admin Search maps correctly to the sheet columns.

## License
By contributing, you agree that your contributions will be licensed under the MIT License.
