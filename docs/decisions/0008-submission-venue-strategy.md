# ADR-0008：投稿場域策略（含時效）

- 狀態：Accepted（含時效，依日期需複查）
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 諮詢：投稿決策報告（修訂版 v2，2026-06-25）
- 知會：指導教授

## Context and Problem Statement 脈絡與問題

整合計畫尚未實作完成，但作者已有一個**已發表、已 DOI、可展示**的成品：Satellite Mission Compiler（DOI 10.5281/zenodo.19391965，EUPL-1.2）。問題：近期該投什麼、投哪裡？未完成的整合計畫適合投研討會還是學術會議？

## Decision Drivers 決策驅動力

- LF/CNCF 研討會 CFP 看重「**已完成、可 demo、可評估的技術深度**」，勸阻 AI 樣板，禁銷售/閉源（但**未禁前瞻/WIP**）。
- 整合計畫的**論文版**需要實證（E1–E3），尚未就緒。
- CFP 時程約束。

## Considered Options 考慮過的選項

1. **投已發表的成品 talk；整合計畫走學術 workshop（採納）**：近期投 Satellite Mission Compiler；整合計畫論文待 E1–E3 完成後投 ICPE 2027 類學術 workshop。
2. **直接投未完成的整合計畫**到研討會。
3. **什麼都不投，等整合計畫全完成**。

## Decision Outcome 決策結果

選擇 **「選項 1」**。理由：

- 研討會 CFP 的決策邏輯不是「願景被禁」（其實未禁），而是「**已完成、可 demo、可引用的成品最大化 CFP 看重的可評估技術深度信號**」；未建構的整合計畫反而更像樣板/願景、較難晉級。
- 整合計畫的價值在實證（跨層一致性、E3 deferred-red 隔離），屬學術 systems venue（ICPE/Middleware industry/IC2E 類），且 arXiv 2602.04900 即走 ICPE'26，場域吻合。

### 近期落點（2026-06-25 重查，依時效排序）

| 順位 | 場域 | 關鍵日期 | 狀態 |
|---|---|---|---|
| 最近期 | **OpenSSF Community Day EU** | CFP 開到 **7/12** | openssf.org 證實 |
| 近期主目標 | **OSS Japan 2026（Tokyo）** | 12/7–9；CFP **8/24** 23:59 JST | LF 官方證實 |
| 旗艦長線 | **KubeCon EU 2027（Barcelona）** | 3/15–18；CFP 預計 H2 2026 開 | LF calendar 證實 |
| 論文版 | **ICPE 2027 類學術 workshop** | 投前逐一查 | 待 E1–E3 完成 |
| ❌ 已過 | OSS EU 2026（Prague 10/7–9） | CFP **06-24 已截止** | **今日 06-25 已過期** |

### Consequences 後果

- 好處：近期就有可投的成品；決策邏輯誠實（非「願景被禁」）；論文走對的場域。
- 壞處：整合計畫論文需等 E1–E3，週期較長。
- 中性：投稿用 30–40 分 session（LF Summit 慣例），track 依場域選（Policy Agents / Edge AI / Cloud-Native AI / Aerospace）。

### Confirmation 確認

**兩個須作者手動確認的時效點**：
1. 投 OpenSSF / OSS Japan 前在 **Sessionize 確認 CFP 仍開放**（本 ADR 依官網公告日期，非即時 Sessionize 狀態）。
2. 學術場域（SoCC / Middleware / IC2E / CCGrid / IEEE SEC）2026–2027 deadline **投前逐一查**（本次未逐一確認）。

## Pros and Cons of the Options 各選項利弊

### 選項 1：投成品 + 整合計畫走學術
- 優點：近期可投；誠實；場域對。
- 缺點：論文週期長。

### 選項 2：直接投未完成整合計畫
- 優點：若中則早。
- 缺點：像願景/樣板、難晉級；無實證支撐。

### 選項 3：什麼都不投
- 優點：等全完成再一次到位。
- 缺點：錯過近期所有 CFP；可見度歸零。

## More Information 更多資訊

- 一手來源：openssf.org（OpenSSF Community Day EU CFP）、events.linuxfoundation.org（OSS Japan CFP、KubeCon EU 2027 calendar）。
- DOI：10.5281/zenodo.19391965（Satellite Mission Compiler，EUPL-1.2）。
- **透明聲明**：把「OSS EU」換成「OSS Japan/OpenSSF」是依「今日日期 + 作者既定近期目標」的推斷；若作者其實要保留 OSS EU 歷史框架（如已於截止前投出），請於 PR 修正本 ADR。
- 相關：投稿決策報告修訂版 v2、SDD §2.2（C-O2）。
- **後續複查**：任何日期變動後重查 CFP 狀態。
