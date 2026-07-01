# ADR-0003：以 OPA/Rego（可選 Gatekeeper）為政策守門

- 狀態：Accepted
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 知會：指導教授

## Context and Problem Statement 脈絡與問題

契約在編譯為各層成品之前，必須先通過合法性守門：租戶請求是否超出其授權上限？deadline 是否低於系統最小可服務時間？資源類別是否存在？問題：用什麼引擎做這層「policy-as-code」守門，才能做到宣告式、可版本控制、可單元測試、且與既有方法學連續？

## Decision Drivers 決策驅動力

- 守門規則須**宣告式、可測試、版本控制**（policy-as-code）。
- 沿用既有編譯器方法學（已用 OPA/Rego）的**連續性**。
- 守門正確性（Q4）需 `opa eval` 單元測試（known-good/known-bad）。
- 可選地把規則推到**叢集端強制**（防止繞過編譯器直接 apply）。

## Considered Options 考慮過的選項

1. **OPA/Rego 作編譯期守門；可選 Gatekeeper 作叢集端 admission webhook**。
2. **Kyverno**（YAML-based K8s 原生政策引擎）。
3. **在 Pydantic / 程式碼裡硬寫 if-else 驗證**。

## Decision Outcome 決策結果

選擇 **「選項 1：OPA/Rego（可選 Gatekeeper）」**。OPA 模型 `input（契約 JSON）→ policy（Rego）→ decision（allow/deny + reason）` 正好契合「契約守門」；Rego 宣告式、set-based、可 `opa eval` 單元測試；與作者既有編譯器方法學連續（降風險）。需要叢集端強制時，Gatekeeper 的 `ConstraintTemplate`（規則本體）＋`Constraint`（套用範圍與參數）＋Controller 是 2026 K8s admission 的事實標準，可防止繞過編譯器直接 apply 不合規物件。

### Consequences 後果

- 好處：policy-as-code（版本控制、可測試、可重用）；與既有方法學連續；可選地叢集端強制；OPA AOT 編譯到 IR、評估為單位數毫秒。
- 壞處：Rego 學習曲線陡（非命令式、無傳統迴圈/可變變數）；規則是活產物需持續維護。
- 中性：是否啟用 Gatekeeper 視部署情境而定；研究原型可先只用編譯期 OPA。

### Confirmation 確認

Q4/E1：對 known-good/known-bad 契約樣本，`opa eval` 單元測試全綠、無 false-allow；新政策進 deny 模式前先跑 1–2 週 dry-run（對齊 2026 PaC 業界最佳實踐）。

## Pros and Cons of the Options 各選項利弊

### 選項 1：OPA/Rego（可選 Gatekeeper）
- 優點：通用、跨層；與既有方法學連續；可測試；CNCF graduated；可選叢集強制。
- 缺點：Rego 學習曲線。

### 選項 2：Kyverno
- 優點：YAML、對非程式背景者更親和；K8s 原生。
- 缺點：與既有方法學不連續（既有用 Rego）；表達複雜跨資源邏輯不如 Rego；非通用引擎。

### 選項 3：硬寫 if-else
- 優點：起步最快、無新依賴。
- 缺點：非宣告式、難測試、難重用、規則散落；policy-as-code 的價值全失。

## More Information 更多資訊

- 對應 SDD §4.1、§8.2。
- 業界訊號：Red Hat（2026-03）「Eliminating the Rego tax」以 LLM 自動生成 context-aware Gatekeeper 政策（Intent-as-Governance）——與本計畫「契約 intent → 政策」相鄰但不同（彼方是從 live cluster 違規生成 Rego，本方是把型別化任務 QoS 契約經驗證 IR 編譯）。可作 related work 區隔。
- 相關：ADR-0002（IR）、ADR-0004。
