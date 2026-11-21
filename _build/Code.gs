/**
 * colby! Tour Book – App Data backend (Google Apps Script web app).
 *
 * Set up (on a computer, about 5 minutes):
 *  1. Create a Google Sheet named "colby! Tour Book – App Data" in the touring folder.
 *  2. Extensions > Apps Script. Delete what's there, paste this whole file, Save.
 *  3. Deploy > New deployment > gear > Web app. Execute as: Me. Who has access: Anyone. Deploy.
 *  4. Authorize (Advanced > Go to project (unsafe) > Allow). Copy the /exec URL and send it to Claude.
 * The Guests and Travel tabs are created on first use.
 *
 * Optional: Project Settings > Script properties > ANTHROPIC_API_KEY reads travel
 * screenshots instantly (paid, about a cent each). Without it, screenshots are saved
 * as "pending" rows and filed by the daily refresh.
 */
var TOKEN = 'REPLACE_WITH_TOKEN';            // same value as api.json "token"
var FOLDER_NAME = 'colby! Tour Book – Travel Screenshots';
var MODEL = 'claude-haiku-5-5';
var COLS = {
  Guests: ['id', 'date', 'name', 'company', 'category', 'plus', 'status', 'addedBy', 'addedAt', 'source', 'synced'],
  Travel: ['id', 'kind', 'date', 'endDate', 'title', 'from', 'to', 'start', 'end', 'address', 'conf', 'who', 'notes',
           'imageId', 'imageUrl', 'addedBy', 'addedAt', 'source', 'status']
};
var HIDDEN_TRAVEL = { duplicate: 1, unreadable: 1 };

function doGet() { return out_({ ok: true, app: 'colby! Tour Book' }); }

function doPost(e) {
  try {
    var b = JSON.parse(e.postData.contents);
    if (b.token !== TOKEN) return out_({ ok: false, error: 'not_granted' });
    switch (b.action) {
      case 'list':   return out_({ ok: true, rows: list_(b.table, b.date) });
      case 'add':    return out_({ ok: true, id: add_(b.table, b.row || {}) });
      case 'update': update_(b.table, b.id, b.patch || {}); return out_({ ok: true });
      case 'remove': remove_(b.table, b.id); return out_({ ok: true });
      case 'upload': return out_(upload_(b.data, b.type));
      case 'read':   return out_(read_(b.prompt, b.data, b.type));
    }
    return out_({ ok: false, error: 'bad_action' });
  } catch (err) {
    return out_({ ok: false, error: 'failed', detail: String(err) });
  }
}

function out_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function sheet_(table) {
  if (!COLS[table]) throw new Error('bad table');
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(table);
  if (!sh) { sh = ss.insertSheet(table); sh.appendRow(COLS[table]); sh.setFrozenRows(1); }
  return sh;
}

function rows_(table) {
  var sh = sheet_(table), v = sh.getDataRange().getDisplayValues(), head = v[0], res = [];
  for (var i = 1; i < v.length; i++) {
    var o = { _row: i + 1 };
    for (var j = 0; j < head.length; j++) o[head[j]] = v[i][j];
    if (o.id) res.push(o);
  }
  return res;
}

function clean_(o) { var c = {}; for (var k in o) if (k !== '_row') c[k] = o[k]; return c; }

function list_(table, date) {
  return rows_(table).filter(function (r) {
    if (table === 'Guests') return r.date === date;
    return !HIDDEN_TRAVEL[r.status];
  }).map(clean_);
}

function add_(table, row) {
  var lock = LockService.getScriptLock(); lock.waitLock(10000);
  try {
    var id = Utilities.getUuid().slice(0, 12);
    row.id = id;
    sheet_(table).appendRow(COLS[table].map(function (c) { return row[c] == null ? '' : String(row[c]); }));
    return id;
  } finally { lock.releaseLock(); }
}

function find_(table, id) {
  var r = rows_(table).filter(function (x) { return x.id === id; })[0];
  if (!r) throw new Error('not found');
  return r;
}

function update_(table, id, patch) {
  var sh = sheet_(table), r = find_(table, id);
  COLS[table].forEach(function (c, j) {
    if (c !== 'id' && c in patch) sh.getRange(r._row, j + 1).setValue(String(patch[c]));
  });
}

function remove_(table, id) { sheet_(table).deleteRow(find_(table, id)._row); }

function folder_() {
  var it = DriveApp.getFoldersByName(FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER_NAME);
}

function upload_(data, type) {
  var blob = Utilities.newBlob(Utilities.base64Decode(data), type || 'image/jpeg',
    'travel-' + Utilities.formatDate(new Date(), 'GMT', 'yyyyMMdd-HHmmss') + '.jpg');
  var f = folder_().createFile(blob);
  f.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  return { ok: true, id: f.getId(), url: 'https://drive.google.com/thumbnail?id=' + f.getId() + '&sz=w1600' };
}

function read_(prompt, data, type) {
  var key = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
  if (!key) return { ok: false, error: 'no_key' };
  var res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01' },
    payload: JSON.stringify({
      model: MODEL, max_tokens: 2000,
      messages: [{ role: 'user', content: [
        { type: 'image', source: { type: 'base64', media_type: type || 'image/jpeg', data: data } },
        { type: 'text', text: prompt }
      ] }]
    })
  });
  if (res.getResponseCode() === 429) return { ok: false, error: 'rate_limited' };
  if (res.getResponseCode() !== 200) return { ok: false, error: 'failed' };
  var text = JSON.parse(res.getContentText()).content.map(function (c) { return c.text || ''; }).join('');
  var m = text.match(/\{[\s\S]*\}/);
  return { ok: true, value: m ? JSON.parse(m[0]) : { bookings: [] } };
}
