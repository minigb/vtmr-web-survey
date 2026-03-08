const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 5555;
const RESULTS_READ_TOKEN = process.env.RESULTS_READ_TOKEN || '';
const ADMIN_API_TOKEN = process.env.ADMIN_API_TOKEN || '';

app.use(express.static('public'));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

const resultsFile = path.join(dataDir, 'results.json');
const userMappingsFile = path.join(dataDir, 'user_mappings.json');
const assignmentsPublicFile = path.join(dataDir, 'test_case_assignments_public.json');
const assignmentsPrivateMapFile = path.join(dataDir, 'test_case_assignments_private_map.json');

function readJsonFile(filePath, fallbackValue) {
  try {
    if (!fs.existsSync(filePath)) return fallbackValue;
    const raw = fs.readFileSync(filePath, 'utf8').trim();
    if (!raw) return fallbackValue;
    return JSON.parse(raw);
  } catch (error) {
    console.error(`Failed to read JSON file: ${filePath}`, error);
    return fallbackValue;
  }
}

function writeJsonFile(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), 'utf8');
}

function ensureResultsFile() {
  if (!fs.existsSync(resultsFile)) {
    writeJsonFile(resultsFile, {});
    return;
  }
  const raw = fs.readFileSync(resultsFile, 'utf8').trim();
  if (!raw) {
    writeJsonFile(resultsFile, {});
  }
}

function normalizeMappings(raw) {
  const base = {
    byUsername: {},
    byUserId: {},
  };
  if (!raw || typeof raw !== 'object') return base;
  if (raw.byUsername && typeof raw.byUsername === 'object') base.byUsername = raw.byUsername;
  if (raw.byUserId && typeof raw.byUserId === 'object') base.byUserId = raw.byUserId;
  return base;
}

function ensureUserMappingsFile() {
  if (!fs.existsSync(userMappingsFile)) {
    writeJsonFile(userMappingsFile, normalizeMappings(null));
    return;
  }
  const normalized = normalizeMappings(readJsonFile(userMappingsFile, null));
  writeJsonFile(userMappingsFile, normalized);
}

ensureResultsFile();
ensureUserMappingsFile();

let assignmentsByUserId = {};
let assignmentUserIds = [];
const videoMapping = new Map();

function loadSurveyAssets() {
  const publicPayload = readJsonFile(assignmentsPublicFile, null);
  if (!publicPayload || typeof publicPayload !== 'object' || !publicPayload.users || typeof publicPayload.users !== 'object') {
    throw new Error(`Invalid or missing assignments file: ${assignmentsPublicFile}`);
  }
  assignmentsByUserId = publicPayload.users;
  assignmentUserIds = Object.keys(assignmentsByUserId).sort();
  if (!assignmentUserIds.length) {
    throw new Error('No assigned user slots found in assignments file.');
  }

  const privatePayload = readJsonFile(assignmentsPrivateMapFile, null);
  if (!privatePayload || typeof privatePayload !== 'object' || !privatePayload.video_token_to_private || typeof privatePayload.video_token_to_private !== 'object') {
    throw new Error(`Invalid or missing private map file: ${assignmentsPrivateMapFile}`);
  }

  videoMapping.clear();
  Object.entries(privatePayload.video_token_to_private).forEach(([token, meta]) => {
    if (!meta || typeof meta !== 'object' || typeof meta.file !== 'string') return;
    videoMapping.set(token, meta.file);
  });

  console.log(`📋 Loaded ${assignmentUserIds.length} user slots and ${videoMapping.size} video tokens`);
}

function refreshMappings() {
  try {
    loadSurveyAssets();
    console.log('📋 Survey mappings refreshed');
    return true;
  } catch (error) {
    console.error('Error refreshing survey mappings:', error);
    return false;
  }
}

loadSurveyAssets();

function readResults() {
  return readJsonFile(resultsFile, {}) || {};
}

function readUserMappings() {
  const raw = readJsonFile(userMappingsFile, null);
  return normalizeMappings(raw);
}

function normalizeUsername(raw) {
  return String(raw || '').trim();
}

function usernameKey(username) {
  return normalizeUsername(username).toLowerCase();
}

function allocateUserSlot(username) {
  const normalized = normalizeUsername(username);
  if (!normalized) {
    return { error: 'Please provide a username.', status: 400 };
  }

  const key = usernameKey(normalized);
  const mappings = readUserMappings();

  const existing = mappings.byUsername[key];
  if (existing && existing.userId) {
    return { error: 'This username is already taken. Please use a different username.', status: 409 };
  }

  const availableUserId = assignmentUserIds.find((userId) => !mappings.byUserId[userId]);
  if (!availableUserId) {
    return { error: 'All participant slots are already taken.', status: 409 };
  }

  const record = {
    username: normalized,
    userId: availableUserId,
    assignedAt: new Date().toISOString(),
  };
  mappings.byUsername[key] = record;
  mappings.byUserId[availableUserId] = key;
  writeJsonFile(userMappingsFile, mappings);
  return { userId: availableUserId, mappings, username: normalized, created: true };
}

function getAssignedQuestions(userId) {
  const questions = assignmentsByUserId[userId];
  return Array.isArray(questions) ? questions : null;
}

function mapVideoFromAnonToken(videoObj) {
  if (!videoObj || typeof videoObj !== 'object') return null;
  const anonFile = String(videoObj.file || '');
  const realFile = videoMapping.get(anonFile);
  if (!realFile) return null;
  const parsed = path.parse(realFile);
  const subdir = path.basename(path.dirname(realFile));
  const canonicalId = `${subdir}_${parsed.name}`;
  return {
    id: canonicalId,
    file: realFile,
  };
}

function verifyVoteMatchesAssignment(vote, expectedByQuestionNo) {
  if (!vote || typeof vote !== 'object') return false;
  const questionNo = Number(vote.question_no);
  const expected = expectedByQuestionNo.get(questionNo);
  if (!expected) return false;

  const pair = Array.isArray(vote.pair) ? vote.pair : [];
  if (pair.length !== 2) return false;
  const tokens = [String(pair[0]?.file || ''), String(pair[1]?.file || '')].sort().join('|');
  return tokens === expected;
}

app.post('/api/refresh-mappings', (req, res) => {
  if (!ADMIN_API_TOKEN) {
    return res.status(404).json({ error: 'Not found' });
  }
  if (req.query.token !== ADMIN_API_TOKEN) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  const ok = refreshMappings();
  if (!ok) {
    return res.status(500).json({ ok: false, error: 'Failed to refresh mappings' });
  }
  return res.json({ ok: true, message: 'Mappings refreshed' });
});

// Register username -> fixed user slot, then return that slot's predefined questions.
app.post('/api/register-user', (req, res) => {
  const { username } = req.body || {};
  const allocation = allocateUserSlot(username);
  if (allocation.error) {
    return res.status(allocation.status || 409).json({ ok: false, error: allocation.error });
  }

  const userId = allocation.userId;
  const questions = getAssignedQuestions(userId);
  if (!questions) {
    return res.status(500).json({ ok: false, error: `No assignment found for ${userId}` });
  }

  const results = readResults();
  if (Object.prototype.hasOwnProperty.call(results, userId)) {
    return res.status(409).json({
      ok: false,
      error: 'This assigned user slot has already submitted responses.',
      alreadySubmitted: true,
      userId,
    });
  }

  return res.json({
    ok: true,
    userId,
    username: allocation.username,
    totalQuestions: questions.length,
    pairs: questions,
  });
});

// Optional endpoint for direct per-user assignment lookup.
app.get('/api/all-pairs/:userId', (req, res) => {
  const userId = String(req.params.userId || '');
  const questions = getAssignedQuestions(userId);
  if (!questions) {
    return res.status(404).json({ ok: false, error: 'Assigned user slot not found' });
  }
  return res.json(questions);
});

// Compatibility endpoint: report whether username is already mapped/submitted.
app.get('/api/check-user/:username', (req, res) => {
  const key = usernameKey(req.params.username);
  const mappings = readUserMappings();
  const record = mappings.byUsername[key];
  if (!record) {
    return res.json({ exists: false, mapped: false, submitted: false });
  }
  const results = readResults();
  const submitted = Object.prototype.hasOwnProperty.call(results, record.userId);
  return res.json({ exists: true, mapped: true, submitted, userId: record.userId });
});

// Serve anonymous videos by token from private map.
app.get('/api/video/:anonId', (req, res) => {
  const anonId = req.params.anonId;
  const realPath = videoMapping.get(anonId);
  if (!realPath) {
    return res.status(404).json({ error: 'Video not found' });
  }
  const videoPath = path.join(__dirname, realPath);
  if (!fs.existsSync(videoPath)) {
    return res.status(404).json({ error: 'Video file not found' });
  }
  return res.sendFile(videoPath);
});

app.post('/api/submit', (req, res) => {
  const { userId, username, votes } = req.body || {};
  if (!userId || !username || !Array.isArray(votes)) {
    return res.status(400).json({ ok: false, error: 'Missing required fields (userId, username, votes)' });
  }

  const normalizedUsername = normalizeUsername(username);
  const userKey = usernameKey(normalizedUsername);
  const mappings = readUserMappings();
  const mappingRecord = mappings.byUsername[userKey];
  if (!mappingRecord || mappingRecord.userId !== userId) {
    return res.status(403).json({ ok: false, error: 'Username and assigned user ID do not match' });
  }

  const expectedQuestions = getAssignedQuestions(userId);
  if (!expectedQuestions) {
    return res.status(404).json({ ok: false, error: 'Assigned user slot not found' });
  }
  if (votes.length !== expectedQuestions.length) {
    return res.status(400).json({
      ok: false,
      error: `Unexpected vote count: got ${votes.length}, expected ${expectedQuestions.length}`,
    });
  }

  const expectedByQuestionNo = new Map();
  expectedQuestions.forEach((question) => {
    const qNo = Number(question.question_no);
    const pair = Array.isArray(question.pair) ? question.pair : [];
    if (pair.length !== 2) return;
    const sig = [String(pair[0]?.file || ''), String(pair[1]?.file || '')].sort().join('|');
    expectedByQuestionNo.set(qNo, sig);
  });

  const hasUnexpectedVote = votes.some((vote) => !verifyVoteMatchesAssignment(vote, expectedByQuestionNo));
  if (hasUnexpectedVote) {
    return res.status(400).json({ ok: false, error: 'Vote payload does not match assigned questions' });
  }

  const results = readResults();
  if (Object.prototype.hasOwnProperty.call(results, userId)) {
    return res.status(409).json({ ok: false, error: 'This assigned user slot has already submitted' });
  }

  const votesWithOriginalPaths = votes.map((vote) => {
    const mappedPair = Array.isArray(vote.pair) ? vote.pair.map(mapVideoFromAnonToken) : [];

    const mappedResults = {};
    if (vote.results && typeof vote.results === 'object') {
      Object.entries(vote.results).forEach(([metric, result]) => {
        if (result && result.tie) {
          mappedResults[metric] = {
            tie: true,
            winner: null,
            loser: null,
          };
        } else {
          mappedResults[metric] = {
            tie: false,
            winner: mapVideoFromAnonToken(result?.winner),
            loser: mapVideoFromAnonToken(result?.loser),
          };
        }
      });
    }

    return {
      ...vote,
      pair: mappedPair,
      results: mappedResults,
    };
  });

  const invalidPayload = votesWithOriginalPaths.some((vote) => {
    if (!Array.isArray(vote.pair) || vote.pair.length !== 2 || vote.pair.some((video) => !video)) {
      return true;
    }
    if (!vote.results || typeof vote.results !== 'object') {
      return true;
    }
    for (const result of Object.values(vote.results)) {
      if (!result || typeof result !== 'object') return true;
      if (result.tie === true) continue;
      if (!result.winner || !result.loser) return true;
    }
    return false;
  });
  if (invalidPayload) {
    return res.status(400).json({ ok: false, error: 'Invalid vote payload' });
  }

  results[userId] = votesWithOriginalPaths;
  writeJsonFile(resultsFile, results);

  mappingRecord.completedAt = new Date().toISOString();
  mappings.byUsername[userKey] = mappingRecord;
  mappings.byUserId[userId] = userKey;
  writeJsonFile(userMappingsFile, mappings);

  return res.json({ ok: true });
});

app.get('/results', (req, res) => {
  if (!RESULTS_READ_TOKEN) {
    return res.status(404).json({ error: 'Not found' });
  }
  if (req.query.token !== RESULTS_READ_TOKEN) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  return res.sendFile(resultsFile);
});

app.listen(PORT, '0.0.0.0', () => console.log(`Listening on ${PORT}`));
