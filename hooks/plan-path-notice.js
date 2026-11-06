#!/usr/bin/env node
/* PreToolUse hook — 四職能（Phase 8 fail-counter 換載體；Phase 9 三點式 fixindex loop）：
 *   1. ExitPlanMode → 注入「計畫檔：<完整路徑>」；session 沒查過舊帳時
 *      加一句域級 find 提醒（三點式第 1 點：plan 起點靜態掃雷，一次性）
 *   2. Bash    → 偵測 fixindex find / mem-search，建 ran flag
 *   3. Bash    → 連續失敗（2026-10-20 移到 fixindex-pretool.js（重試同指紋召回）；
 *      停損由 Genie fail_streak.py 負責）
 *   4. Edit|Write → 沒查過才提醒一次；查過閉嘴
 * （三點式第 3 點「完工 fi」掛 Stop 事件，見 fi-reminder.sh）
 *
 * 為什麼原本掛在 PostToolUse 的 fail-counter.js 是死碼、為何換到這裡，
 * 見 fixindex（症狀：fail-counter 死碼 PostToolUse exit code）。
 * 摘要：(a) PostToolUse payload 沒有 exit code / success 欄位；
 *       (b) Bash 指令非零退出時 PostToolUse 根本不觸發。
 * PreToolUse 一定會觸發，但它本身也不知道「上一道指令」的結果——
 * 唯一可用訊號是 transcript_path 指向的 jsonl：tool_result 物件帶
 * `is_error` 布林，可跟 tool_use_id 配對回原始 Bash 指令。
 *
 * 已知限制（實測，2026-08-06）：此訊號只在「使用者直接互動的主 session」
 * 有效。用 Agent/Task 工具派出去的 sub-agent，其自身的 tool_use/tool_result
 * 不會即時寫回 transcript_path 指到的檔案（連續 12+ 次工具呼叫、6+ 分鐘
 * 都是 0 bytes 增量）——所以 sub-agent 對自己指令的連續失敗，這個機制
 * 目前偵測不到，只能偵測「使用者主 session 直接下的 Bash」。
 */

const fs = require('fs');
const path = require('path');
const { execFileSync, spawnSync } = require('child_process');

const PLANS_DIR = path.join(process.env.HOME || '/Users/51mini', '.claude', 'plans');
const GUARD_DIR = path.join(process.env.HOME || '/Users/51mini', '.claude', 'guard-state');
const TRANSCRIPT_TAIL_BYTES = 200 * 1024; // 只讀尾端 200KB，絕不整檔讀入（職能 2a／4 讀 transcript 用）

// ── gate-config 集中設定（【R】）──
// 啟動時讀 ~/.claude/hooks/gate-config.json；讀不到或壞掉 → 全部視為 deny
// （回退到現有行為，fail-closed）。
const CONFIG_PATH = path.join(process.env.HOME || '/Users/51mini', '.claude', 'hooks', 'gate-config.json');
function loadGateConfig() {
  try {
    const cfg = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    return (cfg && typeof cfg === 'object' && cfg.gates) ? cfg.gates : null;
  } catch { return null; }
}
const GATES = loadGateConfig() || {};
function gateMode(name, def) {
  const g = GATES[name];
  if (!g) return def;
  if (g.locked) return 'deny';   // locked：忽略 mode 覆寫，程式內強制
  return g.mode || def;
}

// ── deny 記錄迴路（【Q】）──
// 每一次 deny 都追加一行 JSONL 到 guard-state/deny-log.jsonl。
// 寫入失敗靜默略過（雷 #4：記錄是輔助，不能反過來擋工作）。
const DENY_LOG = path.join(GUARD_DIR, 'deny-log.jsonl');
function logDeny(hook, gate, tool, hit, snippet) {
  try {
    if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true, mode: 0o700 });
    fs.appendFileSync(DENY_LOG, JSON.stringify({
      ts: new Date().toISOString(),
      hook,
      gate: String(gate || 'PPN'),
      tool: String(tool || ''),
      hit: String(hit || '').slice(0, 120),
      snippet: (gate === 'SECRET')
        ? 'REDACTED'
        : String(snippet || '').split('\n')[0].trim().slice(0, 80),
    }) + '\n', { mode: 0o600 });
  } catch { /* 記錄失敗靜默略過（雷 #4） */ }
}

function readStdin() {
  return new Promise(resolve => {
    let data = '';
    if (process.stdin.isTTY) return resolve('');
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', c => { data += c; });
    process.stdin.on('end', () => { clearTimeout(timer); resolve(data); });
    // 1500ms 只是 fallback 上限；'end' 先到就 clearTimeout，
    // 否則這個 pending timer 會讓 process 多活 1.5s 才能真的結束
    // （原本的 bug：resolve() 提早呼叫了，但 timer 沒清，process 還是卡著）。
    const timer = setTimeout(() => resolve(data), 1500);
  });
}

function allow() {
  console.log(JSON.stringify({ continue: true, suppressOutput: true }));
}

function flagPath(sessionId, suffix) {
  return path.join(GUARD_DIR, suffix + '-' + sessionId + '.flag');
}

// 去重（2026-10-20）：fixindex-pretool.js 的 L1 查舊帳閘已啟動（本輪判定檢修）時，它會 deny 並附完整說明，
// 這裡的「尚未查舊帳」提醒就是同一句話講第二次，讓開。路徑規則照 fixindex-pretool.js L1 閘（6h 過期同步）。
function l1GateArmed(sessionId) {
  const dir = process.env.ROUTER_DIR || path.join(process.env.HOME || '/Users/51mini', '.claude', 'context-router');
  try {
    const st = fs.statSync(path.join(dir, 'l1-gate', String(sessionId).replace(/[^\w-]/g, '_')));
    return Date.now() - st.mtimeMs <= 6 * 3600e3;
  } catch { return false; }
}

// session → plan 路徑釘選檔。ExitPlanMode 當下寫入，後續同 session 的呼叫
// 優先讀這個，避免併行 session 用 mtime 猜到別人剛寫的 plan（fixindex 併行誤指問題）。
function pinPath(sessionId) {
  return path.join(GUARD_DIR, 'plan-' + sessionId + '.path');
}

// 讀「本 session 釘住的 plan 路徑」，新鮮度保護：路徑若已不存在視同無記錄。
// 讀不到才 fallback 到 resolvePlanMd() 的 mtime 猜測（標記 guessed:true，
// 呼叫端要在注入文字裡標「推測」，因為這仍可能撈到別的併行 session 的 plan）。
function resolvePlanForSession(sessionId) {
  try {
    const pinned = fs.readFileSync(pinPath(sessionId), 'utf8').trim();
    if (pinned && fs.existsSync(pinned)) return { full: pinned, guessed: false };
  } catch {}
  const guessed = resolvePlanMd();
  return guessed ? { full: guessed.full, guessed: true } : null;
}

function notice(msg, cap) {
  console.log(JSON.stringify({
    continue: true,
    suppressOutput: true,
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: String(msg).slice(0, cap || 400),
    },
  }));
}

// v4 advisory warn：記 warn-log + systemMessage，不 deny。
function warnFn(reason, gate, tool, hit) {
  try {
    if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true, mode: 0o700 });
    fs.appendFileSync(
      path.join(GUARD_DIR, 'warn-log.jsonl'),
      JSON.stringify({ ts: new Date().toISOString(), hook: 'ppn', gate: String(gate || 'PPN'),
        tool: String(tool || ''), hit: String(hit || '').slice(0, 120),
        snippet: String(reason || '').split('\n')[0].trim().slice(0, 80) }) + '\n',
      { mode: 0o600 });
  } catch {}
  console.log(JSON.stringify({
    continue: true,
    suppressOutput: true,
    systemMessage: '[HEADLESS-GATE] ' + String(reason).slice(0, 400) +
      '\n（advisory 模式：未阻斷。這是無頭設備，請依訊息指引調整。此閘不會重複攔。）',
  }));
}

// 從 plan 全文抽標題（首行 `# ` heading → 查詢語）。
function extractPlanTitle(planText) {
  const m = String(planText || '').match(/^#\s+(.+)$/m);
  return m ? m[1].trim().slice(0, 80) : '';
}

// 三點式掃雷的洞見層：plan 起點按標題查 insight 型條目，命中注入供承接。
// execFileSync 不過 shell，title 含引號/反引號無注入風險；fail-open 回 ''（保留既有提醒）。
function queryInsights(title) {
  if (!title) return '';
  try {
    const out = execFileSync('fixindex', ['insights', title, '--limit', '5'],
      { timeout: 4500, maxBuffer: 8 * 1024 * 1024, encoding: 'utf8',
        env: { ...process.env, FIXINDEX_SEMANTIC: '0' } });
    const s = String(out || '').trim();
    if (!s) return '';                          // 空輸出 = 沒命中
    if (/matched 0 sections|no insight entries|\(no entries\)|no entries/i.test(s)) return '';  // 未命中文字
    return s;
  } catch (e) {
    return '';  // fixindex 不在 / timeout / 非零 → 視同未命中
  }
}

// 踩雷當下排雷：hook 內直接查 fixindex。execFileSync 不過 shell，
// symptom 含引號/反引號也不會變成指令注入。fail-open 回空字串。
function fixindexFind(symptom) {
  try {
    // 實測 fixindex find 要 ~2.8s（2026-08-16），timeout 得留餘裕；
    // 此分支只在「同指紋已失敗、正要重試」時走到，延遲可接受。
    const out = execFileSync('fixindex', ['find', symptom], {
      timeout: 4500,
      stdio: ['pipe', 'pipe', 'pipe'],
      // 語意層載模型 ~2GB、>4.5s；逾時只殺 bash，python 孤兒照跑完（2026-10-22 當機）
      env: { ...process.env, FIXINDEX_SEMANTIC: '0' },
    });
    return out.toString().trim();
  } catch { return ''; }
}

// PreToolUse 硬攔截。notice() 只注入模型 context（使用者看不到、且正文已輸出完
// 才觸發，來不及補），所以路徑規則靠它等於零強制力 —— 改用 deny 讓模型被迫先講話。
// gate/tool/hit 供 deny-log 分類；SECRET 類 snippet 由 logDeny 內部 REDACT。
function deny(reason, gate, tool, hit) {
  logDeny('ppn', gate, tool, hit, reason);
  if (gate === 'HEADLESS') {
    // 【R】headless gate 支援 warn/off（顧問/純規劃 session 白名單）；
    // locked 由 gateMode 內部強制。warn 放行但出聲。
    const mode = gateMode('headless', 'deny');
    if (mode === 'off') {
      console.log(JSON.stringify({ continue: true, suppressOutput: true }));
      return;
    }
    if (mode === 'warn') {
      console.log(JSON.stringify({
        continue: true,
        suppressOutput: true,
        systemMessage: '[GUARD-warn] ' + String(reason).slice(0, 1200),
      }));
      return;
    }
  }
  console.log(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: String(reason).slice(0, 1200),
    },
  }));
}

// ── prior-art 檢索證據掃描（feedback_dispatch_policy.md §4 item 8(a)）──
// 只認 assistant 真的發出的 tool_use，不掃純文字——否則本 hook 自己 warn 訊息裡
// 的指令範例會造成假陽性。fail-open：讀不到／解析失敗回 null，呼叫端視同無法判定。
// wheel/registry.tsv：/wheel skill 收尾登記輪子卡的那道指令，等同查過。
const PRIOR_ART_CMD = /\bgh\s+search\b|\bnpm\s+(search|view)\b|\bbrew\s+search\b|\bpip\s+index\s+search\b|wheel\/registry\.tsv/;
const PRIOR_ART_TOOL = /^(WebSearch|WebFetch)$|context7|deepwiki/i;
// 「要拉新依賴」＝最典型的選輪子時刻。npm i 不帶套件名（還原 lockfile）不算。
const DEP_ADD_CMD = /\b(npm|pnpm|yarn|bun)\s+(i|install|add)\s+[^-\s]|\bpip3?\s+install\s+(?!-r\b|-e\b)[^-\s]|\buv\s+(add|pip\s+install)\s|\bbrew\s+install\s|\bcargo\s+add\s|\bgo\s+get\s/;
const WHEEL_HINT = '先跑 `/wheel`（三軸：官方文檔／社群共識／成熟輪子 → 輪子卡裁決）。自造是最後一格。';
function priorArtSeen(transcriptPath) {
  try {
    if (!transcriptPath || !fs.existsSync(transcriptPath)) return null;
    const st = fs.statSync(transcriptPath);
    const start = Math.max(0, st.size - TRANSCRIPT_TAIL_BYTES);
    const len = st.size - start;
    if (len <= 0) return null;
    const fd = fs.openSync(transcriptPath, 'r');
    const buf = Buffer.alloc(len);
    fs.readSync(fd, buf, 0, len, start);
    fs.closeSync(fd);
    for (const line of buf.toString('utf8').split('\n')) {
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      const content = obj && obj.message && obj.message.content;
      if (!Array.isArray(content)) continue;
      for (const c of content) {
        if (!c || c.type !== 'tool_use') continue;
        if (PRIOR_ART_TOOL.test(String(c.name || ''))) return true;
        if (c.name === 'Skill' && /^wheel$/.test(String((c.input && c.input.skill) || ''))) return true;
        const cmd = String((c.input && c.input.command) || '');
        if (cmd && PRIOR_ART_CMD.test(cmd)) return true;
      }
    }
    return false;
  } catch { return null; }
}

// 讀 transcript 尾端，取「最後一則 user message 之後」的所有 assistant text，
// 判斷本輪正文有沒有出現 needle（plan 絕對路徑）。
// fail-open：任何解析失敗回 null，呼叫端視同「無法判定」→ 放行。
function turnTextHas(transcriptPath, needle) {
  try {
    if (!transcriptPath || !needle) return null;
    const stat = fs.statSync(transcriptPath);
    const start = Math.max(0, stat.size - TRANSCRIPT_TAIL_BYTES);
    const fd = fs.openSync(transcriptPath, 'r');
    const buf = Buffer.alloc(stat.size - start);
    fs.readSync(fd, buf, 0, buf.length, start);
    fs.closeSync(fd);
    let text = buf.toString('utf8');
    if (start > 0) {
      const nl = text.indexOf('\n');
      text = nl >= 0 ? text.slice(nl + 1) : '';
    }
    const lines = text.split('\n').filter(Boolean);
    // 由尾往前掃，收集 assistant text，遇到第一則「真實 user 訊息」就停。
    // tool_result 也掛在 role:user 底下，要排除（content 全是 tool_result 的不算輪界）。
    const chunks = [];
    for (let i = lines.length - 1; i >= 0; i--) {
      let obj;
      try { obj = JSON.parse(lines[i]); } catch { continue; }
      const msg = obj && obj.message;
      if (!msg || !Array.isArray(msg.content)) continue;
      if (msg.role === 'user') {
        const isToolResultOnly = msg.content.every(
          c => c && typeof c === 'object' && c.type === 'tool_result');
        if (!isToolResultOnly) break;   // 真的輪界
        continue;
      }
      if (msg.role !== 'assistant') continue;
      for (const c of msg.content) {
        if (c && c.type === 'text' && typeof c.text === 'string') chunks.push(c.text);
      }
    }
    if (!chunks.length) return false;
    return chunks.join('\n').includes(needle);
  } catch { return null; }
}

function resolvePlanMd() {
  try {
    const files = fs.readdirSync(PLANS_DIR);
    const md = files.filter(f => f.endsWith('.md'))
      .map(f => ({ name: f, full: path.join(PLANS_DIR, f), mtime: fs.statSync(path.join(PLANS_DIR, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime);
    return md[0] || null;
  } catch { return null; }
}

// ── 第五職能：headless artifact gate ──
// 無頭設備防呆閘門：產出的 plan / 工單 / 交付文件不得含手動操作步驟。
// 觸發：Write/Edit/ExitPlanMode 且目標在 ~/.claude/plans/ 下（或 ExitPlanMode）。
// 命中 pattern 即 deny；含逃生標記的行跳過。fail-open：任何錯誤回 null → 放行。
const HEADLESS_PATTERNS = [
  { re: /WebUI|Web UI|網頁介面|瀏覽器(開|打開|前往)/i, why: '指引 WebUI / 瀏覽器' },
  { re: /Settings\s*→|設定\s*→.*(頁|面板|分頁)/i, why: 'UI 導覽路徑' },
  { re: /(請|麻煩|需要)(你|使用者|用戶)?.{0,12}(手動|自行|親自)/i, why: '明示手動' },
  { re: /(在|到)終端.{0,8}(執行|輸入|貼上|下)/i, why: '要人下指令' },
  { re: /(請|麻煩).{0,10}(貼上|填入|點(選|擊)|勾選)/i, why: '要人操作' },
  { re: /在\s*Telegram\s*(私訊|對|送)/i, why: '要人發訊息' },
];
const HEADLESS_GATE_REVIEW_MARK = '<!-- headless-gate: reviewed -->';
// 【N】否定句：命中位置前 20 字內出現否定詞 → 該行跳過（描述約束不是下指示）。
const NEGATION_RE = /無法|不能|禁止|不得|不准|沒有人|不會/;
// 【N】引用/描述行：行首 blockquote，或行內含規則/測資字樣 → 在描述不是指示。
const DESCRIBE_RE = /\bre:|regex|pattern|fixture|測試資料|rule|規則/i;

function collectWriteText(payload) {
  // 依工具抓「待寫入內容」：Write→content；Edit→new_string；ExitPlanMode→plan。
  const ti = payload.tool_input || {};
  if (payload.tool_name === 'Write') return String(ti.content || '');
  if (payload.tool_name === 'Edit') return String(ti.new_string || '');
  if (payload.tool_name === 'ExitPlanMode') return String(ti.plan || '');
  return '';
}

function headlessArtifactGate(payload) {
  try {
    const tool = payload.tool_name || payload.toolName || '';
    if (tool !== 'Write' && tool !== 'Edit' && tool !== 'ExitPlanMode') return false;
    // 只在 plans 目錄內掃（ExitPlanMode 無目錄語義，一律掃）。
    if (tool !== 'ExitPlanMode') {
      const fp = (payload.tool_input || {}).file_path ||
                 (payload.tool_input || {}).filePath || '';
      if (!fp.startsWith(PLANS_DIR + path.sep)) return false;
    }
    const text = collectWriteText(payload);
    if (!text) return false;    // 無待寫內容 → 放行
    const lines = text.split('\n');
    let hit = null;
    let inFence = false;       // 【N】三反引號 fence 狀態機
    for (let i = 0; i < lines.length && !hit; i++) {
      const line = lines[i];
      if (line.includes(HEADLESS_GATE_REVIEW_MARK)) continue;   // 逃生門
      // 【N】fence 開關：```` 切換狀態；fence 內的行是引用（指令/regex 原文），跳過。
      const fenceTicks = line.match(/```+/g);
      if (fenceTicks && fenceTicks.length % 2 === 1) inFence = !inFence;
      if (inFence) continue;
      // 【N】引用/描述行排除：blockquote 或規則/測資字樣。
      if (/^\s*>/.test(line) || DESCRIBE_RE.test(line)) continue;
      for (const p of HEADLESS_PATTERNS) {
        const m = line.match(p.re);
        if (!m) continue;
        // 【N】否定句排除：命中位置前 20 字內有否定詞 → 描述約束，跳過。
        const before = line.slice(Math.max(0, m.index - 20), m.index);
        if (NEGATION_RE.test(before)) continue;
        hit = { line: line.trim().slice(0, 80), why: p.why, pattern: p.re.source }; break;
      }
    }
    if (!hit) return false;
    const msg = '[HEADLESS-GATE] 攔截：工單/計畫內含手動操作要求。\n' +
      '命中：' + hit.why + ' → "' + hit.line + '"\n' +
      '這是無頭設備，沒有 GUI，使用者無法在終端執行任何指令。\n' +
      '改法：找對應的 HTTP API / CLI / 檔案寫入路徑取代。\n' +
      '若該步驟真的只能由人完成（例：Telegram 對 bot 發訊息以建立 owner 綁定），\n' +
      '必須顯式標記為 optional 並提供自動化的替代驗證方式，然後在該行加上\n' +
      '`<!-- headless-gate: reviewed -->` 才放行。';
    warnFn(msg, 'HEADLESS', tool, hit.why);   // v4 advisory：記 warn-log + 警示不阻斷
    return true;               // 主流程據此停止，不再落入後續職能
  } catch { return false; }   // fail-open
}

// ── 第六職能：plan 檔覆寫自動備份（【V3】git 快照取代 .bak；git 失敗退回 .bak）──
// Write 目標在 PLANS 目錄下、目標檔已存在、且本 session 尚未寫過該檔 → 先 git add+commit
// 自動快照再放行。放行（不 deny、不打斷），只回 systemMessage。PLANS/ 已是 git repo
// （baseline fd32280，v2.1 V3）：git -C ~/.claude/plans add <該檔> && commit。git 失敗
// → 退回舊 .bak 路徑（401–435 舊碼保留當 fallback）+ 警告。不設 remote、不 push。
function planBackupGate(payload, sid) {
  try {
    const tool = payload.tool_name || payload.toolName || '';
    if (tool !== 'Write') return false;
    const fp = (payload.tool_input || {}).file_path ||
               (payload.tool_input || {}).filePath || '';
    // 只處理 PLANS 目錄下的檔（含子目錄，但 backups/ 本身不受理——.bak.md 已存在會無限快照）
    if (!fp.startsWith(PLANS_DIR + path.sep) || fp.includes(path.sep + 'backups' + path.sep)) return false;
    if (fp === pinPath(sid)) return false;   // 不備份 guard-state 釘選檔
    if (!fs.existsSync(fp)) return false;    // 新檔無需快照
    // 本 session 是否已寫過該檔：用釘選檔機制（session→plan）判斷
    const pinned = (() => { try { return fs.readFileSync(pinPath(sid), 'utf8').trim(); } catch { return ''; } })();
    if (pinned === fp) return false;         // 已釘選=本 session 已見 → 不再快照，避免連鎖
    const base = path.basename(fp, '.md');
    const rel = path.relative(PLANS_DIR, fp);
    const gitAdd = spawnSync('git', ['-C', PLANS_DIR, 'add', '--', rel], { encoding: 'utf8', timeout: 10000 });
    const gitCommit = spawnSync('git', ['-C', PLANS_DIR, 'commit', '-m', `auto: pre-overwrite ${base}`],
                                { encoding: 'utf8', timeout: 10000 });
    const m = gitCommit.stdout ? gitCommit.stdout.match(/\[([^\]]+)\]/ ) : null;
    if (m && m[1]) {
      console.log(JSON.stringify({
        continue: true,
        suppressOutput: true,
        systemMessage: `[PLAN-GIT] 已快照 ${base} @ ${m[1]}`,
      }));
      return true;
    }
    // git commit 失敗（非 repo/非 tracked/權限）→ 退回 .bak（v1 舊職）+ 警告
    const bakDir = path.join(PLANS_DIR, 'backups');
    if (!fs.existsSync(bakDir)) fs.mkdirSync(bakDir, { recursive: true });
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
    const bakPath = path.join(bakDir, `${base}.${stamp}.bak.md`);
    fs.copyFileSync(fp, bakPath);
    // 同名備份保留 5 份：刪最舊（按檔名 stamp 排序）
    const same = fs.readdirSync(bakDir).filter(f => f.startsWith(base + '.') && f.endsWith('.bak.md')).sort();
    while (same.length > 5) {
      const old = same.shift();
      try { fs.unlinkSync(path.join(bakDir, old)); } catch {}
    }
    console.log(JSON.stringify({
      continue: true,
      suppressOutput: true,
      systemMessage: `[PLAN-GIT] git 快照失敗，退回 .bak：${bakPath}`,
    }));
    return true;
  } catch { return false; }   // 快照失敗靜默略過（不擋工作）
}

async function main() {
  try {
    const raw = await readStdin();
    const payload = raw ? JSON.parse(raw) : {};
    const tool = payload.tool_name || payload.toolName || '';
    const sid = payload.session_id || payload.sessionId || 'default';

    // ── 第五職能：headless artifact gate（無頭設備防呆；fail-open）──
    if (headlessArtifactGate(payload)) return;

    // ── 第六職能：plan 檔覆蓋自動備份（【P】；Write 到 PLANS 下已存在檔）──
    if (planBackupGate(payload, sid)) return;

    // ── 職能 1：ExitPlanMode → plan 路徑注入 ──
    if (tool === 'ExitPlanMode') {
      // 優先信任 tool_input.planFilePath（ExitPlanMode 呼叫本身帶的欄位，
      // 不受併行 session 影響）；探測發現實際 key 是 planFilePath，值即完整路徑。
      // 只有這欄位缺失或指向不存在的檔時，才退回 mtime 猜測（可能撈錯併行 session 的 plan）。
      const inputPath = (payload.tool_input && payload.tool_input.planFilePath) || '';
      let planFull = '';
      if (inputPath && fs.existsSync(inputPath)) {
        planFull = inputPath;
      } else {
        const guessed = resolvePlanMd();
        if (guessed) planFull = guessed.full;
      }
      if (!planFull) return allow();

      try {
        if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
        fs.writeFileSync(pinPath(sid), planFull);
      } catch {}

      // 三點式第 1 點：plan 起點域級掃雷。session 還沒查過舊帳 → 提醒一次
      // （對 plan 主題 + 涉及工具鏈各做一次 fixindex find；執行期踩雷另有第 2 點兜底）。
      let ranBefore = false;
      try { fs.accessSync(flagPath(sid, 'fixindex-ran')); ranBefore = true; } catch {}
      const domainHint = ranBefore ? '' :
        '。另：本 session 未偵測到 fixindex find／mem-search——執行前先對 plan 主題與涉及工具鏈做一次域級 fixindex find（靜態掃雷，只此一次），' +
        '並預判執行期高機率踩雷點（外部服務、權限、timeout、stale state 類），對可預見的症狀關鍵字順帶各查一次';
      // 三點式掃雷的洞見層：plan 標題 → fixindex insights 提取（命中注入、未命中/錯誤保留提醒）
      let planText = '';
      try { planText = fs.readFileSync(planFull, 'utf8'); } catch {}
      const insightHits = queryInsights(extractPlanTitle(planText));
      const insightLine = insightHits
        ? '\n\n[fixindex insights 命中] 依 plan 主題提取到的已固化洞見（承接時保留本 session 外的設計決策）：\n```\n' + insightHits + '\n```'
        : '';
      // ── v4 advisory：本輪正文沒出現 plan 絕對路徑就提醒（不 deny、不數次）──
      // 2a：plan 起點域級 find 代跑。同指令內把「insight 提示」與「find 命中」合併注入；
      // 命中也立 fixindex-ran flag（與職能 2 同機制），避免職能 4 事後重複提醒。
      const planFindHits = fixindexFind(extractPlanTitle(planText) || planFull);
      const planFindLine = planFindHits
        ? '\n\n[fixindex find 命中] 依 plan 主題查到的修理舊帳（承接前保留已修/未修決策）：\n```\n' + planFindHits.slice(0, 450) + '\n```'
        : '';
      if (planFindHits) {
        try {
          if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
          fs.writeFileSync(flagPath(sid, 'fixindex-ran'), new Date().toISOString());
        } catch {}
      }
      const has = turnTextHas(payload.transcript_path || payload.transcriptPath, planFull);
      if (has === false) {
        return notice(
          '本輪正文未出現計畫檔絕對路徑。\n' +
          '在本回合最終回覆的結尾附上這一行（原樣複製，不要改寫、不要只寫檔名）：\n\n' +
          '計畫檔：' + planFull + '\n\n' +
          '（使用者是無頭設備，路徑只在聊天視窗可見才有用；工具呼叫之間的文字、' +
          'md 內文、UI 呈現都不保證可見。）',
          1600
        );
      }

      // ── 輪子決定行檢查：coding plan（含驗收/verify 段）必須帶「輪子：」決定行 ──
      // 規則全文見 feedback_dispatch_policy.md §4 item 8(a)。
      // 2026-09-23：notice() → warnFn()。fixindex 0442§6 已自證 notice 等於零強制力
      //（只灌 additionalContext、使用者看不到、ExitPlanMode 觸發時正文已輸出完無補寫
      // 機會）；同檔 PONYTAIL 條 2026-08-30 就因此換成 warnFn，輪子條當時漏改。
      const isCodingPlan = /##\s*驗收|\bverify\b/i.test(planText);
      const hasWheel = /輪子[：:]/.test(planText);
      if (isCodingPlan && !hasWheel) {
        return warnFn(
          'coding plan 缺「輪子：」決定行。\n' +
          WHEEL_HINT + '\n' +
          '在 plan 檔加一行「輪子：<裁決> <來源>」（裁決：不做／換題／設定／採用／改用／借鏡／自造），trivial 寫「輪子：不適用（原因）」。',
          'WHEEL', 'ExitPlanMode', 'plan-missing-wheel'
        );
      }
      // 宣告≠生效（feedback_declaration_vs_effect）：「輪子：」行寫了，但整個 session
      // 一次真實檢索都沒有 → 那行是空頭支票，出聲。「不適用」是 8(a) 的 trivial 豁免；
      // priorArtSeen 回 null（無法判定）時放行，只有明確回 false 才 warn。
      if (isCodingPlan && hasWheel && !/輪子[：:]\s*不適用/.test(planText) &&
          priorArtSeen(payload.transcript_path || payload.transcriptPath) === false) {
        return warnFn(
          '「輪子：」行有寫，但本 session 沒有任何一次 prior-art 檢索的實際工具呼叫。\n' +
          '先實跑再下結論：' + WHEEL_HINT + '\n' +
          '真的是 trivial 單行改動 → 改寫成「輪子：不適用（原因）」即符合 8(a) 豁免。',
          'WHEEL', 'ExitPlanMode', 'plan-wheel-unverified'
        );
      }

      // 借鏡 github/spec-kit（138k★）Phase 0 的 research.md 契約：prior-art 的結論要留
      // 可複查的證據。spec-kit 另產一份 research.md 並用 check_file 驗存在；我們不新增
      // 檔案類型，改把 provenance 塞進既有那一行——沒來源的「採用 X」是不可複查的斷言。
      // ponytail: 只驗來源 token 在不在，不驗連結活著；驗活要網路 I/O，hook 不該做。
      if (isCodingPlan && hasWheel && !/輪子[：:]\s*不適用/.test(planText)) {
        const wheelLine = (planText.match(/^.*輪子[：:].*$/m) || [''])[0];
        const hasSource = /https?:\/\/|[\w.-]+\/[\w.-]+|官方文件|官方文檔|release\s*notes|README/i.test(wheelLine);
        if (!hasSource) {
          return warnFn(
            '「輪子：」行沒帶來源，只有結論。\n' +
            '加上可複查的出處（擇一）：repo `owner/name`、文件 URL、或「官方文件」字樣。\n' +
            '例：「輪子：借鏡 github/spec-kit 的 Phase 0 research.md 契約，不照搬整條工作流」。',
            'WHEEL', 'ExitPlanMode', 'plan-wheel-no-source'
          );
        }
      }

      // ── Ponytail 閘門檢查：coding plan 必須自報 PONYTAIL 判定 ──
      // 規則全文見 /Users/51mini/.openclaw/workspace/skills/planner-discipline/SKILL.md。
      // ponytail plugin 沒有 CLI，拿不到可程式化的 PASS/FAIL，此處只做字串存在性檢查
      // ——「有沒有自報」可驗，「自報得對不對」不可驗，後者留給模型。
      // ponytail: 不做 deny 計數逃生閥。缺這行的補救成本是「加一行字」，鎖死風險低；
      //           真的誤擋到再加計數器（照 headless gate 的 gateMode 模式）。
      const hasPonytail = /PONYTAIL[：:]\s*(PASS|FAIL|N\/A)/i.test(planText);
      if (isCodingPlan && !hasPonytail) {
        // 2026-08-30 降級：原本 deny。改用既有的 warnFn()（v4 advisory warn：
        // systemMessage 使用者看得到 + 寫 warn-log），不用檔頭已自陳「等於零強制力」
        // 的 notice()（只灌 additionalContext，使用者看不到且正文已輸出完才觸發）。
        return warnFn(
          'plan 缺 Ponytail 閘門判定。\n' +
          '在 ' + planFull + ' 末尾加一段：\n\n' +
          '## PONYTAIL 精簡閘門\n' +
          'PONYTAIL: PASS\n' +
          '- 砍了什麼：<投機性/未被要求的內容>\n' +
          '- 為何這是最低階可行方案：<一行>\n\n' +
          '（判定值限 PASS／FAIL／N/A。寫完再呼叫 ExitPlanMode。）',
          'PONYTAIL', 'ExitPlanMode', 'plan-missing-ponytail'
        );
      }
      return notice('本輪回覆必須在對話正文寫出：計畫檔：' + planFull + domainHint + insightLine + planFindLine, 1600);
    }

    // ── 職能 2：Bash → fixindex 偵測（連續失敗已於 2026-10-20 移到 fixindex-pretool.js）──
    if (tool === 'Bash') {
      const cmd = String((payload.tool_input || {}).command || '');

      // fixindex / mem-search detection（不變）
      if (/\bfixindex\s+find\b/.test(cmd) || /\bmem-search\b/.test(cmd) || /\bclaude-mem\s+search\b/.test(cmd)) {
        try {
          if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
          fs.writeFileSync(flagPath(sid, 'fixindex-ran'), new Date().toISOString());
        } catch {}
      }

      // ── 2a：拉新依賴前沒查輪子 → 提醒一次（與 Edit/Write 的 4a 共用 flag，一 session 最多一次）──
      if (DEP_ADD_CMD.test(cmd)) {
        const paFlag = flagPath(sid, 'prior-art-reminded');
        let paDone = false;
        try { fs.accessSync(paFlag); paDone = true; } catch {}
        if (!paDone && priorArtSeen(payload.transcript_path || payload.transcriptPath) === false) {
          try {
            if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
            fs.writeFileSync(paFlag, new Date().toISOString());
          } catch {}
          return warnFn('要裝新依賴，但本 session 沒查過輪子。\n' + WHEEL_HINT, 'WHEEL', 'Bash', 'dep-add-no-prior-art');
        }
      }

      // ── 2b：Bash 寫入型指令偵測（sed -i / tee / heredoc / 重導向至非 tmp / python3 -c open w）──
      // 慣例約定已降 advisory（fi-reminder），此提醒協助未先查舊帳的 session；
      // 與職能 4 複用同一 flag，避免重複轟炸。只提醒一次，不 deny。噪訊上限 1 次/session。
      {
        const writeish = /\b(sed\s+-i\b|tee\b)/.test(cmd) ||
          /<<\s*['"]?[A-Z_]+/.test(cmd) ||
          /(?:^|[^[:alnum:]_])(>|>>)\s*(?!\/tmp\/|\/dev\/|\${TMP)/.test(cmd) ||
          /python3?\s+-c\s+['"][^'"]*open\([^)]*,\s*['"]w/.test(cmd);
        if (writeish) {
          const ranFlag = flagPath(sid, 'fixindex-ran');
          const remindedFlag = flagPath(sid, 'fixindex-reminded');
          let ran = false, reminded = false;
          try { fs.accessSync(ranFlag); ran = true; } catch {}
          try { fs.accessSync(remindedFlag); reminded = true; } catch {}
          if (!ran && !reminded && !l1GateArmed(sid)) {
            try {
              if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
              fs.writeFileSync(remindedFlag, new Date().toISOString());
            } catch {}
            return notice('本 session 尚未偵測到 fixindex find / mem-search。開發或除錯任務請先雙軸並行查舊帳再動手。');
          }
        }
      }

      // ── plan 路徑一次性延續提醒：同 session 執行階段的第一道 Bash，
      // 用釘住值（優先）或 mtime 猜測（fallback，標「推測」）提醒目前對應哪個 plan。
      // 只發一次（用 flag 節流），避免每道指令都塞 additionalContext。
      const planEchoFlag = flagPath(sid, 'plan-echoed');
      let planEchoed = false;
      try { fs.accessSync(planEchoFlag); planEchoed = true; } catch {}
      if (!planEchoed) {
        const planInfo = resolvePlanForSession(sid);
        if (planInfo) {
          try {
            if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
            fs.writeFileSync(planEchoFlag, new Date().toISOString());
          } catch {}
          if (planInfo.guessed) return allow();   // 沒釘住的 plan 不猜（2026-09-22：30 天 46 次純噪音）
          return notice('本 session 計畫檔：' + planInfo.full);
        }
      }

      return allow();
    }

    // ── 職能 4：Edit|Write → true fixindex check（不變）──
    if (tool === 'Edit' || tool === 'Write') {
      // 4a. prior-art 軸（2026-09-29 新增）。查舊帳（fixindex）只涵蓋自家歷史，
      // 「外面有沒有現成做法」是另一軸——實測本軸缺席時直接自造（fix-RN 任務檔：
      // 拿自家 0113 就開始寫修法，沒查 React 官方文檔、沒查上游 issue／有無現成修法）。
      // 對稱於 plan mode 的 WHEEL 條（:588），差別只在這邊掛 PreToolUse、那邊掛 ExitPlanMode。
      // priorArtSeen 回 null（無法判定）時放行，只有明確回 false 才出聲。
      const paFlag = flagPath(sid, 'prior-art-reminded');
      let paDone = false;
      try { fs.accessSync(paFlag); paDone = true; } catch {}
      if (!paDone && priorArtSeen(payload.transcript_path || payload.transcriptPath) === false) {
        try {
          if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
          fs.writeFileSync(paFlag, new Date().toISOString());
        } catch {}
        return warnFn(
          '本 session 尚未偵測到 prior-art 檢索——查舊帳（fixindex）不等於查輪子。\n' + WHEEL_HINT,
          'WHEEL', tool, 'no-prior-art'
        );
      }

      const ranFlag = flagPath(sid, 'fixindex-ran');
      const remindedFlag = flagPath(sid, 'fixindex-reminded');

      let ran = false;
      try { fs.accessSync(ranFlag); ran = true; } catch {}

      if (ran || l1GateArmed(sid)) return allow();

      let reminded = false;
      try { fs.accessSync(remindedFlag); reminded = true; } catch {}
      if (reminded) return allow();

      try {
        if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
        fs.writeFileSync(remindedFlag, new Date().toISOString());
      } catch {}

      return notice('本 session 尚未偵測到 fixindex find / mem-search。開發或除錯任務請先雙軸並行查舊帳再動手。');
    }

    allow();
  } catch { allow(); }
}

main();
