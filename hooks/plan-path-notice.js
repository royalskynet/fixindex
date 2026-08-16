#!/usr/bin/env node
/* PreToolUse hook — 四職能（Phase 8 fail-counter 換載體；Phase 9 三點式 fixindex loop）：
 *   1. ExitPlanMode → 注入「計畫檔：<完整路徑>」；session 沒查過舊帳時
 *      加一句域級 find 提醒（三點式第 1 點：plan 起點靜態掃雷，一次性）
 *   2. Bash    → 偵測 fixindex find / mem-search，建 ran flag
 *   3. Bash    → 連續失敗計數（讀 transcript 推算上一道 Bash 是否失敗）；
 *      count ≥1 且 <閾值 → 踩雷當下動態排雷：hook 內直接跑 fixindex find
 *      <上次失敗 symptom>，命中注入條目、未命中注入指示（三點式第 2 點）；
 *      count ≥閾值 → 停損注入（不變）
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
const { execFileSync } = require('child_process');

const PLANS_DIR = path.join(process.env.HOME || '/Users/51mini', '.claude', 'plans');
const GUARD_DIR = path.join(process.env.HOME || '/Users/51mini', '.claude', 'guard-state');
const FAIL_THRESHOLD = 2;
const TRANSCRIPT_TAIL_BYTES = 200 * 1024; // 只讀尾端 200KB，絕不整檔讀入

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
      { timeout: 4500, maxBuffer: 8 * 1024 * 1024, encoding: 'utf8' });
    const s = String(out || '').trim();
    if (!s) return '';                          // 空輸出 = 沒命中
    if (/matched 0 sections|no insight entries|\(no entries\)|no entries/i.test(s)) return '';  // 未命中文字
    return s;
  } catch (e) {
    return '';  // fixindex 不在 / timeout / 非零 → 視同未命中
  }
}

// 從 tool_result 錯誤文字抽 symptom 短語（併自死碼 fixindex-hint.js，
// 該檔從未掛進 settings.json 且 PostToolUse 在 Bash 非零退出時不觸發）。
function extractSymptom(text) {
  const s = String(text || '');
  let m = s.match(/(?:ERROR|Error|错误|錯誤|失敗|fatal)[:\s]+(.+)/i);
  if (m) return m[1].trim().slice(0, 80);
  m = s.match(/exit code:?\s*(\d+)/i);
  if (m) return 'exit code ' + m[1];
  return s.trim().slice(0, 80).replace(/\n/g, ' ');
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
      env: process.env,
    });
    return out.toString().trim();
  } catch { return ''; }
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

// 指紋規則：第一個 word 當底；第二層看非 flag 參數個數——
// ≥2 個非 flag 參數（如「gh api xxx」的 api/xxx）視為「子命令 + 資源」，
// 用第二個非 flag 參數（資源本身）分流，讓 gh api xxx / gh api yyy 算不同解法；
// 剛好 1 個非 flag 參數（如「node a.js」「ls /path」）視為單一目標，
// 目標本身不分流，讓 node a.js / node b.js 算同一類重試。
function fingerprint(cmd) {
  const trimmed = String(cmd || '').trim();
  if (!trimmed) return '';
  const tokens = trimmed.split(/\s+/);
  const head = tokens[0] || '';
  const nonFlag = tokens.slice(1).filter(t => t && !t.startsWith('-'));
  let tail = '';
  if (nonFlag.length >= 2) tail = path.basename(nonFlag[1]);
  const fp = (head + '_' + tail).replace(/[^a-zA-Z0-9_.-]/g, '').slice(0, 64);
  return fp;
}

// 只讀 transcript 尾端固定量，解析出「最後一筆 Bash tool_result」
// （含對應的原始指令與 is_error）。fail-open：任何錯誤回 null。
function findLastBashResult(transcriptPath) {
  try {
    const stat = fs.statSync(transcriptPath);
    const start = Math.max(0, stat.size - TRANSCRIPT_TAIL_BYTES);
    const fd = fs.openSync(transcriptPath, 'r');
    const len = stat.size - start;
    const buf = Buffer.alloc(len);
    fs.readSync(fd, buf, 0, len, start);
    fs.closeSync(fd);
    let text = buf.toString('utf8');
    if (start > 0) {
      const nl = text.indexOf('\n');
      text = nl >= 0 ? text.slice(nl + 1) : '';
    }
    const lines = text.split('\n');
    const MAX_LINES = 4000; // 處理上限，避免極端情況吃滿 CPU
    const slice = lines.length > MAX_LINES ? lines.slice(lines.length - MAX_LINES) : lines;

    const toolUseCmd = {};
    let last = null;
    for (const line of slice) {
      if (!line) continue;
      let obj;
      try { obj = JSON.parse(line); } catch { continue; }
      const content = obj && obj.message && obj.message.content;
      if (!Array.isArray(content)) continue;
      for (const item of content) {
        if (!item || typeof item !== 'object') continue;
        if (item.type === 'tool_use' && item.name === 'Bash' && item.id) {
          toolUseCmd[item.id] = (item.input && item.input.command) || '';
        } else if (item.type === 'tool_result' && item.tool_use_id &&
                   Object.prototype.hasOwnProperty.call(toolUseCmd, item.tool_use_id)) {
          let errText = '';
          if (item.is_error) {
            const c = item.content;
            if (typeof c === 'string') errText = c;
            else if (Array.isArray(c)) {
              errText = c.filter(p => p && p.type === 'text' && p.text)
                         .map(p => p.text).join('\n');
            }
            errText = errText.slice(0, 400);
          }
          last = { id: item.tool_use_id, cmd: toolUseCmd[item.tool_use_id], isError: !!item.is_error, errText };
        }
      }
    }
    return last;
  } catch { return null; }
}

async function main() {
  try {
    const raw = await readStdin();
    const payload = raw ? JSON.parse(raw) : {};
    const tool = payload.tool_name || payload.toolName || '';
    const sid = payload.session_id || payload.sessionId || 'default';

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
      return notice('本輪回覆必須在對話正文寫出：計畫檔：' + planFull + domainHint + insightLine, 1600);
    }

    // ── 職能 2+3：Bash → fixindex 偵測 + 連續失敗計數/停損注入 ──
    if (tool === 'Bash') {
      const cmd = String((payload.tool_input || {}).command || '');

      // fixindex / mem-search detection（不變）
      if (/\bfixindex\s+find\b/.test(cmd) || /\bmem-search\b/.test(cmd) || /\bclaude-mem\s+search\b/.test(cmd)) {
        try {
          if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
          fs.writeFileSync(flagPath(sid, 'fixindex-ran'), new Date().toISOString());
        } catch {}
      }

      // ── 用 transcript 推算「上一道 Bash」成敗，更新計數（fail-open） ──
      try {
        if (!fs.existsSync(GUARD_DIR)) fs.mkdirSync(GUARD_DIR, { recursive: true });
        const transcriptPath = payload.transcript_path || payload.transcriptPath || '';
        if (transcriptPath && fs.existsSync(transcriptPath)) {
          const lastResult = findLastBashResult(transcriptPath);
          if (lastResult) {
            const lastIdFile = flagPath(sid, 'fail-lastid');
            let prevProcessed = '';
            try { prevProcessed = fs.readFileSync(lastIdFile, 'utf8').trim(); } catch {}
            if (lastResult.id !== prevProcessed) {
              fs.writeFileSync(lastIdFile, lastResult.id);
              const lastFp = fingerprint(lastResult.cmd);
              if (lastFp) {
                const counterPath = path.join(GUARD_DIR, 'fail-' + lastFp + '-' + sid + '.count');
                const symptomPath = path.join(GUARD_DIR, 'fail-' + lastFp + '-' + sid + '.symptom');
                if (lastResult.isError) {
                  let c = 0;
                  try { c = parseInt(fs.readFileSync(counterPath, 'utf8'), 10) || 0; } catch {}
                  fs.writeFileSync(counterPath, String(c + 1));
                  // 順存 symptom 供「重試前排雷」分支查 fixindex 用
                  const sym = extractSymptom(lastResult.errText || lastResult.cmd);
                  if (sym) { try { fs.writeFileSync(symptomPath, sym); } catch {} }
                } else {
                  // 同指紋成功一次 → 歸零
                  try { fs.unlinkSync(counterPath); } catch {}
                  try { fs.unlinkSync(symptomPath); } catch {}
                }
              }
            }
          }
        }
      } catch {}

      // ── 檢查「即將執行」這道指令的指紋是否已達停損閾值 ──
      const fp = fingerprint(cmd);
      if (fp) {
        const counterPath = path.join(GUARD_DIR, 'fail-' + fp + '-' + sid + '.count');
        let count = 0;
        try { count = parseInt(fs.readFileSync(counterPath, 'utf8'), 10) || 0; } catch {}
        if (count >= FAIL_THRESHOLD) {
          return notice(
            '指紋「' + fp + '」已連續失敗 ' + count + ' 次。依 CLAUDE.md 非模型反事實閘門：' +
            '未定位根因的盲試 2 次即停——停止重試同解法，重述假設、列至少 3 個可證偽替代解釋' +
            '（protocol / transport / routing / tool 或 session lifecycle / stale state / 權限 / 依賴），' +
            '給最小安全下一步 probe。'
          );
        }
        // ── 三點式第 2 點：踩雷當下動態排雷。同指紋已失敗 ≥1 次（未達停損），
        // 重試前 hook 內直接查 fixindex，把舊帳塞進 context 再讓模型決定往哪繞。
        if (count >= 1) {
          let sym = '';
          try { sym = fs.readFileSync(path.join(GUARD_DIR, 'fail-' + fp + '-' + sid + '.symptom'), 'utf8').trim(); } catch {}
          if (sym) {
            const hits = fixindexFind(sym);
            if (hits) {
              return notice('此指紋上次失敗（' + sym.slice(0, 60) + '）。fixindex 命中：\n' +
                hits.slice(0, 450) + '\n先看修理日誌再決定重試或繞路。', 600);
            }
            return notice('此指紋上次失敗（' + sym.slice(0, 60) + '），fixindex 無命中。' +
              '重試前想清楚這次哪裡不同；無新假設就別原樣重跑。');
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
          const suffix = planInfo.guessed ? '（推測，本 session 未記錄 plan）' : '';
          return notice('本 session 計畫檔：' + planInfo.full + suffix);
        }
      }

      return allow();
    }

    // ── 職能 4：Edit|Write → true fixindex check（不變）──
    if (tool === 'Edit' || tool === 'Write') {
      const ranFlag = flagPath(sid, 'fixindex-ran');
      const remindedFlag = flagPath(sid, 'fixindex-reminded');

      let ran = false;
      try { fs.accessSync(ranFlag); ran = true; } catch {}

      if (ran) return allow();

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
