require('dns').setServers(['8.8.8.8', '8.8.4.4']);
require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const multer = require('multer');
const axios = require('axios');
const FormData = require('form-data');
const cron = require('node-cron');

const app = express();
app.use(cors());
app.use(express.json());

// Set up Multer memory storage
const storage = multer.memoryStorage();
const upload = multer({ storage: storage });

// ── Root Route — fixes the {"error":"Not found"} on browser open ──────────────
app.get('/', (req, res) => {
  res.json({
    service:  'DTC e-Bus Pass — Backend API',
    status:   'Running ✅',
    version:  '1.0.0',
    time:     new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }),
    endpoints: {
      health:       'GET  /api/health',
      allPasses:    'GET  /api/passes',
      getPass:      'GET  /api/passes/:passno',
      checkPass:    'GET  /api/passes/check?mobile=&dob=',
      applyPass:    'POST /api/passes/apply',
      updatePass:   'PUT  /api/passes/:id',
      deletePass:   'DELETE /api/passes/:id'
    }
  });
});

// Connect to MongoDB
mongoose.connect(process.env.MONGODB_URI)
  .then(() => console.log('Connected to MongoDB successfully!'))
  .catch(err => console.error('MongoDB connection error:', err));

// Schema
const passSchema = new mongoose.Schema({
  passno: { type: String, unique: true, required: true },
  name: { type: String, required: true },
  mobile: { type: String, required: true },
  dob: { type: String, required: true },
  photoUrl: { type: String, required: true },
  qrCodeUrl: { type: String },
  validFrom: { type: Date, default: Date.now },
  validTo: { type: Date, required: true }
}, { timestamps: true });

const Pass = mongoose.model('Pass', passSchema);

function generatePassNumber() {
  return '750' + Math.floor(1000000000 + Math.random() * 9000000000).toString();
}

// Create a New Pass
app.post('/api/passes/apply', upload.single('photo'), async (req, res) => {
  try {
    const { name, mobile, dob } = req.body;
    
    if (!req.file) {
      return res.status(400).json({ error: 'Please upload a photo.' });
    }

    if (!process.env.IMGBB_API_KEY || process.env.IMGBB_API_KEY === 'YOUR_IMGBB_API_KEY_HERE') {
      return res.status(500).json({ error: 'ImgBB API key is missing. Please add it to the .env file.' });
    }

    // Upload to ImgBB
    const form = new FormData();
    form.append('image', req.file.buffer.toString('base64'));

    console.log('Uploading photo to ImgBB...');
    const imgbbResponse = await axios.post(
      `https://api.imgbb.com/1/upload?key=${process.env.IMGBB_API_KEY}`, 
      form,
      { headers: form.getHeaders() }
    );

    const photoUrl = imgbbResponse.data.data.url;
    console.log('Uploaded successfully! URL:', photoUrl);

    // Calculate Validity
    const validFrom = new Date();
    const validTo = new Date();
    validTo.setMonth(validFrom.getMonth() + 5);
    validTo.setDate(validTo.getDate() - 1);

    const passno = generatePassNumber();
    const newPass = new Pass({
      passno,
      name: name.toUpperCase(),
      mobile,
      dob,
      photoUrl,
      validFrom,
      validTo
    });

    await newPass.save();
    console.log(`Saved pass ${passno} to MongoDB.`);

    const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:8000';
    res.status(201).json({
      success: true,
      passno,
      redirectUrl: `${FRONTEND_URL}/viewEBPass.html?passno=${passno}`
    });

  } catch (error) {
    console.error('Error creating pass:', error.message);
    res.status(500).json({ error: 'Server error processing application.' });
  }
});

// Check Pass Existence
app.get('/api/passes/check', async (req, res) => {
  try {
    const { mobile, dob } = req.query;
    if (!mobile || !dob) {
      return res.status(400).json({ error: 'Mobile and Date of Birth are required.' });
    }
    const pass = await Pass.findOne({ mobile: mobile.trim(), dob: dob.trim() });
    if (pass) {
      return res.json({ exists: true, pass });
    }
    res.json({ exists: false });
  } catch (error) {
    console.error('Error checking pass existence:', error.message);
    res.status(500).json({ error: 'Server error checking pass.' });
  }
});

// Get All Passes (Admin Panel) — MUST be before /:passno to avoid route conflict
app.get('/api/passes', async (req, res) => {
  try {
    const passes = await Pass.find().sort({ createdAt: -1 });
    res.json(passes);
  } catch (error) {
    console.error('Error fetching passes:', error.message);
    res.status(500).json({ error: 'Server error retrieving passes.' });
  }
});

// Get Single Pass Details by Pass Number
app.get('/api/passes/:passno', async (req, res) => {
  try {
    const pass = await Pass.findOne({ passno: req.params.passno });
    if (!pass) {
      return res.status(404).json({ error: 'Bus Pass not found.' });
    }
    res.json(pass);
  } catch (error) {
    res.status(500).json({ error: 'Server error retrieving pass.' });
  }
});

// Update Pass (Admin Panel)
app.put('/api/passes/:id', upload.fields([{ name: 'photo', maxCount: 1 }, { name: 'qrCode', maxCount: 1 }]), async (req, res) => {
  try {
    const { name, mobile, dob, passno, validFrom, validTo } = req.body;
    const passId = req.params.id;

    const pass = await Pass.findById(passId);
    if (!pass) {
      return res.status(404).json({ error: 'Pass not found.' });
    }

    // Process photo file if uploaded
    if (req.files && req.files.photo && req.files.photo[0]) {
      const form = new FormData();
      form.append('image', req.files.photo[0].buffer.toString('base64'));

      console.log('Uploading new photo to ImgBB...');
      const imgbbResponse = await axios.post(
        `https://api.imgbb.com/1/upload?key=${process.env.IMGBB_API_KEY}`,
        form,
        { headers: form.getHeaders() }
      );
      pass.photoUrl = imgbbResponse.data.data.url;
      console.log('New photo URL:', pass.photoUrl);
    }

    // Process qrCode file if uploaded
    if (req.files && req.files.qrCode && req.files.qrCode[0]) {
      const form = new FormData();
      form.append('image', req.files.qrCode[0].buffer.toString('base64'));

      console.log('Uploading custom QR Code to ImgBB...');
      const imgbbResponse = await axios.post(
        `https://api.imgbb.com/1/upload?key=${process.env.IMGBB_API_KEY}`,
        form,
        { headers: form.getHeaders() }
      );
      pass.qrCodeUrl = imgbbResponse.data.data.url;
      console.log('Custom QR Code URL:', pass.qrCodeUrl);
    }

    if (name) pass.name = name.trim().toUpperCase();
    if (mobile) pass.mobile = mobile.trim();
    if (dob) pass.dob = dob.trim();
    if (passno) pass.passno = passno.trim();
    if (validFrom) pass.validFrom = new Date(validFrom);
    if (validTo) pass.validTo = new Date(validTo);

    await pass.save();
    console.log(`Successfully updated pass ${pass.passno}`);
    res.json({ success: true, pass });
  } catch (error) {
    console.error('Error updating pass:', error.message);
    res.status(500).json({ error: 'Server error updating pass.' });
  }
});

// Delete Pass (Admin Panel)
app.delete('/api/passes/:id', async (req, res) => {
  try {
    const pass = await Pass.findByIdAndDelete(req.params.id);
    if (!pass) {
      return res.status(404).json({ error: 'Pass not found.' });
    }
    res.json({ success: true, message: 'Pass deleted successfully.' });
  } catch (error) {
    console.error('Error deleting pass:', error.message);
    res.status(500).json({ error: 'Server error deleting pass.' });
  }
});

// ── Health Check Endpoint ─────────────────────────────────────────────────────
// Used by cron-job.org (external) to ping and keep Render awake on free tier
app.get('/api/health', (req, res) => {
  res.json({
    status: 'OK',
    time: new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }),
    service: 'DTC e-Bus Pass Backend'
  });
});

// ── Cron Job (runs inside Render server process) ──────────────────────────────────────
// Schedule: Every 14 minutes, all hours, all days (keeps Render free-tier awake 24/7)
// Free tier spins down after 15 min of inactivity, so we ping every 14 min to prevent that.
//
//  ┌─────── minute  (*/14 = every 14 min)
//  │   ┌─── hour    (* = every hour, 24/7)
//  │   │   ┌ day  ┌ month  ┌ weekday
// */14  *   *     *        *

cron.schedule('*/14 * * * *', async () => {
  const now = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
  console.log(`[CRON] ⏰ Tick at ${now}`);

  try {
    // ── Task 1: Self health-check ───────────────────────────────────────
    const SELF_URL = process.env.RENDER_EXTERNAL_URL || `http://localhost:${process.env.PORT || 5000}`;
    const res = await axios.get(`${SELF_URL}/api/health`, { timeout: 8000 });
    console.log(`[CRON] ✅ Health OK → ${res.data.status} (${SELF_URL})`);

    // ── Add more tasks here ───────────────────────────────────────
    // await expireOldPasses();
    // await sendReminders();

  } catch (err) {
    console.error(`[CRON] ❌ Task failed: ${err.message}`);
  }
}, {
  scheduled: true,
  timezone: 'Asia/Kolkata'
});

console.log('[CRON] 🚀 Scheduled: every 14 min, 24/7 (*/14 * * * * Asia/Kolkata) — keeps Render awake');

// ── Start Server ──────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Backend server running at http://localhost:${PORT}`);
});
