# LazyContainerAgent

**中文** ｜ [English](README.en.md)

> **箱子物品「延遲反序列化 + 沒碰過就原樣寫回」的 Java agent。**
> 針對 Paper 1.21.11,把 chunk 載入時「立刻把每個箱子的物品從 NBT 解包」與卸載時「重新打包」這兩筆白工砍掉。

⚠️ **這不是外掛(plugin),是 Java agent** —— 用 `-javaagent:` 掛在 JVM 上,**不要丟 `plugins/`**(丟了沒用)。

> 🔒 **版本敏感(務必先讀)**
> 本 agent 以 bytecode **直接織入 Paper 1.21.11 / Java 21** 的內部類別(classfile major 65),屬**版本綁死**的工具。
> - **僅適用於 Paper 1.21.11 + Java 21。** 任何其他 Minecraft 版本或 Java 版本,**一律不要直接套用**。
> - 換版必須:① 以對應版本的 NMS 重新編譯 `template/`、② 將 ASM 升級到能解析目標 classfile 版本、③ 重新以 shadow 模式驗證。
> - 版本不符時會在**開機或首次載入箱子時直接拋出例外**(`VerifyError` / `NoSuchMethodError`)。這是**刻意的「安全停機」設計——絕不會靜默改壞或弄丟資料**,但該節點會無法啟動,因此**務必先在測試環境驗證**再上線。
> - 測試素材(region / 物品 dump)同為 1.21.11 格式,請勿在其他版本載入。

---

## 快速上手

> 前提:**Paper 1.21.11 + Java 21**(其他版本請先看上面的「版本敏感」)。

**1. 放 jar** —— 把 `LazyContainerAgent.jar` 放到節點看得到的位置(跟你的伺服器 jar 放同一層最省事)。**不要丟進 `plugins/`**:它是 Java agent、不是外掛,丟了沒作用。

**2. 改啟動參數** —— 在 `java` 那行、`-jar` 的**前面**,加上以下幾段(第一次**請先用 shadow 驗證模式**):

```bash
java ... \
  -javaagent:LazyContainerAgent.jar \
  -Dlazycontainer.shadow=true \
  -Dlazycontainer.verbose=true \
  -jar <你的 Paper>.jar nogui
```

**3. 先驗證,別急著上真效能** —— 開著 `shadow=true` 跑個幾天。它會把優化後的輸出跟原版做法**逐位元組對照**:只要 `shadowMismatch` 一直是 **0**,就代表輸出跟原版完全一致、**資料零風險**。代價是這階段兩套都做、暫時不會變快。
> - 開機 log 應出現 `[LazyContainer] agent installed … [SHADOW mode]`。
> - verbose 每隔一段印一行 `stash=… rawSave=… shadowMismatch=0 …`;`stash` 持續往上爬 = 正在運作。

**4. 確認沒問題,再換真效能** —— 跑數天 `shadowMismatch=0`、也沒玩家回報少東西,就把 `-Dlazycontainer.shadow=true` 拿掉、重啟。這時「沒人碰過的箱子」會直接原樣寫回(跳過打包),效能才真正省下來。

**回滾** —— 把那幾段 `-D` 與 `-javaagent` 拿掉、重啟,立刻回 100% 原版,**不需要任何資料遷移**(硬碟格式從頭到尾沒被改過)。

---

## 這東西在解決什麼

開伺服器開久了,你大概都會撞上一種很微妙的卡頓:

明明沒什麼人在線上,主執行緒卻莫名其妙地忙。

抓 spark 一看,真兇往往不是怪、不是紅石——是**箱子**。

更精確一點,是「箱子裡的東西」。Minecraft 把物品存在硬碟上時是壓縮打包的;每當一塊地圖(chunk)被載進記憶體,伺服器就把那一區**每一個箱子、每一格物品,從 NBT 完整拆包一遍**;這塊地圖要卸載時,又**整批重新打包**寫回去。

問題是——那些箱子,絕大多數從載入到卸載,**根本沒人去開**。

拆了、又包回去,中間沒人看一眼。純白工。

而且 1.21 之後物品帶了 data components(附魔、lore、自訂名稱、容器內容…),拆包打包更貴。一座放滿地圖畫的倉庫、一條塞滿界伏盒的儲存線,光是「被載入」這件事,就能把主執行緒吃掉好幾成——在廢土(約 110 個 Paper 節點)的正式環境裡,負載最重的節點一度有 **45%** 的主執行緒,就卡在這一條鏈上:

```
ChunkFullTask.run → … → ChestBlockEntity.loadAdditional
  → ContainerHelper.loadAllItems     ← 拆包箱子物品 ≈ 45%
```

面對這種卡頓,最輕鬆的解法是**禁止**——限制每個箱子能放幾張地圖、叫大家別蓋大倉庫。但這就像為了省電把冰箱拔掉:LAG 是不見了,玩家的東西也跟著不見了。我一向不信這套——**能用技術克服的,就不該用規則去閹割玩法。**

所以這個 agent 做的事,白話講就一句:

**沒人要看的箱子,別急著拆;沒人動過的箱子,就原封不動地放回去。**

載入時,先把箱子的原始資料**收著**、先不拆;真的有人去開、漏斗去抽、比較器去讀,才當場拆**那一個**。從載入到卸載都沒人碰的,就把當初收著的那包原始 bytes **逐位元組原樣寫回**——完全跳過重新打包。

對玩家來說,箱子裡裝什麼、擺在第幾格,**一模一樣**,你驗證不出任何差別。差別只在伺服器:那一大批「拆了又包、卻根本沒人看」的白工,消失了。

---

## 效能實證(206 層波動拳 → 0%)

vanilla 載入一個放滿地圖畫/唱片的箱子,光把物品從 NBT 解出來,呼叫堆疊就深到 **~206 層**——因為資料是真的巢狀(箱子 → 界伏盒 → 地圖畫 → lore → 不同顏色文字)再乘上 Mojang codec 框架每層疊 15-20 個 frame。最底層那一行只是在 `TextColor.parseColor`(解析 lore 顏色)/ `String.equals`(比對欄位名)。

<p align="center">
<img src="docs/img/callchain-206-before.png" width="360" alt="206 層呼叫鏈(波動拳)">
&nbsp;&nbsp;
<img src="docs/img/improved-after.png" width="440" alt="改善後">
</p>

`.lctest` 同一塊密集容器 chunk、`forceload` churn、跑兩輪:

| Run | 模式 | spark | 容器解碼佔主執行緒 | profile 節點數 | 最深呼叫 |
|---|---|---|---|---|---|
| 1 | vanilla | `WOVkupfiJx` | **62.17%** | 3378 | 200 層 |
| 1 | **agent** | `wGDbUTbZKN` | **0.00%** | 482 | 9 層 |
| 2 | vanilla | `AjXLAdXzTd` | **65.65%** | 4305 | 200 層 |
| 2 | **agent** | `caXFofKSVQ` | **0.00%** | 763 | 36 層 |

整座解碼塔在 agent profile **直接消失**。4 份 spark 原始檔(已靜態存檔避免連結失效)+ 完整 206 行鏈 + 說明:[`docs/spark/`](docs/spark/SUMMARY.md)。

> ⚠️ 62~66% 是「容器解碼**單獨隔離**」的壓力測;真實混合負載下佔比為載入 **~24%** + 卸載 **~11%**(負載最重的節點可達 **~45%**)。省的是解/打包 CPU,不省 I/O / GC。

---

## 怎麼運作

### 白話比喻
像搬家公司本來**每個經過倉庫的箱子都拆開檢查再封回**(連沒人問的也拆)。改成:**沒人要看的別拆;沒動過的原封出貨。**

### 技術機制
注入 NMS 容器類別,加入兩個合成欄位 + 改寫存取點:

| 動作 | 計數器 | 說明 |
|---|---|---|
| **延遲載入** | `stash` | `loadAdditional` 不呼 `ContainerHelper.loadAllItems`,改抓未解碼的原始 `Items` ListTag 暫存、標記 `pending`。**跳過解包。** |
| **存取時物化** | `ensure` | 首次有人呼 `getItems()/getContents()` → 才把暫存的 raw 解進清單(只解這一個)。 |
| **原樣寫回** | `rawSave` | 卸載存檔時若該容器全程沒被碰(`pending`)→ 把原始 bytes 逐位元組寫回。**跳過打包。** |
| **退回 eager** | `eagerLoad` | input 不是 `TagValueInput`(理論上不會)→ 安全退回原本 vanilla 行為。 |

涵蓋型別:`ChestBlockEntity`、`BarrelBlockEntity`、`ShulkerBoxBlockEntity`。
**唯一咽喉 = `getItems()`**:NMS `BaseContainerBlockEntity` 所有容器讀寫(isEmpty/getItem/removeItem/setItem/clearContent/掉落/比較器…)都經它,守一個即覆蓋全部;CraftBukkit 的 `getContents()` 會繞過,額外守。`getContainerSize()` 不經內容(結構性),不守。

---

## 架構(怎麼注入的)

純 plugin 無法覆寫 NMS final 方法,所以用 **Java agent + ASM bytecode 注入**:

1. **`LazyContainerAgentMain`**(premain):把整個 jar `appendToBootstrapClassLoaderSearch` 掛上 bootstrap classloader(繞過 Paper 隔離 classloader),再註冊 transformer。
2. **`LazyContainerTransformer`**(ASM):
   - 把 **`LazyContainerTemplate`**(用 plain Java 對「真實 NMS」編譯出的邏輯)splice 進 `BaseContainerBlockEntity`(欄位 + 方法,owner remap)。→ **編譯器驗證簽章,比手寫 ASM 安全。**
   - 在三個 leaf 的 `getItems/getContents/setItems` 入口插 guard、把 load/save 的 `ContainerHelper` 呼叫 redirect 成延遲版。
3. **`LazyContainerRuntime`**(bootstrap、純 JDK):shadow 開關 + 計數器。
4. **安全鐵律**:base(superclass)沒 splice 成功就**完全不動 leaf** → 退回純 vanilla,絕不產生 `NoSuchMethodError`;任何例外 → 回傳原 bytes。

---

## 為什麼不會掉資料 / 改到區塊資料

**它改的是「什麼時候解包」,不是「箱子存什麼」。硬碟格式從頭到尾沒變。**

- **沒碰的箱子** → 寫回的是載入時讀到的同一份 bytes(逐位元組相同),沒經轉換。
- **被碰的箱子** → 跟 vanilla 一模一樣地解碼、再一模一樣地存回。
- 只動箱子的 `Items`,不碰地形 / 方塊 / 實體 / 光照 / 其他 BE。

已驗證:
- **離線 JVM bytecode 驗證**:注入的 4 個類別全通過 link/verify。
- **真實 Paper 1.21.11 端對端**:放物品→重啟→重載,**逐字相同**(含 damage/component);漏斗存取觸發解碼正確、零遺失。
- **對抗審查(8 種失效模式 × 對抗驗證)**:**0 個會改/掉資料的路徑**;查到 2 個無關痛癢的 byte-identity 小差異,已修。
- **DFU 跨版本**:stash 的 raw 本來就是「DataFixerUpper 升級後」的(DFU 在 chunk-tag 層、BE 建立前跑完),回寫的也是升級後版本。

詳見 [`FINDINGS.md`](FINDINGS.md)、[`ADVERSARIAL-REVIEW.md`](ADVERSARIAL-REVIEW.md)。

---

## shadow 模式(上線必開的驗證)

`-Dlazycontainer.shadow=true`:每次要寫 raw **之前**,額外把 vanilla 的做法(解開→重打包)算一遍**逐位元組比對**:
- **一樣** → 寫 raw(並得到一筆「快路徑正確」的證據)。
- **不一樣** → 改寫 **vanilla 那份**(安全的),`shadowMismatch++` 並印座標。

→ **開著 shadow,硬碟輸出在數學上不可能跟 vanilla 不同**(零風險驗證)。代價:兩套都做了,**暫時沒加速**。
跑數天 `shadowMismatch=0` + 無玩家回報少東西 → 才關 shadow 換真效能。

### shadowMismatch vs benignReorder(語意感知比對)

純逐位元組比對對「**同一組物品、只是 Items 清單順序不同**」會誤判(常見於外掛產的容器——每個 entry 自帶 `Slot`,清單順序不影響槽位)。所以 v2 起把差異分兩類:

- **`benignReorder`** — raw 與 eager 是**同一組物品+槽位、只差清單順序**(以 multiset 比對確認)→ **安全寫 raw、不算問題**。但仍**偵測並回報**:印 `benign reorder @ <pos> — … NO IMPACT (raw kept)`(前 30 次,之後僅累加避免洗版)。
- **`shadowMismatch`** — 真正的結構差異(物品數量/內容變了,例如槽位越界被丟棄)→ 寫 eager(對齊 vanilla)+ 印座標。

→ 盯 **`shadowMismatch=0`** 即可;`benignReorder` 只是「外掛寫法不同」的無害提示,**不是要修的東西**。`-Dlazycontainer.dump=true` 時兩類都會把 raw/eager 各存一份(`lc-mismatch-N` / `lc-benign-N`)供離線 diff。

---

## 建置

```bash
bash build.sh        # JDK 21;產出 target/LazyContainerAgent.jar
```
需要 `nms-lib/`(你的伺服器核心 Paper 的 NMS 編譯相依 libraries,供 `template/` 對真實 NMS 編譯)。
此目錄不入 git(太大、含 Mojang/Paper 產物),建置前自行放好。

流程:① `mvn package`(agent 類別 + shade/relocate ASM + manifest)→ ② `javac` template 對真實 NMS 編譯 → ③ `jar uf` 把 template `.class` 當 passive resource 注入 jar(執行期只被讀 bytes、不被載入為類別)。

---

## 部署

把 jar 放到節點看得到的位置,在 `java` 那行 **`-jar` 前面**插旗標:

```bash
java -Xms8000M -Xmx8000M \
  -javaagent:LazyContainerAgent.jar \
  -Dlazycontainer.shadow=true \
  -Dlazycontainer.verbose=true \
  ... 原本的 -XX 旗標 ... \
  -jar <你的 Paper>.jar nogui
```

開機 log 應出現:
```
[LazyContainer] LazyContainerAgent —— crafted by 廢土貓大 LogoCat · 廢土 · mcfallout.net
[LazyContainer] spliced 2 fields + 6 methods into BaseContainerBlockEntity
[LazyContainer] transformed leaf .../ChestBlockEntity
[LazyContainer] agent installed (transformer registered) [SHADOW mode]
```

| 旗標 | 作用 |
|---|---|
| `-Dlazycontainer.shadow=true` | **上線必開**。輸出保證等同 vanilla;暫無加速。 |
| `-Dlazycontainer.verbose=true` | 背景 daemon 定期印計數。 |
| `-Dlazycontainer.verbose.ms=8000` | verbose 列印間隔(ms,預設 30000)。 |
| `-Dlazycontainer.dump=true` | mismatch / benign reorder 時把 raw/eager SNBT 各落一檔(`lc-mismatch-N` / `lc-benign-N`,各前 30 次),供離線 diff。 |
| `-Dlazycontainer.dump.dir=<路徑>` | dump 落檔目錄(預設 `.` = 伺服器工作目錄)。 |

**回滾**:刪掉那幾段旗標重啟 → 回 100% vanilla,**不需任何資料遷移**(硬碟格式沒被改過)。

---

## 實測(正式環境,shadow 模式)

在正式環境的 Paper 節點實掛 shadow 模式,觀察到的行為:

- **`shadowMismatch=0`(持續)** → 輸出與 vanilla 逐位元組一致,資料零風險。
- `stash` 持續累積 → 載入時「立刻解包」這件白工確實被攔下(也就是那 45% 的源頭)。
- `ensure` 的高低取決於該節點漏斗/比較器的活躍度:被碰到的箱子會即時物化(分散到各 tick),「完全省掉」的是「從載入到卸載都沒被碰」的那一批(`rawSave`)。

因此最大效益落在「閒置或 churn 中的容器」;最終加速幅度待關閉 shadow 後重抓 spark 對照(見上方「效能實證」)。

---

## 限制與注意

- **益處依賴「箱子沒被碰」**:churn / 閒置儲存(載入→沒人碰→卸載)大勝;**活躍的漏斗/比較器分類倉**會把箱子 ensure 掉,純省比例變小(主要益處變成「把載入尖峰打散」)。姊妹專案 **ChunkForceManager** 從「別讓 chunk 反覆載卸」那端互補。
- **版本綁定**:Paper **1.21.11 / Java 21**(major 65)。換版需用對應 NMS 重編 `template/`,並把 ASM 升到能讀目標 classfile 版本。版本不符會在開機/首次載箱子時**大聲報錯**(VerifyError/NoSuchMethod),不會靜默毀資料。詳見下方「版本敏感(務必先讀)」。
- 不影響:loot table 箱子(走另一條路徑,正交)、雙箱 CompoundContainer(委派到子箱 getItems,已守)、執行緒(載入/tick/卸載皆主執行緒)。

---

## 檔案地圖

```
src/main/java/io/github/kuohsuanlo/lazycontainer/
  LazyContainerAgentMain.java   premain / bootstrap 掛載
  LazyContainerRuntime.java     bootstrap 純 JDK:shadow 開關 + 計數器
  LazyContainerTransformer.java ASM:splice base + 改寫 leaf
template/.../LazyContainerTemplate.java   對真實 NMS 編譯的延遲邏輯(splice 來源)
tools/scan_containers.py        掃 region 檔找箱子最密的 chunk(找「載入最貴」的地點)
build.sh  pom.xml  nms-lib/(不入 git)
FINDINGS.md           反編譯確認的事實 + 設計定案 + 風險分析
ADVERSARIAL-REVIEW.md 對抗審查報告(8 失效模式)
TESTING.md            怎麼自己測(自動 round-trip / 手動玩測 / 真實世界副本驗 shadow)
```

延伸閱讀:[`FINDINGS.md`](FINDINGS.md)(技術全貌)· [`TESTING.md`](TESTING.md)(自測)· [`ADVERSARIAL-REVIEW.md`](ADVERSARIAL-REVIEW.md)(審查)。
