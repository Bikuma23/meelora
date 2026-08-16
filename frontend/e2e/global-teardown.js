// Global teardown: remove disposable E2E company artifacts (ZZ *) from Mongo.
// Runs after the whole suite so no "ZZ Lifecycle Test" pollution remains.
const { execFileSync } = require("child_process");

module.exports = async () => {
  try {
    const out = execFileSync("python", ["/app/backend/scripts/cleanup_e2e_companies.py"], {
      encoding: "utf-8", timeout: 30000,
    });
    process.stdout.write(out);
  } catch (e) {
    process.stdout.write(`globalTeardown cleanup skipped: ${e.message}\n`);
  }
};
