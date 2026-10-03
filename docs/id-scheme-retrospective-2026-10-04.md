# ID 編碼歷程：9999 溢位、一個被撤回的補空號方案，與 adr-tools 的收斂

日期: 2026-10-04
主題: fixindex 條目 ID 怎麼配號、9999 之後怎麼辦
狀態: 已落地並驗收（fixindex `3aaea39`、beacon-harness `f76a903`）

---

## 1. 問題：第 9999 號之後，每筆新條目都拿到 10000

2026-10-03 連續寫入兩筆，兩筆都被配成 `10000-*.md`。`fixindex show 10000` 只回第一筆。

根因有兩層：

| 層 | 寫法 | 後果 |
|---|---|---|
| 配號 | `sorted(glob)[-1][:4]` + 1 | 字典序 `'9999-…' > '10000-…'`，max 永遠是 9999，每次都配 10000 |
| 解析 | `[:4]`、`\d{4}`、`[0-9][0-9][0-9][0-9]-*.md`，約 35 處 | 10000 被截成 `1000`，跟既有的 `1000-stale-hook-*` 混在一起 |

外部消費端也有一處：beacon-harness `fix2beacon.py` 的 `re.match(r"^(\d{4})-")` 遇到 5 位數會回 None，直接崩潰。

為什麼會這麼早滿：編號從 1010 直接跳到 9190（2026-09-16），之後一路 max+1。全庫只有 1735 筆，卻用到了 9999。

---

## 2. 第一個修法：補空號 —— 一輪後撤回

第一版的想法是「不碰 35 處解析，配號滿了就從 1000 起補空號」。這版測試通過，也上線了（`e8ca3d6`）。

下一輪過 `/wheel` 時撤回，原因有兩個：

- **編號不再照時間順序。** 1013 會比 9999 新。人看 `fix 1013` 會以為是舊帳。
- **多機撞號機率沒有變低。** 兩台機器各自 pull 之後，會搶同一個最小空號。這跟 max+1 一樣糟，而且還多了一種排序上的錯覺。

**教訓：** 「不動解析層」看起來是 diff 最小的做法，但它把成本轉嫁成語義錯亂。最短的 diff 不一定是最便宜的修法。

---

## 3. prior-art：三種做法

| 做法 | 代表 | 取捨 |
|---|---|---|
| 整數、數值取 max、最小寬度補零 | npryce/adr-tools ★5.7k（`grep -Eo '^[0-9]+' \| sort -rn`，`printf %04d`） | 短、好念、照時間順序；多人同時寫會撞號 |
| UTC 時間戳 | Rails 2.1 migrations、log4brains（ISO 日期＋slug） | 不會撞號；ID 長 14 碼，人工引用 `fix 20261004003912` 不實際 |
| 隨機或雜湊 | Alembic revision、changesets | 不會撞號；沒有順序，人記不住 |

社群共識：Rails 從流水號改成時間戳，就是為了解決多人分支同時產 migration 時的撞號問題。

fixindex 的情況：
- 寫入端只有 2 台機器，而且有 flock 配號鎖和 pull-first。
- 跨機撞號已經有 `resolve_id_collision` 事後改號，也有測試。
- 「`fix 9987`」這種短編號在 hook 注入、記憶和對話裡到處被引用，換成時間戳的遷移成本最高。

---

## 4. 決定：借鏡 adr-tools

- 配號：`max(int(\d+)) + 1`，用 `%04d` 補零，所以 9999 之後自然長成 10000、10001。
- 解析：35 處全改成「至少 4 位數」（`\d{4,}`、`split('-', 1)[0]`、`[0-9][0-9][0-9][0-9]*-*.md`）。
- 舊檔不用遷移，4 位數檔名照常被認得。
- 撤回補空號；兩筆撞號的條目改成 10000、10001，恢復時間順序。
- `fixindex-pretool.js` 原本就用 `\d{3,5}`，所以不用改。

---

## 5. 驗收

- `test_id_overflow.py`：9999 → 10000 → 10001；`SECTION_KEY` 能解析 `10000#1`；`build_entries` 同時認得 `10000` 和 `1000`。舊碼回 `10000`／`1001`，新碼通過。
- 12 個 `test_*.py` 全過。`id-race-test`（40 個 ID 不重複）、`fxauto-mixed`、`fxsync-pathspec` 全過。
- `intake-gate-test` 4.5 和 `section-trust-test` C9 會失敗，但在舊碼上一樣失敗，跟這次改動無關，沒有處理。
- 真實 store：`fixindex show 10000／10001／1000／9999` 各回正確的 slug；`find` 命中 `10001#2`；下一個配號是 `10002`；`status --assert-clean` 回 ok。
- beacon-harness：`fix_meta` 解析出 `fix-10000`、`fix-1000`；31 passed。

## 6. 什麼時候要重新評估

- 寫入端超過 3 台機器，或 `resolve_id_collision` 一個月觸發超過 1 次 → 改成時間戳 ID。
- ID 到 99999 → 檢查 `fixindex-pretool.js` 的 `\d{3,5}`。

來源：
- adr-tools `adr-new`：https://github.com/npryce/adr-tools/blob/master/src/adr-new
- Rails timestamped migrations 討論：https://discuss.rubyonrails.org/t/timestamped-migrations/31715
- OpenStack 的 migration 撞號討論：https://lists.openstack.org/pipermail/openstack/2011-June/022112.html
- log4brains 改用日期 ID：https://architecture.lullabot.com/adr/20210705-use-log4brains-to-manage-the-adrs
