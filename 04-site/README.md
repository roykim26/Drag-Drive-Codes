# DragDriveCodes — 可部署静态站点

纯前端静态站，无框架、无外部请求。9 个 HTML 页面 + sitemap + robots + ads.txt 占位。

站点域名 `https://dragdrivecodes.space`（唯一来源：`data/site.json` 的 `base_url`；代码里没有硬编码域名，换域名只改这一处）。

> **本地预览：双击 `dist-local/index.html`，不要双击 `dist/index.html`。**
> `dist/` 是部署产物，内部链接是 `/about/` 这种根绝对路径 + 目录索引形式；`file://` 协议下它会解析到 `E:\about\` 并且不认目录索引，所以逐个链接都会 `ERR_FILE_NOT_FOUND`。这是静态站的正常表现，不是坏链。`dist-local/` 是同一套页面换成了扁平文件名（`about.html`）+ 相对链接，双击即可离线浏览全站；canonical / OG / sitemap 仍是生产环境的绝对地址，不会被本地预览污染。想看与生产完全一致的效果，用 `python -m http.server 8000 --directory dist`。

## 目录

```
04-site/
├─ build.py            构建脚本（唯一需要运行的命令，无第三方依赖）
├─ data/
│  ├─ site.json        品牌名、base URL、联系邮箱、检查日期、广告位开关
│  └─ codes.json       所有兑换码（唯一数据源：有效 / 待确认 / 过期）
├─ scripts/
│  ├─ patrol.py        官方接口每日巡检（标准库 only，只报告不写码表）
│  └─ gsc_submit.py    GSC sitemap 提交（可选；需要服务账号，当前未验证）
├─ dist/               构建产物（可直接部署，勿手改）
├─ dist-local/         本地双击预览用（扁平 .html + 相对链接，不部署）
├─ .gitignore          忽略 dist/、dist-local/、凭证文件、本地预览截图
└─ preview/            本地实测截图（移动端 375px / 桌面 1280px）
```

`dist/` 里最终包含：9 个 HTML、`sitemap.xml`、`robots.txt`、`ads.txt`、`og.png`、`favicon.ico`、`_headers`、`_redirects`。其中 `_headers` / `_redirects` 是 Cloudflare Pages 的约定文件（构建时生成，不要手写进 `dist/`）。`dist-local/` 只有 9 个扁平 HTML + `favicon.ico` + `og.png`，**永远不要上传它**（里面的 canonical 指向生产域名，扁平文件名与 canonical 路径不一致）。

## 构建与本地预览

```powershell
cd "E:\Dev_Program\drag drive simulator codes\04-site"
python build.py
python -m http.server 8123 --directory dist
# 浏览器打开 http://127.0.0.1:8123/
```

`python build.py` 一次产出两套：

| 目录 | 内部链接 | 用途 |
|---|---|---|
| `dist/` | `/about/` 绝对路径 + 目录索引 | **上线用**，与 canonical / sitemap 完全一致 |
| `dist-local/` | `about.html` 相对路径 + 扁平文件 | **本地双击用**，`file://` 下可正常跳转 |

不启动服务、只想快速看一眼：双击 `dist-local/index.html`。要看与线上一致的表现（含 `_headers`、目录索引、404 状态码），用上面的 `http.server`。

要求 Python 3.9+。生成 OG 图需要 Pillow（`pip install pillow`），缺失时脚本会跳过并继续。

## 更新兑换码（每月/每次更新必做）

只改 `data/codes.json`，然后重新 `python build.py`，全站自动同步：

1. 把失效码从 `active` 移到 `expired["2026"]`（保留 `reward`），同时从 `active` 删除。
2. 新码加入 `active`，必须填：`code`、`reward_min`、`reward_max`、`status`（`confirmed` / `reported`）、
   `added`、`last_verified`、`in_game_verified`（没实测过就写 `null`）、`sources`（数组）、`note`。
3. 更新 `data/site.json` 的 `last_checked`（标题月份、页头胶囊、JSON-LD `dateModified`、sitemap `lastmod` 都取这个值）。
4. 如官方发布新版本，同步改 `data/site.json` 的 `game.version` 与 `/updates/` 页面文案（`build.py` 内 `page_updates`）。

**核验规则**：官方页出现且 ≥2 个独立来源 → `confirmed`；官方页 + 游戏内实测通过也可直接 `confirmed`（速度快于等二级站跟进）；仅 1 个来源 → `reported`；≥2 个来源标过期 → 移入归档。不确定的数字用区间，不写单一精确值。

**数量词不要再写死**：正文里的 "five codes" 一类表述由 `count_word(len(ACTIVE))` 生成，新增/删除码后自动变化。`build.py` 会在写文件前跑 `validate_data()` + `validate_copy()`，出现重复码、日期倒挂、`confirmed` 来源不足、正文数量词与 `len(ACTIVE)` 不一致、奖励区间非法、状态与列表不一致时**直接构建失败**并打印原因（`dist/` 保持上一版）。

## 内测证据（`in_game_verified`）

只有满足三条才填日期：真实账号在游戏内兑换成功、RP 增加额与卡片一致、已记录日期。填了之后卡片会多出蓝色 `In-game tested <date>` 徽标；不填则不显示。**不要因为"看起来没问题"就补一个日期**——这条是站点唯一比追踪站更强的东西。

## 品牌标（logo）

内联 SVG，40×40 网格，零图片请求、零外部字体：字母「DD」用 `<path>` 画，不依赖任何设备上的字体。同一几何有三个消费者，全部由 `build.py` 生成：

| 消费者 | 生成方式 | 位置 |
|---|---|---|
| 站头 / 页脚 | `mark_svg(28)` → 内联 `<svg class="brand__mark" aria-hidden="true">` | 每页 header 与 footer |
| 浏览器标签页 | `mark_data_uri()` → `data:image/svg+xml,...` 的 `rel="icon"` | `<head>`，现代浏览器零请求 |
| 老浏览器 / 部分爬虫 | `build_icon()` → Pillow 光栅 `favicon.ico`（16/32/48） | `dist/favicon.ico` |
| 社交分享 | `draw_mark()` 画进 `og.png` | `dist/og.png` |

语义：图形是装饰，配 `aria-hidden="true"` + `focusable="false"`；可读名称由紧邻的文字 `DragDriveCodes` 提供（品牌链接的可访问名来自这段文字，不是空 svg）。**不要**给 `svg` 加 `role="img"` 或 `aria-label`，否则读屏会念两遍品牌名。

设计说明与取形依据见 [03-design/UI设计.md](../03-design/UI设计.md) 的「品牌标」一节。

## 广告位（配置驱动，默认关闭）

广告不是"运行时隐藏"，而是**构建期决策**：`build.py` 读 `data/site.json` 的 `ads`，关闭时连 CSS 规则都不输出，所以产物里没有任何可被误显示的空位。

```json
"ads": {
  "enabled": false,
  "client": "",
  "slots": {
    "home-after-codes": "", "home-end": "", "redeem-mid": "",
    "expired-after-tables": "", "rp-mid": "", "updates-mid": ""
  }
}
```

| 状态 | 产物里出现什么 |
|---|---|
| `enabled: false`（默认） | 没有 `.ad-slot` 容器、没有 `ins.adsbygoogle`、没有 `adsbygoogle.js`、没有预留高度、没有 `data-ads` 属性；`ads.txt` 保持无 pub-id 的注释占位 |
| `enabled: true` + 6 个 slot 齐全 | 每页 `<head>` 引一次 `adsbygoogle.js?client=…`；对应位置输出 `<div class="ad-slot" data-slot="…"><ins class="adsbygoogle" data-ad-client data-ad-slot data-ad-format="auto" data-full-width-responsive="true"></ins><script>push({})</script></div>`；`ads.txt` 写入 `google.com, pub-…, DIRECT, f08c47fec0942fa0` |

六个位置与页面：

| `data-slot` | 页面 | 落点 |
|---|---|---|
| `home-after-codes` | 首页 | 码表之后、兑换步骤之前 |
| `home-end` | 首页 | FAQ 之后、来源之前 |
| `redeem-mid` | how-to-redeem | 快速路径提示之后 |
| `expired-after-tables` | expired-codes | 两张归档表之后 |
| `rp-mid` | rp-guide | 首个 callout 之后 |
| `updates-mid` | updates | 更新时间表之后 |

**构建期校验**：`enabled: true` 时 `validate_ads()` 会检查 `client` 必须是 `ca-pub-` + 16 位数字、每个位置都必须有纯数字 slot；任一项不合规直接 `BUILD FAILED` 并逐条打印字段名，`dist/` 保持上一版。**没有**真实广告代码或示例 pub-id 写在仓库里。

**预留高度与 CLS**：启用态 CSS 用 `.ad-slot::before{min-height:200px}`（`≥640px` 时 250px）先把高度占住，广告填充时不再顶动下方内容；关闭态这段 CSS 整段不输出，页面零留白。上线后用 PageSpeed Insights / CrUX 看移动端 CLS，再在 Chrome DevTools Performance 里对照"有广告 / 无广告"两次 trace 的 layout shift 区域，确认广告位是位移来源而不是受害者；如果 CLS 变差，优先调整 `::before` 的 `min-height` 使其接近实际填充高度。

**同意管理（未实现，上线前必须处理）**：AdSense 对 EEA / UK / 瑞士用户要求经 Google 认证的 CMP 做同意收集；当前站点没有 Cookie 条、也没有 CMP，因此在上述地区投放是不合规的。接广告前要么在 AdSense 后台启用 Google 的同意管理平台，要么接入其他认证 CMP，并同步更新 `/privacy/` 文案。

## 每日巡检（`scripts/patrol.py`，只报告不写站）

拉 Roblox 官方 games API 快照 → 与上次快照 diff `updated` 与 `description` → 正则抽候选码 → 输出「疑似新码 / 疑似失效」清单。**只标需人工确认，绝不自动改 `codes.json` 或任何页面。**

```powershell
python scripts\patrol.py --dry-run          # 不写快照、不发通知，只打印将要做什么
python scripts\patrol.py --snapshot-file x.json   # 离线：用本地 JSON 代替联网
python scripts\patrol.py                    # 正常跑（写快照 + 报告，可选 webhook）
```

| 项 | 说明 |
|---|---|
| 依赖 | 仅 Python 标准库（`urllib`/`json`/`re`/`hashlib`），无 pip 安装 |
| 状态目录 | Linux 默认 `/var/lib/ddc-patrol`，Windows 默认 `~/.ddc-patrol`，可用 `DDC_STATE_DIR` 覆盖 |
| 目录权限 | `/var/lib/ddc-patrol` → `0750 ddc:ddc`；快照 `snapshots/*.json` 与 `state.json` → `0640 ddc:ddc`；配置 `/etc/ddc-patrol/patrol.env` → `0640 root:ddc` |
| 文件布局 | `snapshots/YYYY-MM-DDTHHMMZ.json`、`snapshots/latest.json`、`reports/YYYY-MM-DD.md`、`state.json`；`--keep 90` 清理 90 天前快照 |
| 告警 | webhook 只从环境变量 `DDC_WEBHOOK_URL` 读（**不写死、不入库**）；未设置时打印 `notify: skipped` 并照常落盘。按 host 自动区分 Discord / 飞书 / 通用 JSON |
| 失败行为 | HTTP 失败重试 3 次（2/4/8s 退避）；全程失败退出码 30，静默 >36h 退出码 40，有候选退出码 10（systemd 里用 `--exit-zero`） |
| 首次运行 | 只建基线不告警，报告里的候选码标为「基线候选（仅供参考）」 |

部署到服务器（systemd timer、时区、验证步骤）见 [05-launch/ECS每日巡检部署方案.md](../05-launch/ECS每日巡检部署方案.md)。

## 部署（Cloudflare Pages）

- 构建命令：`python build.py`
- 输出目录：`dist`
- 构建环境：需要 Python 3.9+；**没有第三方依赖**（Pillow 可选，只在生成 `og.png` / `favicon.ico` 时需要）。Cloudflare 的构建镜像默认有 Python 3，若不想在 CI 里跑 Pillow，把 `dist/` 直接上传也完全等效。
- 无需环境变量，无服务端逻辑。
- 404：Pages 自动使用 `dist/404.html`。
- `dist/_headers`：`X-Content-Type-Options`、`Referrer-Policy`、`X-Frame-Options`、`Permissions-Policy` + 静态资源缓存。**故意没有 CSP**——页面样式和脚本都是内联的，favicon 是 `data:` URI，写错的 CSP 会静默弄坏复制按钮；要加就先在预览部署上验证。
- `dist/_redirects`：`www` → 裸域 301。**前提**是把 `www.dragdrivecodes.space` 也加成同一个 Pages 项目的自定义域，否则该主机根本不会解析到 Pages，规则永远不会被触发。

### 部署操作清单（全部需要你亲手做，助手不执行）

前置：以下任何一步都涉及账号或 DNS，本仓库**不包含**也不应包含任何凭证。

1. **推代码**：把 `04-site/` 提交到 GitHub/GitLab（Pages 支持直连仓库），或本地 `python build.py` 后把 `dist/` 用 `wrangler pages deploy` 上传。
2. **建 Pages 项目**：Cloudflare 控制台 → Workers & Pages → Create → Pages → 连仓库；Framework preset 选 **None**；
   Build command `python build.py`；Build output directory `dist`；Root directory `04-site`（若仓库根就是 04-site 则留空）。
3. **先看预览域**：项目会得到一个 `<project-name>.pages.dev`。先在这个域上验收（含 `_headers` 是否生效、复制按钮是否正常），再挂正式域名。
4. **加自定义域**：项目 → Custom domains → 添加 `dragdrivecodes.space`，再添加 `www.dragdrivecodes.space`。
5. **改 DNS**（记录值以 Cloudflare 控制台当时显示为准，**不要手填 IP**——Pages 没有固定 A 记录 IP）：

   | 类型 | 名称 | 目标 | 代理 | 何时需要 |
   |---|---|---|---|---|
   | NS | `@` | Cloudflare 分配的两个 nameserver | — | 只有把 DNS 托管迁到 Cloudflare 时才改；值看控制台「概览」页，**以控制台显示为准** |
   | CNAME | `@`（裸域） | `<project-name>.pages.dev` | 已代理（橙云） | 添加自定义域后由 Cloudflare 自动创建，**以控制台显示为准** |
   | CNAME | `www` | `<project-name>.pages.dev` | 已代理（橙云） | 同上；配合 `_redirects` 做 301 |
   | TXT | `_cf-custom-hostname.<domain>` 之类 | 控制台给出的校验值 | — | 若控制台要求域名所有权校验，按提示添加 |

   若你不想迁 NS，而是保留原注册商的 DNS：裸域必须用支持 CNAME/ALIAS-flattening 的解析服务才能指向 `pages.dev`，否则只能先挂 `www` 再把裸域 301 过去。这条策略请以 Cloudflare 当前文档为准。
6. **等证书**：自定义域显示 Active 且证书签发完成（通常几分钟）后，`https://dragdrivecodes.space` 才可用。
7. **回填 GSC**：在第 5 步生效后，做 Search Console 验证并提交 `https://dragdrivecodes.space/sitemap.xml`（或跑 `python scripts/gsc_submit.py`）。
8. **邮箱**：`contact@dragdrivecodes.space`（通用）与 `abuse@dragdrivecodes.space`（法律/版权/内容投诉）已通过 Cloudflare Email Routing 转发到个人邮箱，均为 Active。地址配置在 `data/site.json` 的 `contact_email` / `abuse_email`，构建期会校验域名是否为本站域名。

## 上线还差的条件与授权（由你决定）

1. DNS 已接入 Cloudflare（NS 为 `curt` / `daphne`），`dragdrivecodes.space` 与 `www` 已绑定 Pages 且 Active；`www` 通过 Redirect Rule 301 到 apex。
2. 托管账号（Cloudflare Pages 免费额度足够）。
3. 联系邮箱已就绪：`contact@` 与 `abuse@` 经 Cloudflare Email Routing 转发，只负责收信，回复从个人邮箱发出。
4. Google Search Console 验证 + 提交 `sitemap.xml`（脚本已备：`python scripts/gsc_submit.py --check`）。
5. 分析工具（建议 Cloudflare Web Analytics，无 Cookie 免同意条；GA4 需加同意提示）。
6. AdSense：账号申请、审核通过后把 pub-id 写入 `dist/ads.txt` 并插入广告代码。**当前只有 6 个内容页，审核偏薄，建议扩到 15+ 页再申请。** 受众含未成年人，勿开个性化定向、勿使用儿童定向标记。
7. 广告位已改为**配置驱动**（`data/site.json` 的 `ads`）。默认关闭时不输出任何广告相关字节；接入流程见下一节「广告位（配置驱动）」。

## GSC 自动提交 sitemap（脚本可用，链路未验证）

```powershell
python scripts\gsc_submit.py --check     # 只查前置条件，不发请求
python scripts\gsc_submit.py --dry-run   # 打印将要发送的 PUT，不发
python scripts\gsc_submit.py             # 真的提交（需要凭证 + 已上线）
```

凭证读取顺序（只读，不写回仓库或 `dist/`）：

1. 环境变量 `GSC_SERVICE_ACCOUNT_JSON`（原始 JSON 或文件路径）
2. 环境变量 `GSC_SERVICE_ACCOUNT_FILE`（文件路径）
3. 本地文件 `gsc-service-account.json`（已在 `.gitignore`）

需要 `pip install google-auth`。**当前状态：域名已注册但站点未上线**（`https://dragdrivecodes.space/sitemap.xml` 仍不可达）、没有 GSC 属性验证、没有服务账号密钥。`--check` 现在会返回退出码 1 并打印 `NOT VERIFIED`，这是预期行为，不是脚本坏了。脚本的 base URL 从 `data/site.json` 读取，没有硬编码域名。

域名上线后需要人工完成：建属性并验证 → 建服务账号并启用 Search Console API → 把服务账号邮箱加为该属性的用户 → 把密钥交给上面三种方式之一。

## 自测结果（2026-11-15）

**构建期断言**：`data validation OK (49 unique codes, 5 active)` → `copy validation OK (number words match 5 active codes)`。7 类坏数据（重复码、日期倒挂、单来源 confirmed、奖励区间倒挂、状态与列表不一致、实测日期非法、正文数量词不一致）均已实测会让构建以退出码 1 失败，且失败时 `dist/` 保留上一版。

**静态检查**（9 页）：title/description/canonical/OG 齐全，description 长度 125–162 字符，每页唯一 H1，JSON-LD 可解析，内部链接无死链，sitemap 8 条 URL 全部可解析，robots 含 Sitemap 指令 — 全部通过。

**浏览器实测**（headless Chrome + CDP，9 页 × 3 视口 = 27 组 + 8 页 × 320/360 窄屏 iframe）：
- 控制台错误 0、页面异常 0、资源加载失败 0，`failures: []`。
- 复制按钮：点击后文案变为 `Copied`、背景变绿、`aria-live` 播报完整码值，1.6s 后复位；按钮高度 44px。
- 举报入口：首页 6 张码卡 → 6 个 `mailto:` 链接，主题预填 `Code report: <CODE>`，移动端高度 44px。
- 横向溢出：27 组全部 `scrollWidth == innerWidth`；320/360px 实测无溢出元素。
- 实测徽标：线上 0 个（没有任何 `in_game_verified` 日期，符合事实）。
- 首屏（375px）在 1 屏内呈现 H1 + 结论 + 统计 + 首个码卡；首屏无广告位。

**性能**：每页 15–29KB，CSS/JS 全内联，零外部字体、零图片请求（OG 图仅供社交分享，favicon 走 `data:` URI，均不参与页面渲染）。

**域名切换核查**（`dragdrivecodes.com` → `dragdrivecodes.space`）：9 页的 canonical / `og:url` / `og:image` / `twitter:image`、sitemap 8 条 `<loc>`、`robots.txt` 的 Sitemap 行、`ads.txt`、JSON-LD `@id`、`mailto:` 全部为新域名；对 `dist/` 全量文本扫描 `dragdrivecodes.com` 命中 **0** 次。

**品牌标尺寸核验**：内联 SVG 在 120 / 44 / 32px、深（`#0A0D12`）浅（`#F4F6FA`）两种背景、以及 `favicon.ico` 的 16 / 32 / 48px 下均能读出「DD」，无模糊、无裁切。

**本地双击（`file://`）核验**：`dist-local/` 九个页面逐个直接打开、以及从首页点击 8 个导航链接，全部正常渲染（背景 `rgb(10,13,18)`、内联样式表 1 个、无控制台错误、无横向溢出），复制按钮 `Copy code → Copied` 可用，页脚链接全为相对路径。`dist/` 在 `file://` 下**故意不可用**（根绝对路径会解析到 `E:\`），其链接形式与 canonical 保持一致，供线上使用。

## 技术 SEO 落地清单

| 项 | 状态 |
|---|---|
| 语义化 HTML（header/main/footer/nav/article/table/caption） | 已做 |
| 每页唯一 title + meta description | 已做 |
| canonical（自引用绝对 URL） | 已做 |
| `lang="en"` + viewport | 已做 |
| Open Graph / Twitter Card | 已做（og.png 1200×630） |
| JSON-LD：Organization、WebSite、WebPage、ItemList、FAQPage、BreadcrumbList | 已做 |
| 面包屑（视觉 + 结构化数据） | 功能页已做 |
| 内链（首页 ↔ 4 个功能页 ↔ About） | 已做 |
| sitemap.xml（lastmod 取自数据文件） | 已做 |
| robots.txt + sitemap 引用 | 已做 |
| 404 页面 + noindex | 已做 |
| 移动端适配（320–1280 实测） | 已做 |
| 性能（无外部请求、无 CLS 资源） | 已做 |
| hreflang / 多语言 | 本期不做（按定位要求）；结构为平级目录，后续可加 `/es/` |

## 不要做的事

- 不要手改 `dist/`，重新构建会覆盖。
- 不要在码表中插入未经核验的码——`confirmed` 标签是站点唯一信任资产。
- 不要把广告位放到首屏或码卡之间。
