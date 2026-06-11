// cron.js  –  DTC e-Bus Pass Backend Keep-Alive Cron
// --------------------------------------------------
// Schedule : Every 14 minutes, 24/7 (prevents Render free-tier sleep)
// Cron expr: */14 * * * *
//
//  Why 14 min? Render free-tier spins down after 15 min of inactivity.
//  Pinging every 14 min keeps the server warm at all times.
//
//  Field reference:
//   ┌──────────── minute  (0-59)   → */14 = every 14 min
//   │   ┌──────── hour    (0-23)   → * = all hours
//   │   │   ┌────── day of month  → * = every day
//   │   │   │   ┌──── month       → * = every month
//   │   │   │   │   ┌── day of week → * = every day
//   │   │   │   │   │
//  */14  *   *   *   *
//
// Usage:
//   node cron.js

require('dotenv').config();
const cron  = require('node-cron');
const axios = require('axios');

const BACKEND_URL = process.env.BACKEND_URL || process.env.RENDER_EXTERNAL_URL || `http://localhost:${process.env.PORT || 5000}`;

// ── Helper ────────────────────────────────────────────────────────────────────
function timestamp() {
  return new Date().toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour12: true,
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function log(msg) {
  console.log(`[${timestamp()}]  ${msg}`);
}

// ── Tasks to run every tick ───────────────────────────────────────────────
async function pingHealth() {
  try {
    // Ping /api/health (lightweight) instead of /api/passes (fetches entire DB)
    // Timeout set to 60s to accommodate Render cold starts when server is spun down
    const res = await axios.get(`${BACKEND_URL}/api/health`, { timeout: 60000 });
    log(`✅  Keep-alive ping OK  →  ${BACKEND_URL}/api/health  (HTTP ${res.status})`);
  } catch (err) {
    log(`❌  Keep-alive ping FAILED  →  ${err.message}`);
  }
}

async function runTasks() {
  log('⏰  Cron tick — running tasks…');
  await pingHealth();

  // ── Add more tasks here as needed ──
  // await syncExpiredPasses();
  // await sendReminderNotifications();
  log('✔️   All tasks done.');
}

// ── Schedule ───────────────────────────────────────────────────────────────
//   */10 * * * *
//   ↑
//   Every 10 min, 24/7 (keeps Render awake continuously)

const CRON_EXPR = '*/10 * * * *';

if (!cron.validate(CRON_EXPR)) {
  console.error('Invalid cron expression:', CRON_EXPR);
  process.exit(1);
}

const job = cron.schedule(CRON_EXPR, runTasks, {
  scheduled: true,
  timezone: 'Asia/Kolkata'   // IST (UTC+5:30)
});

log(`🚀  Keep-alive cron started — schedule: "${CRON_EXPR}"  (every 10 min, 24/7)`);

// Graceful shutdown
process.on('SIGINT',  () => { job.stop(); log('🛑  Cron stopped (SIGINT).');  process.exit(0); });
process.on('SIGTERM', () => { job.stop(); log('🛑  Cron stopped (SIGTERM).'); process.exit(0); });
