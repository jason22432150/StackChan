# 01｜設計決策登錄（#1～#96）

> 由本次對話確認結果重建；保留必要的摘要語義，並非逐字決策逐字稿。若需法律級決策佐證，應以原始對話核對。後續 #97–#99 是先前助手提出的候選細化，不列入「已確認的 96 項」。

| ID | 決策摘要 | 狀態 |
|---:|---|---|
| D-001 | C｜Agent 全生命週期：開始、執行、等待、完成、失敗 | CONFIRMED |
| D-002 | C｜各事件可自訂畫面／Servo／音訊／TTS | CONFIRMED |
| D-003 | D｜智慧優先級、合併、佇列與搶占 | CONFIRMED |
| D-004 | D｜自訂中斷規則；不打斷 Xiaozhi | CONFIRMED |
| D-005 | D｜收件／呈現／已讀、去重與智慧重播 | CONFIRMED |
| D-006 | D｜Bridge SQLite＋Coordinator 分散式同步 | CONFIRMED |
| D-007 | D｜Coordinator 原生跨平台／Docker／NAS | CONFIRMED |
| D-008 | D｜早期 Bridge 直連備援；已被 #81 限制 | CONFIRMED |
| D-009 | D｜mDNS、安全配對、IP 手動備援 | CONFIRMED |
| D-010 | D｜LAN／VPN／可選遠端中繼，不公開 CoreS3 | CONFIRMED |
| D-011 | D｜Bridge CLI＋Tray GUI＋Local Web | CONFIRMED |
| D-012 | D｜Adapter 探測與最小授權，官方接口優先 | CONFIRMED |
| D-013 | D｜分級資料蒐集、預設不蒐集敏感全文 | CONFIRMED |
| D-014 | D｜Xiaozhi 語音查詢 Coordinator／可選獨立服務 | CONFIRMED |
| D-015 | D｜喚醒詞／觸控／追問，共用單一音訊工作階段 | CONFIRMED |
| D-016 | D｜表情＋全身＋Servo＋Audio 時間軸 | CONFIRMED |
| D-017 | D｜多角色，Mew 全身；保留原廠備援 | CONFIRMED |
| D-018 | D｜韌體／SD／Flash 混合素材與版本策略 | CONFIRMED |
| D-019 | D｜Web 時間軸編輯、JSON/YAML、Windows 模擬器、授權硬體預覽 | CONFIRMED |
| D-020 | D｜多 CoreS3 單播／群播／廣播 | CONFIRMED |
| D-021 | D｜裝置、桌面、手機、Web 多平台通知 | CONFIRMED |
| D-022 | C｜全域已讀同步，獨立裝置仍可呈現 | CONFIRMED |
| D-023 | A｜短期保存（7／14／30 日為候選，未鎖值） | CONFIRMED |
| D-024 | A｜基本錯誤日誌，不做大型監控 | CONFIRMED |
| D-025 | C｜分級軟體更新，韌體與 OTA 需核准 | CONFIRMED |
| D-026 | D｜核心先行＋模組可平行 | CONFIRMED |
| D-027 | D｜開發規格全套：架構/API/DB/安全/測試/AI 計畫 | CONFIRMED |
| D-028 | D｜調查源碼後各模組選適合技術堆疊 | CONFIRMED |
| D-029 | D｜先技術可行性研究及證據分級 | CONFIRMED |
| D-030 | D｜繁體中文 Markdown＋英文契約／PDF 總覽 | CONFIRMED |
| D-031 | D｜多 AI 分支／worktree／PR／CI／人工高風險核准 | CONFIRMED |
| D-032 | D｜單元／契約／整合／故障＋CoreS3 實機驗收 | CONFIRMED |
| D-033 | C｜風險分級開發授權，高風險明確授權 | CONFIRMED |
| D-034 | C｜跨平台核心 MVP，Windows＋CoreS3 先驗收 | CONFIRMED |
| D-035 | D｜官方 Hook／Browser／桌面 UI Adapter 分層能力 | CONFIRMED |
| D-036 | D｜事件語義、可信度、response.completed ≠ task.succeeded | CONFIRMED |
| D-037 | D｜智慧 timeout／Idle／反通知風暴，不擅自取消任務 | CONFIRMED |
| D-038 | A｜只通知與查詢，禁止遠端 Agent 控制 | CONFIRMED |
| D-039 | C｜唯讀 Agent Dashboard、查詢與篩選 | CONFIRMED |
| D-040 | D｜機器/Agent/Session/Task/Project 識別及歧義解決 | CONFIRMED |
| D-041 | A｜僅原始事件資料，不增加 AI 摘要／臆測任務內容 | CONFIRMED |
| D-042 | D｜音量／靜音時段／DND，可自訂且不影響 Xiaozhi | CONFIRMED |
| D-043 | D｜可自訂 CoreS3 通知 UI | CONFIRMED |
| D-044 | D｜情境式浮層／全螢幕／狀態圖示 | CONFIRMED |
| D-045 | D｜智慧群組／輪播／優先級，保留原始事件 | CONFIRMED |
| D-046 | D｜觸控手勢、情境動作、防誤觸 | CONFIRMED |
| D-047 | A｜CoreS3 不保存本機通知歷史，只使用 RAM | CONFIRMED |
| D-048 | D｜重連去重／復原；早期直連備援受 #81 限制 | CONFIRMED |
| D-049 | D｜Bridge GUI 與 CoreS3 初次配對引導、診斷 | CONFIRMED |
| D-050 | B｜一鍵匯出簡單遮蔽診斷 | CONFIRMED |
| D-051 | D｜設定備份／同步／版本化選擇性復原 | CONFIRMED |
| D-052 | D｜全域/裝置/Bridge/Agent/Project/Event 分層設定 | CONFIRMED |
| D-053 | D｜視覺規則編輯＋JSON/YAML 聲明式驗證 | CONFIRMED |
| D-054 | C｜內建＋本地模板庫，無公開市集 | CONFIRMED |
| D-055 | A｜不建立統一插件套件格式／管理器 | CONFIRMED |
| D-056 | C｜SD 卡優先，韌體內建角色備援 | CONFIRMED |
| D-057 | C｜SD 手動或經核准 LAN 上傳 | CONFIRMED |
| D-058 | D｜PC 端素材轉換優化，PNG/圖層/Spritesheet 等 | CONFIRMED |
| D-059 | D｜影格/圖層/Servo/音效混合動畫時間軸 | CONFIRMED |
| D-060 | D｜分層狀態機、控制權與安全狀態回復 | CONFIRMED |
| D-061 | D｜情境 Mew 待機與資源負載適應 | CONFIRMED |
| D-062 | D｜效能層級、動態資源預算、安全降級 | CONFIRMED |
| D-063 | C｜分級安全模式，避免重啟循環 | CONFIRMED |
| D-064 | A｜韌體及 SD 手動恢復；不自動 OTA 回滾 | CONFIRMED |
| D-065 | B｜功能＋穩定性實機驗收；無需精密硬體實驗室 | CONFIRMED |
| D-066 | D｜契約先行、模組化 AI 開發、分期整合 | CONFIRMED |
| D-067 | A｜唯一一份 Markdown 開發清單 | CONFIRMED |
| D-068 | D｜依賴驅動＋MVP 優先＋可平行 | CONFIRMED |
| D-069 | C｜自動化驗收＋關鍵階段人工確認 | CONFIRMED |
| D-070 | D｜完整技術風險登錄＋驗證門檻 | CONFIRMED |
| D-071 | C｜技術替代方案按風險分級授權 | CONFIRMED |
| D-072 | C｜規格版本基準＋變更紀錄 | CONFIRMED |
| D-073 | D｜完整一致性審查＋決策追溯 | CONFIRMED |
| D-074 | C｜先進行需求總覽＋缺漏確認 | CONFIRMED |
| D-075 | A｜單一使用者模式 | CONFIRMED |
| D-076 | D｜智慧補送＋Event TTL＋最新狀態重新確認 | CONFIRMED |
| D-077 | D｜完整情境感知隱私 | CONFIRMED |
| D-078 | C｜規則情境判斷＋手動優先 | CONFIRMED |
| D-079 | C｜敏感語音追問分級＋可信確認 | CONFIRMED |
| D-080 | D｜分層隱私政策同步＋裝置獨立授權 | CONFIRMED |
| D-081 | A｜Coordinator 離線時完全禁用 Agent 通知 | CONFIRMED |
| D-082 | C｜政策版本／撤銷驗證／安全恢復 | CONFIRMED |
| D-083 | C｜狀態機＋指數退避＋連線穩定門檻 | CONFIRMED |
| D-084 | C｜分級視覺提示＋按需診斷 | CONFIRMED |
| D-085 | C｜智慧恢復提示＋累積通知合併 | CONFIRMED |
| D-086 | D｜風險優先＋追溯＋分批衝突審查 | CONFIRMED |
| D-087 | D｜安全優先原子中斷＋狀態恢復 | CONFIRMED |
| D-088 | D｜資源控制器＋Generation Token＋取消確認 | CONFIRMED |
| D-089 | D｜Xiaozhi 安全搶占＋智慧恢復 | CONFIRMED |
| D-090 | D｜公平排程＋優先級＋合併＋背壓 | CONFIRMED |
| D-091 | D｜完整交付狀態機＋呈現收據 | CONFIRMED |
| D-092 | D｜冪等事件＋裝置獨立狀態＋版本化同步 | CONFIRMED |
| D-093 | D｜追加式日誌＋因果順序＋版本化對帳 | CONFIRMED |
| D-094 | D｜分層身份＋證據等級＋不確定性隔離 | CONFIRMED |
| D-095 | D｜可信分級＋通知權限矩陣＋防誤報 | CONFIRMED |
| D-096 | D｜追加式證據修正＋通知撤銷／更正＋版本化狀態 | CONFIRMED |

## 後續候選細化（非已確認需求）

- **P-097**：多 Adapter 矛盾證據，不以最後到達覆寫；權威與語義優先，不能決定則衝突標記。
- **P-098**：後續更正採追加式關聯，必要時低干擾更正提示（實質對 #96 的落地細化）。
- **P-099**：交付、已讀、任務結果分離（實質重述 #91）。

## 決策優先規則

明確、較晚的安全決策優先於舊的相容性假設。例如 D-081 對 D-008／D-048 的故障備援施加禁止直送限制。一般實作提案不得自行推翻已確認不變式；遇到真正矛盾應列入風險並請求人工核准。
