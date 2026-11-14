STAGE=adjudicate
只讀 {INPUT} 這一個檔，不跑其他指令、不讀其他檔（fixindex 條目庫在工作目錄外，讀取會被拒絕而整題失敗）。查重資訊全在 hits 裡，只憑 hits 裁決。不要建立、修改或刪除任何檔案。

它是一個 JSON 陣列，每個元素是一個候選：i（編號）、kind、core、quote、fields，以及 hits（fixindex 既有條目的查重結果：key、file、title、score）。

一次看完全部候選再裁決，對每個 i 輸出一行 JSON，不要包在 code block 裡：
{"i":0,"action":"write"}
{"i":1,"action":"skip","reason":"已存在 NNNN"}
{"i":2,"action":"skip","reason":"同輪重複，併入 0"}

裁決規則：
- hits 裡有條目講的是同一個根因、同一條規則 → skip，reason 寫「已存在 <編號>」。只是關鍵字重疊、根因不同的不算。
- 候選彼此同主題 → 只留一條 write，其餘 skip，reason 寫「同輪重複，併入 <i>」。要保留的那條缺的資訊可以補：在它那行加 "fields":{…完整欄位…} 覆蓋原欄位，quote 不可改。
- 一次性、只對單一專案有意義、下次 fixindex find 找到也沒用的 → skip，reason 寫「一次性」或「無重現價值」。
- 其餘 write。
- 每個 i 都要有一行。
