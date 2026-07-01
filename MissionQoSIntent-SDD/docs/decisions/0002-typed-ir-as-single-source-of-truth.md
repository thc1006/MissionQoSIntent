# ADR-0002：以型別化 IR 為單一事實來源（single source of truth）

- 狀態：Accepted
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 知會：指導教授

## Context and Problem Statement 脈絡與問題

一份 QoS 契約須轉成三層成品：L2（admission gate 設定）、L4（Kueue 配額 + DRA 裝置宣告）、L5（GAIE 設定）。若每層各自從契約直接生成，極易出現「改了一層忘改另一層」的不一致（例如 L4 配額單位改了、L2 的 admission 計數沒跟上）。問題：用什麼結構承接契約，才能讓跨層一致性**結構上可保證、且可驗證**？

## Decision Drivers 決策驅動力

- **跨層一致性（Q1，最強貢獻腿）** 需要同源。
- **可追溯性（Q5）**：成品欄位須能回指契約與任務語意。
- 沿用作者既有編譯器方法學（Pydantic + 型別 IR + 多目標 renderer，422 tests）的**連續性**與**降風險**。
- 型別檢查可在編譯期攔下大量錯誤。

## Considered Options 考慮過的選項

1. **型別化 IR 為單一事實來源**：契約 → 驗證 → 型別化 IR → 各層 renderer 從 IR 渲染；IR 節點帶 provenance。
2. **各層直接從契約生成**：無中間層，三個獨立 generator 各讀契約。
3. **以 Kubernetes CRD 為事實來源**：把契約直接做成 CRD，控制器 reconcile 出各層。

## Decision Outcome 決策結果

選擇 **「選項 1：型別化 IR」**，因為所有層成品由同一 IR 渲染，**結構上即保證同源**；再加 golden tests 攔截渲染後的不一致，即可把「跨層可驗證一致性」做成本研究最硬的貢獻。OPA 自身就把 Rego 編譯為 AST→IR（AOT），是「以 IR 承接宣告式輸入」的成熟業界前例，佐證此路徑可行。

### Consequences 後果

- 好處：跨層一致性結構上同源；型別檢查早攔錯；provenance 支撐可追溯；與既有編譯器方法學連續。
- 壞處：多一層 IR 設計與維護成本；IR schema 演進需版本管理。
- 中性：IR 的抽象粒度需隨各層 API 演進調整（如 Kueue v1beta2、GAIE v1alpha1 變動時）。

### Confirmation 確認

E1：對 N 個契約，三層成品皆由 IR 渲染；注入「只改一層」的不一致，golden tests 必失敗。IR 每節點可列出其 provenance 連結。

## Pros and Cons of the Options 各選項利弊

### 選項 1：型別化 IR
- 優點：同源保證一致；可追溯；可測試；方法學連續。
- 缺點：多一層成本。

### 選項 2：各層直接生成
- 優點：少一層、起步快。
- 缺點：一致性無結構保證，全靠紀律；最強貢獻腿（可驗證一致性）直接消失。

### 選項 3：CRD 為事實來源
- 優點：K8s 原生、可 reconcile。
- 缺點：把研究綁進控制器運維複雜度；契約語意被 CRD schema 限制；離線可驗證性與可攜性下降；對單人專題過重。

## More Information 更多資訊

- 對應 SDD §4.2、§5、§8.1、§8.3。
- 相關：ADR-0001、ADR-0006（GAIE 設定非 CRD，僅啟動讀取——更說明「以離線 IR 渲染設定」比「線上 reconcile」更貼合 GAIE 現況）。
