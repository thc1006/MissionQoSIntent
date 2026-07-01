# ADR-0005：以 Kueue + DRA 作 L4 配額與裝置

- 狀態：Accepted
- 日期：2026-06-25
- 決策者：Hsiu-Chi Tsai
- 知會：指導教授

## Context and Problem Statement 脈絡與問題

L4 需要兩件事：(i) 多租戶**配額**管理（誰能用多少 GPU/CPU/記憶體、可否互借、過載時誰被搶占）；(ii) GPU **裝置**的宣告與配置（哪顆卡、多少 VRAM、什麼型號）。問題：用哪些 K8s 原生機制承接 IR 渲染出的 L4 成品，且能與 arXiv 2602.04900 的既有貢獻區隔？

## Decision Drivers 決策驅動力

- 要**原生 K8s**、可被 IR 渲染為宣告式 manifests。
- 配額（quota reservation）與裝置（device allocation）職責要清楚分離。
- 要與 arXiv 2602.04900（已示範 Kueue + **DAS** + GAIE）**區隔/互補**，而非複製。
- 版本要對齊 2026-06 現況。

## Considered Options 考慮過的選項

1. **Kueue（配額）+ DRA（裝置）（採納）**：Kueue `ClusterQueue`/`LocalQueue`/`ResourceFlavor`/`Workload`/`Cohort` 管配額與 fair-sharing；DRA `DeviceClass`/`ResourceClaim`/`ResourceClaimTemplate`/`ResourceSlice` 管裝置。
2. **DAS（Dynamic Accelerator Slicer）路徑**：跟隨 arXiv 2602.04900 用 DAS 做 GPU 切分。
3. **傳統 Device Plugin + nodeSelector/taints**：不用 DRA。

## Decision Outcome 決策結果

選擇 **「選項 1：Kueue + DRA」**。理由：

- **原生且宣告式**：兩者皆 K8s 原生 API，IR 可直接渲染為 YAML。
- **職責分離乾淨**：Kueue 管 quota reservation（鎖配額，≠ pod scheduling），DRA + kube-scheduler 管實際裝置配置——正好對應「L4 配額」與「L4 裝置」兩件事，也讓 admission-vs-allocation 的 timing gap 可被明確處理（見 SDD §11 R-3）。
- **與 2602.04900 互補而非複製**：該論文用 **DAS** 切分 GPU；本系統走 **DRA** 路徑。因此一個 **Kueue + DRA + GAIE** 的範例**填補了 2602.04900（Kueue + DAS + GAIE）未覆蓋的 DRA 縫**，是互補貢獻。
- **版本對齊（2026-06-25 重查）**：K8s v1.36（DRA 核心 v1.34 GA；v1.36 prioritized list GA、Device Taints/Tolerations beta、DRA Admin Access GA、Extended Resource via DRA beta；scheduler 把 ResourceSlice 分 shared/per-node，降約 50% Filter 延遲）；Kueue v0.18.1（`v1beta2`；`KueueDRAIntegration` 升 beta 預設開；DRA 配額計帳自 v0.17 alpha）。

### Consequences 後果

- 好處：原生宣告式；職責分離；與既有論文互補；可重現（固定版本）。
- 壞處：**DRA 配額雙重計費雷**——未開 `DRAExtendedResources` 會對同裝置同時計 `requests` 與自動建立的 `ResourceClaim`（見 SDD §11 R-5）；**preemption 雷**——`ResourceClaim` 的 Pod 預設 `PreemptLowerPriority` 會增 autoscaling 延遲，須設 `preemptionPolicy: Never`；**timing gap**——Kueue 只查配額不知哪顆裝置，kube-scheduler 才配置，狀態變化時可能配置失敗。
- 中性：`ResourceClaim`（共享，適合推論）vs `ResourceClaimTemplate`（每 Pod 專屬，適合訓練）的選擇依工作負載而定。

### Confirmation 確認

E1：DRA 配額計帳正確（開 `DRAExtendedResources` 後無雙重計費）；`ResourceClaim` 用 CEL 選對裝置；Kueue admission 與 DRA 配置在 commodity 叢集上端到端跑通；`preemptionPolicy: Never` 已設。

## Pros and Cons of the Options 各選項利弊

### 選項 1：Kueue + DRA
- 優點：原生宣告式；職責分離；互補 2602.04900；可重現。
- 缺點：雙重計費/preemption/timing gap 等已知雷需處理。

### 選項 2：DAS 路徑
- 優點：跟隨已發表的成功路徑。
- 缺點：與 2602.04900 重疊（複製而非互補）；DAS 偏 GPU 切分，與「配額管理」職責不同。

### 選項 3：Device Plugin + nodeSelector
- 優點：成熟、簡單。
- 缺點：all-or-nothing、無細粒度屬性選擇；與「宣告式契約→裝置宣告」的研究主軸不合；非 2026 方向。

## More Information 更多資訊

- 一手來源：K8s DRA concepts（`resource.k8s.io/v1`）、Kueue `setup_dra`/concepts/releases（v0.18.1）、arXiv 2602.04900（DAS，DOI 10.1145/3777884.3796983）。詳見 `references.md`。
- 相關：ADR-0006（GAIE）、ADR-0002（IR 渲染 L4）、SDD §5.3、§7。
- **可信度資產（待確認）**：Kueue v0.18 release notes 的 `#12094, @thc1006`（DRA hot-reconcile 修復）若為作者，直接佐證此路徑的 upstream 投入。
