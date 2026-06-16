// cron.js  –  DTC e-Bus Pass Backend Keep-Alive Cron
// --------------------------------------------------
// Run this SEPARATELY (e.g. on cron-job.org, Vercel CRON, Railway, etc.)
// OR locally: node cron.js
//
// Schedule : Every 10 minutes, 24/7 (prevents Render free-tier sleep)
// Cron expr: */10 * * * *
//
// NOTE: The server.js already has a built-in cron that pings itself.
//       This external cron.js is a BACKUP — it pings from OUTSIDE the
//       server process, which is more reliable (hits the real HTTP layer).
//
//  Field reference:
//   ┌──────────── minute  (0-59)   → */10 = every 10 min
//   │   ┌──────── hour    (0-23)   → * = all hours
//   │   │   ┌────── day of month  → * = every day
//   │   │   │   ┌──── month       → * = every month
//   │   │   │   │   ┌── day of week → * = every day
//   │   │   │   │   │
//  */10  *   *   *   *

require('dotenv').config();
const cron  = require('node-cron');
const axios = require('axios');

// ── Backend URL ──────────────────────────────────────────────────────────────
// RENDER_EXTERNAL_URL is auto-set by Render in production.
// Fallback to the known public Render URL, then localhost for local dev.
const BACKEND_URL = process.env.RENDER_EXTERNAL_URL
                 || process.env.BACKEND_URL
                 || 'https://dtcpass-backend-api.onrender.com';

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
    // Ping /api/health (lightweight) — 60s timeout to handle Render cold starts
    const res = await axios.get(`${BACKEND_URL}/api/health`, { timeout: 60000 });
    log(`✅  Keep-alive ping OK  →  ${BACKEND_URL}/api/health  (HTTP ${res.status})`);
    if (res.data && res.data.status) {
      log(`    Server status: ${res.data.status}  |  Time: ${res.data.time}`);
    }
  } catch (err) {
    log(`❌  Keep-alive ping FAILED  →  ${err.message}`);
    if (err.code === 'ECONNREFUSED') {
      log(`    ℹ️  Connection refused — is the server running? URL: ${BACKEND_URL}`);
    } else if (err.code === 'ENOTFOUND') {
      log(`    ℹ️  DNS lookup failed — check BACKEND_URL: ${BACKEND_URL}`);
    }
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
log(`    Target URL: ${BACKEND_URL}/api/health`);

// Run once immediately on startup to verify connectivity
log('🔍  Running initial ping to verify backend is reachable...');
pingHealth();

// Graceful shutdown
process.on('SIGINT',  () => { job.stop(); log('🛑  Cron stopped (SIGINT).');  process.exit(0); });
process.on('SIGTERM', () => { job.stop(); log('🛑  Cron stopped (SIGTERM).'); process.exit(0); });
