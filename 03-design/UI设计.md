# 阶段 3：UI 设计规范

- 项目：DragDriveCodes（占位品牌）
- 版本：v1.0，2026-11-15
- 落地方式：全部为原生 CSS 变量 + 语义化 HTML，无 UI 框架、无外部字体、无装饰性图片

---

## 一、视觉方向

**关键词：赛道仪表盘（Track Dashboard）**

把「兑换码」当成仪表盘上的读数来做：深色底、高对比数据、荧光青柠色做「有效/可操作」信号、等宽字体呈现码本身。整体观感偏游戏工具，而不是媒体资讯站。

三条设计原则：

1. **答案优先于装饰**：首屏 60% 面积是码本身，没有任何英雄大图、没有插画、没有轮播。
2. **状态即颜色**：Confirmed / Reported / Expired 三种状态用固定色 + 文字标签双编码（不只靠颜色，兼顾色盲）。
3. **拇指可达**：所有可点元素 ≥ 44×44px，复制按钮在卡片右侧固定位置，单手可点。

### 1.1 为什么适合该类目受众

| 受众特征 | 设计应对 |
|---|---|
| Roblox 玩家，移动端为主，碎片时间 | 单列卡片流、首屏即码表、无横向滚动 |
| 熟悉游戏 UI，习惯 HUD 语言 | 仪表盘式数字排版、荧光强调色、状态徽标 |
| 对「假/过期码」高度敏感 | 绿色 Confirmed 徽标 + 逐码日期，视觉上可扫读 |
| 需要复制粘贴长串大写码 | 等宽字体 + 独立复制按钮 + 复制成功反馈 |
| 网络环境差异大（东南亚移动网络） | 零外部字体、零图片、CSS 内联关键部分、单文件 CSS |
| 竞争对手多为白底媒体模板 | 深色 + 荧光形成 SERP 外的记忆点，首页停留更久 |

---

## 二、色彩系统

深色单主题（本期不做明暗切换，减少状态与测试成本）。

| Token | 值 | 用途 | 对比度 |
|---|---|---|---|
| `--bg` | `#0A0D12` | 页面底色 | — |
| `--bg-elev` | `#11161F` | 卡片 / 表头 | — |
| `--bg-elev-2` | `#161E2A` | 悬浮 / 代码块 / 步骤序号底 | — |
| `--line` | `#232C3A` | 1px 分隔线、卡片描边 | — |
| `--line-strong` | `#344054` | 输入框、焦点前描边 | — |
| `--text` | `#E8EDF5` | 正文 | 对 `--bg` 15.8:1 |
| `--text-dim` | `#98A4B7` | 次要说明、日期 | 对 `--bg` 7.1:1 |
| `--text-mute` | `#6E7B8F` | 页脚、禁用 | 对 `--bg` 4.2:1（仅大字号） |
| `--accent` | `#C8FF3D` | 主 CTA、复制按钮、高亮数字 | 对 `--bg` 15.3:1 |
| `--accent-ink` | `#0A0D12` | 强调色上的文字 | 15.3:1 |
| `--ok` | `#35D07F` | Confirmed 徽标 | 对 `--bg` 9.6:1 |
| `--warn` | `#FFB020` | Reported / 提醒 | 对 `--bg` 11.2:1 |
| `--danger` | `#FF5C5C` | 失败、过期提示 | 对 `--bg` 6.4:1 |
| `--info` | `#5AA9FF` | 正文链接 | 对 `--bg` 7.4:1 |

状态色只用于徽标与小面积描边，不做大块背景，避免「万圣节配色」。

---

## 三、字体与排版

**不使用 Web Font**（性能优先，跨境移动网络友好）。

```css
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
```

| 层级 | 规格 | 用途 |
|---|---|---|
| H1 | 32/38px（移动 28/34），700，`-0.02em` | 每页唯一，含主词 |
| H2 | 22px / 1.3，700 | 区块标题 |
| H3 | 17px / 1.4，650 | 卡片内标题 |
| 正文 | 16px / 1.65，400，`--text` | 说明文字 |
| 小字 | 14px / 1.55，`--text-dim` | 日期、来源、注释 |
| 标签 | 12px，700，`uppercase`，`0.08em` 字距 | 徽标、分区标签 |
| 数字读数 | 28–34px，700，`--accent`，`tabular-nums` | 「5 codes / 155M RP」 |
| 兑换码 | 17px，700，`--font-mono`，`letter-spacing: .02em`，`word-break: break-all` | 码本体 |

排版规则：
- 正文最大宽度 **68ch**；表格与码卡可到 100% 容器宽（1080px）。
- 每段 ≤ 3 行；codes 类页面用户是扫读，不是阅读。
- 不用斜体，不用超过 2 级的下划线装饰。

---

## 四、间距与栅格

```css
--sp-1: 4px;  --sp-2: 8px;  --sp-3: 12px; --sp-4: 16px;
--sp-5: 24px; --sp-6: 32px; --sp-7: 48px; --sp-8: 64px; --sp-9: 96px;
--radius-sm: 8px;  --radius: 12px;  --radius-lg: 16px;  --radius-pill: 999px;
--shadow-1: 0 1px 2px rgba(0,0,0,.4);
--shadow-2: 0 8px 24px -8px rgba(0,0,0,.6);
```

- 容器：`max-width: 1080px`，左右 padding 移动 16px / ≥640px 24px / ≥1024px 32px。
- 区块垂直节奏：区块间 `--sp-7`(48)，区块内 `--sp-4`。
- 断点：`640px`（码卡从单列转两列信息布局）、`900px`（导航展开、表格完整展示）。
- **零横向溢出**：所有宽内容（过期码表格）包在 `.table-scroll{overflow-x:auto}` 内，`body{overflow-x:hidden}` 仅作兜底不依赖。

---

## 五、组件规范

### 5.1 顶栏 `.site-header`
- 高 56px，`--bg` + 底部 1px `--line`，`position: sticky; top:0`。
- 左：28px 徽章标（§8.1）+ 品牌字标（`DragDriveCodes`，700，18px，`--text`；`<360px` 时字标 16px、徽章 24px）。
- 右：`Last checked` 胶囊（12px，`--bg-elev-2` 底，`--ok` 圆点 + UTC 日期）。
- 移动端：只保留品牌 + 胶囊，导航折叠进页脚（本期 4 个页面，不做汉堡菜单，减少 JS）。

### 5.2 首屏 `.hero`
- 结构：状态胶囊 → H1 → 一句话结论（16px，`--text-dim`，≤2 行）→ 读数条（3 个数字）→ 码表。
- H1 例：`Drag Drive Simulator Codes (November 2026)`
- 结论句例：`5 codes confirmed by the official game page and multiple trackers. Last checked 15 Nov 2026, 08:00 UTC.`
- 读数条：`5` Active codes / `~155M` RP available / `Updated 8h ago`。数字用 `--accent`。

### 5.3 码卡 `.code-card`（核心组件）
```
┌──────────────────────────────────────────────┐
│ [CONFIRMED]  •  2 sources  •  15 Nov 2026    │
│ DRAGDRIVESIMULATORSEPTEMBER26      [ Copy ]  │
│ 35,000,000 RP                                │
└──────────────────────────────────────────────┘
```
- 卡片：`--bg-elev` 底、1px `--line`、`--radius`、padding `--sp-4`。
- 左侧 3px 竖条表示状态色（Confirmed `--ok`，Reported `--warn`）。
- 码本体：`--font-mono`，可选文本，`user-select: all`。
- 复制按钮：`--accent` 实底 + `--accent-ink` 文字，`--radius-sm`，`min-height: 40px`，`padding: 0 16px`；点击后 1.6s 内变为 `Copied ✓`，`aria-live="polite"` 播报。
- 移动端：按钮整行宽置于码下方（拇指可达）；≥640px 回到右侧。
- 奖励数值：`--text`，17px，600，后跟 `RP`（`--text-dim`，14px）。

### 5.4 步骤列表 `.steps`
- 有序 `<ol>`，序号圆 28px、`--bg-elev-2` 底 + `--accent` 数字；`counter-reset` 实现，不用图片。
- 每步一行标题 + 一行说明（≤90 字）。

### 5.5 数据表 `.code-table`（过期归档页）
- `<table>` 语义化，`<thead>` sticky，行悬停 `--bg-elev-2`。
- 列：Code（mono，可换行）/ Reward / Added / Expired / Status。
- 容器 `overflow-x:auto`，`-webkit-overflow-scrolling:touch`；移动端首列不冻结（避免复杂度）。

### 5.6 提示块 `.callout`
- 三型：`.callout--note`（`--info` 左边框）、`.callout--warn`（`--warn`）、`.callout--ok`（`--ok`）。
- 结构：左边 3px 描边 + `--bg-elev` 底 + 14px 文字；用于免责声明与「码失效怎么办」。

### 5.7 FAQ（`<details>`）
- 原生 `<details>` + `<summary>`，无 JS；summary 前用 CSS `::after` 加 `+` / `−`。
- 每个 `<details>` 对应 JSON-LD FAQPage 的一条问答，**文字必须一致**（结构化数据与可见内容不匹配会被判作弊）。

### 5.8 广告位 `.ad-slot`
- 开发期：1px 虚线 `--line-strong`，居中 12px `--text-mute` 文案 `Ad slot — reserved`，高度 250px（移动 200px）。
- 上线前通过 `body[data-ads="off"] .ad-slot{display:none}` 一键隐藏，或直接删除容器内占位文本、注入广告代码。
- 位置见阶段 2 第 5.1 节，**首屏与码卡内部绝不出现**。

### 5.9 页脚 `.site-footer`
- 两列（移动单列）：左为品牌 + 一句免责（来源与更新时间说明），右为链接（How to redeem / Expired / RP guide / Updates / About / Privacy / Contact）。
- 12–13px，`--text-mute`；顶部 1px `--line`。

### 5.10 面包屑
- 仅功能页使用：`Home / Expired codes`，12px，`--text-dim`，`aria-label="Breadcrumb"`，同步输出 BreadcrumbList JSON-LD。

### 5.11 焦点与可访问性
- `:focus-visible{outline:2px solid var(--accent); outline-offset:2px}`，禁止 `outline:none`。
- 跳转链接 `.skip-link` 置顶隐藏，聚焦时显示。
- 所有交互元素原生 `<button>` / `<a>`；不用 `div` 冒充。
- `prefers-reduced-motion` 下取消复制按钮的缩放动画。

---

## 六、动效

克制，只保留两处：
1. 复制成功：按钮背景 `--accent` → `--ok`，120ms 过渡，1.6s 后复原。
2. 卡片首次进入：`opacity 0→1` + `translateY 4px→0`，200ms，仅首屏码表，不重复触发。

无视差、无滚动动画、无骨架屏闪动（避免 CLS 与移动端卡顿）。

---

## 七、响应式规则摘要

| 断点 | 变化 |
|---|---|
| < 640px | 码卡单列、复制按钮整行宽、H1 28px、过期表横向滚动、页脚单列 |
| 640–899px | 码卡「码 + 按钮」同行、H1 32px、读数条三列 |
| ≥ 900px | 容器 1080px、导航展开为顶部横向链接、表格完整展示 |

**验收硬指标**：320px 宽度下无横向滚动条；所有文本不截断；复制按钮不小于 44px。

---

## 八、视觉资产策略

- 不使用装饰性图片 / 插画 / 库存图（性能与「假内容」双重考虑）。
- OG 分享图：由 `build.py` 用 Pillow 生成（深色底 + 品牌标 + 当前有效码首条），上线后用真实浏览器截图复核，不用合成假 UI。
- 若后续需要游戏画面，**只用官方 Roblox 游戏页可引用的素材并注明来源**，本期不做。
- Favicon：内联 SVG 字母标 `DD`（见 §8.1），零外部请求。

### 8.1 品牌标（DD 字母标）

**结论先行**：一个 40×40 的深色圆角徽章，内嵌两个用路径绘制的「D」，底部一条细基准线；强调色沿用 UI token `--accent`，徽章底沿用 `--bg-elev`。图形、SVG favicon、`favicon.ico`、OG 图四者的几何同源（`build.py` 里的 `MARK_PATH` / `mark_svg()` / `mark_data_uri()` / `draw_mark()`），不存在「网页上的 logo 和标签页里的 logo 不是同一个」的问题。

**图形构成（40×40 网格）**

| 元素 | 几何 | 依据 |
|---|---|---|
| 徽章 | `x/y = 0.8..39.2`，圆角 `r=10`，填充 `#10151D`，描边 `#C8FF3D` @38% / 1.6 | 10/40 = 25% 圆角，是「App 图标」语汇里最稳的比例：比全圆更仪表盘，比直角更友好；1px 级描边提供深浅背景下的边界 |
| 字母 D ×2 | 字干 4 宽（`6.8..10.8`），碗 `r=8`（高 16，从 y=12 到 28），内孔 `r=4.4` | 字干 : 字高 = 4 : 16 = 1 : 4，接近粗黑体（Black/Heavy）笔画比，远看是块面、近看仍是字母 |
| 双 D 间距 | `18.8 → 21.2`，即 2.4 | 2.4/8 = 0.3 倍碗半径；再窄两个 D 会粘成一个「胶囊」，再宽就不再是一个整体标记 |
| 基准线 | `x 8.8..31.2`，`y=31`，高 1.6，55% 透明度 | 对应仪表盘刻度的「地面线」，也是视觉基线：让两个字母有「压在地上」的稳定感，同时避免下缘空旷 |
| 侧边留白 | 左右各 6.8，上 12，下 8.4（含基准线） | 光学校正：字母视觉中心略高于几何中心，符合无衬线字母的 overshoot 习惯 |

**为什么这样取形**

1. **首字母双写而非全称**：品牌名 `DragDriveCodes` 三段，前两段共用 D 开头。两个 D 并置既是最短的可识别单元（32px 下仍能读出两个独立字形），也直接对应「Drag Drive」的节奏感，不需要在 28px 里塞 14 个字母。
2. **字母画成路径，不用字体**：系统字体栈在 Windows/macOS/Android/iOS 上字重和字宽差异很大，用 `<text>` 做的标在跨设备时会跳动；路径版本在任何设备上像素一致，且不产生字体请求（本项目的硬约束是零外部资源）。
3. **块面 + 内孔，而不是纯实心**：初版是实心半圆（无内孔），实测在 120px 下会读成「两个半圆」而不是字母；补 `r=4.4` 内孔后，120/44/32px 三个尺寸都能读出「DD」，16px 的 favicon 也保住了内孔的暗示（见下方对比）。
4. **斜体 / 速度线一律不用**：赛车题材最容易滑向「斜体 + 火焰 + 速度线」，那也是与竞品撞脸最快的路径。本站的速度感来自强调色的荧光绿和仪表盘式的边框，不来自字母倾斜。
5. **不复制任何现成标识**：双字母几何由本项目的网格参数唯一确定（4/8/2.4/1.6），没有引用任何游戏、车队或工具的现成 logo 造型。

**字重与间距依据**：字高 16、字干 4 是 1:4 的粗字重，这个比例在 32px 渲染时字干仍是 3.2px（≥3px，抗锯齿下不糊）；内孔直径 8.8 → 32px 时为 7px，是「能看出是孔」的下限；两个 D 间距 2.4 → 32px 时约 1.9px，刚好不至于粘连。

**尺寸与用法**

| 场景 | 尺寸 | 说明 |
|---|---|---|
| 站头 / 页脚 | 28px（<360px 视口 24px） | 与 `DragDriveCodes` 字标同行，间距由 `.brand` 的 `gap` 控制（≈8px，约 0.29 倍图标宽） |
| 浏览器标签页 | 任意（SVG） | `data:image/svg+xml` 内联，现代浏览器零请求；`favicon.ico`（16/32/48）作为退化 |
| OG 分享图 | 76px | 与 34px 字标左对齐，留 92px 起排 |
| 三档验收 | 120 / 44 / 32px | 120px 看形态与留白，44px 看触控场景（收藏夹图标、PWA），32px 看最小可辨识度 |

**语义与可访问性**：标记本身是装饰（品牌名由紧邻文字承担），所以 `aria-hidden="true" focusable="false"`，不加 `role="img"`、不加 `aria-label` —— 否则读屏会把「DragDriveCodes」念两遍。品牌链接 `<a class="brand" href="/">` 的可访问名来自其中的文本节点，不是空 svg。`favicon.ico` 作为纯装饰的浏览器 UI 资源无需替代文本。

**深浅背景**：徽章自带 `#10151D` 底 + 38% 荧光绿描边，因此在浅色背景（如浏览器书签栏、浅色主题的分享卡片）上仍是一个完整色块，不会出现「只剩绿色字母、边界消失」的情况。实测对比度：字母 `#C8FF3D` 对徽章底 `#10151D` = **15.54:1**；徽章底对浅背景 `#F4F6FA` = **16.92:1**（对纯白 18.31:1）。即无论深浅背景，字母与徽章两层各自都远超 WCAG AA。

**已验证**：120 / 44 / 32px × 深（`#0A0D12`）/ 浅（`#F4F6FA`）+ `favicon.ico` 的 16 / 32 / 48px，全部可辨认；截图见本轮交付（`logo-sizes.png`、`header-desktop.png`、`header-mobile.png`）。

---

## 九、与竞品的视觉差异（为什么能记住）

| 维度 | 竞品（IGN / Radio Times / timesaver 等） | 本站 |
|---|---|---|
| 主题 | 白底媒体模板 | 深色仪表盘 |
| 首屏 | 大图 + 导语 + 广告 | 码表直接呈现 |
| 状态表达 | 纯文字「Working / Expired」 | 颜色 + 文字双编码 + 确认日期 |
| 复制 | 纯文本/需长按选择 | 明确按钮 + 成功反馈 |
| 密度 | 段落多、需滚动 | 卡片、扫读 |
