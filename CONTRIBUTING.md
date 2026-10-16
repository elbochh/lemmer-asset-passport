# Contributing

Follow the README to install Node, Python, PostgreSQL, and dependencies. Keep local configuration in `.env`, using `.env.example` as the template. Use synthetic data and a separate development/test database.

1. Clone the repository (or fork it if you do not have write access).
2. Create a branch: `git switch -c feature/your-change`.
3. Make the change and run `npm run build`. Run the backend tests against an isolated PostgreSQL database for backend changes; use `npm run test:mobile` with the local servers for responsive interface changes.
4. Commit only the files relevant to your change, push your branch, and open a pull request against `main`. Describe the behavior changed and checks completed.

Do not commit credentials, `.env`, customer/employee records, uploaded service papers, database exports, backups, private company correspondence, or `.local/`. Use clearly synthetic fixtures. Update `.env.example` with placeholders when adding a setting.

The Calgary equipment workflow is the current implementation scope. Review `docs/V3_CALGARY.md` before changing permissions or procedure approval. Technical and privacy review remain necessary before shared diagnostic knowledge is approved. AI evidence review does not establish a correct diagnosis.

Public product imagery, logos, and manual extracts retain their original ownership; see `docs/SOURCES.md`. No additional license is granted for those assets.
