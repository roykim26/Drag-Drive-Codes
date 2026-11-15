# Cloudflare Pages 上线清单（照着做即可，不需要运维经验）

- 日期：2026-11-15
- 目标域名：`dragdrivecodes.space`（已在用户手上，DNS 尚未接入托管）
- 产物：`04-site/dist/`，9 个 HTML + `sitemap.xml` / `robots.txt` / `ads.txt` / `og.png` / `favicon.ico` / `_headers` / `_redirects`
- 本文只是步骤，**助手未部署、未登录任何账号、未改动任何 DNS**

> 命令块前的标签说明在哪台机器上执行：**【本地】** = 你自己的 Windows；**【控制台】** = 浏览器里的 Cloudflare 后台；**【任意】** = 都行。

---

## 0. 先做一个决定：Git 接入 还是 直接上传

| | A. Git 仓库接入 | B. 直接上传 `dist` |
|---|---|---|
| 前提 | 代码必须先 commit 并 push 到 GitHub/GitLab | 不需要 git，`dist/` 是现成的 |
| 构建发生在哪 | Cloudflare 构建机（`python build.py`） | 你的电脑（已经构建好了） |
| 你能部署的内容 | Cloudflare 拉到的代码 = 你推上去的代码 | 你已经验收过的那个 `dist/` |
| 缺点 | 构建镜像的 Python 版本、Pillow 是否存在不受你控制 | 每次更新要本地重新构建 + 上传 |
| 适合 | 长期维护、想 push 即发布 | 第一次上线、想先把站挂上去 |

**你的现状**：仓库还没提交过（`git status` 里没有 commit）。这条对两条路的影响完全不同——

- **走 A**：Cloudflare 拉不到代码，必须先由你提交并推送。助手按约定不代做 commit/push。
- **走 B**：完全不受影响，`dist/` 已经在本地了。

**建议**：先走 **B** 把站点上线拿到可用 URL，再补 A 做后续自动发布。下面的步骤两条都写了，按你选的那条跳读。

---

## 1. 前提检查（3 分钟）

**【本地】**

```powershell
cd "E:\Dev_Program\drag drive simulator codes\04-site"
python build.py
```

必须看到结尾两行：

```
Build OK · 9 HTML pages · base URL https://dragdrivecodes.space
Deploy: upload dist/ as-is (Cloudflare Pages, no build step needed on CI).
```

> **只上传 `dist/`，不要上传 `dist-local/`。** 后者是双击本地预览用的扁平版（`about.html` 而不是 `about/index.html`），里面的 canonical 指向 `/about/`，上传会让 `/about/` 直接 404。

再确认 `dist/` 里有 `_headers` 和 `_redirects`（这两个文件缺失时，`_headers` 的响应头与 www 跳转都不会生效）：

```powershell
dir dist\_headers, dist\_redirects, dist\favicon.ico, dist\og.png
```

---

## 2A. 路线 A：Git 仓库接入

**【本地】先提交并推送**（这一步只能你做，涉及你的 GitHub/GitLab 账号）

```powershell
cd "E:\Dev_Program\drag drive simulator codes"
git init
git add 01-research 02-product 03-design 04-site 05-launch
git commit -m "Initial site: DragDriveCodes static build"
git remote add origin <你的仓库地址>
git branch -M main
git push -u origin main
```

> `04-site/.gitignore` 已忽略 `dist/`、凭证文件，所以推上去的是源码；Cloudflare 会自己构建。若你想让 Cloudflare 直接用你构建好的产物，把 `dist/` 一起提交（不推荐，容易和源码不同步）。

**【控制台】** Workers & Pages → Create → Pages → Connect to Git → 选仓库，然后按下表填：

| 设置项 | 值 |
|---|---|
| Project name | `dragdrivecodes`（决定预览域 `dragdrivecodes.pages.dev`，可改） |
| Production branch | `main` |
| Framework preset | **None** |
| Build command | `python build.py` |
| Build output directory | `dist` |
| Root directory | `04-site`（若仓库根目录就是 `04-site` 的内容，则留空） |
| Environment variables | 无 |

**【控制台】构建日志要看的两行**：首行的 `python --version`，以及结尾有没有 `! Pillow not installed, skipping og.png`。

- 如果出现 Pillow 警告：`og.png` 与 `favicon.ico` 不会生成，页面本体仍然可用（favicon 会退化到内联 SVG，现代浏览器没问题），但社交分享图会 404。修法二选一：在 Build command 前加 `pip install pillow && python build.py`（需要构建镜像允许访问 PyPI），或干脆改走路线 B。

---

## 2B. 路线 B：直接上传 `dist`

**【本地】** 需要 Node 18+ 和一次浏览器登录（`wrangler login` 会打开浏览器让你点授权，这一步是账号授权，只能你做）：

```powershell
cd "E:\Dev_Program\drag drive simulator codes\04-site"
npx wrangler@latest login
npx wrangler@latest pages deploy dist --project-name dragdrivecodes
```

输出结尾会给一个 `https://<hash>.dragdrivecodes.pages.dev` 预览地址，先打开它验收（见第 6 步），再挂域名。

> 未来更新站点：本地 `python build.py` → 同一条 `pages deploy` 命令。想自动化再回去做路线 A。

---

## 3. 绑定自定义域名

**【控制台】** 项目 → Custom domains → Set up a custom domain，依次添加两个：

1. `dragdrivecodes.space`（裸域，主域）
2. `www.dragdrivecodes.space`（用于把 www 301 到裸域，配合 `dist/_redirects` 已经写好的规则）

添加后会显示一个 **CNAME 目标值**（形如 `dragdrivecodes.pages.dev`）和一个状态（`Initializing` → `Active`）。**具体值以控制台当时显示的为准，本文不写死。**

---

## 4. DNS 该改什么（两种方式，二选一）

### 方式一：把 DNS 托管迁到 Cloudflare（推荐）

- **【控制台】** 首页 Add a site → 输入 `dragdrivecodes.space` → 选 Free 计划 → Cloudflare 会给你 **两个 nameserver 地址**。
- **【注册商后台】** 把域名的 NS 改成这两个值。**具体是哪两个，以你要改的那一刻控制台显示为准**，不要照抄别人的例子。
- 迁完后 Cloudflare 会自动建好指向 `dragdrivecodes.pages.dev` 的 CNAME（裸域走 CNAME flattening，不需要你手填 IP）。

### 方式二：保留现有 DNS 服务商

| 记录 | 名称 | 值 | 说明 |
|---|---|---|---|
| CNAME | `www` | `dragdrivecodes.pages.dev` | 一般 DNS 服务商都支持 |
| CNAME | `@`（裸域） | `dragdrivecodes.pages.dev` | **多数服务商的裸域不支持 CNAME**，需要 ALIAS / ANAME / CNAME flattening；不支持就只能先只用 www，再在别处做裸域 301 |

**没有 A 记录可用**：Cloudflare Pages 不提供固定 IP，任何让你填 IP 的教程都是错的/过时的。

> 判断迁 NS 是否生效：**【本地】** `nslookup -type=ns dragdrivecodes.space 1.1.1.1`，返回的 NS 里出现 `ns.cloudflare.com` 就说明已经生效（可能要等几分钟到几小时）。

---

## 5. HTTPS、跳转、缓存、压缩（哪些要动，哪些别动）

| 项 | 默认行为 | 你要做什么 |
|---|---|---|
| 证书 | 域名 `Active` 后自动签发（Universal SSL） | 什么都不用做，等状态变绿 |
| 强制 HTTPS | 默认不强制（http 仍可访问） | **要动**：SSL/TLS → Edge Certificates → 打开 **Always Use HTTPS** |
| HSTS | 默认关 | **先别开**。等站点稳定运行一两周、确认所有子域都上 https 再考虑，开错要等一年才能回退 |
| 最小 TLS 版本 | 1.2 | 不用动 |
| Brotli 压缩 | 默认开启 | 不用动 |
| 缓存 | HTML 每次回源校验，静态资源走 `_headers` 里的 `Cache-Control` | 不用动；**不要**加 "Cache Everything" 规则，否则改完码表用户还看到旧版 |
| 自动 HTTPS 重写 | 可开 | 站点没有混合内容，开了也无害，可选 |

---

## 6. 上线后自测（10 分钟，逐条对结果）

**【本地】** 全部命令在 PowerShell 里跑，`curl` 是 Windows 10+ 自带的。

### 6.1 状态码

```powershell
$H = @("https://dragdrivecodes.space/",
       "https://dragdrivecodes.space/how-to-redeem/",
       "https://dragdrivecodes.space/expired-codes/",
       "https://dragdrivecodes.space/sitemap.xml",
       "https://dragdrivecodes.space/robots.txt",
       "https://dragdrivecodes.space/ads.txt",
       "https://dragdrivecodes.space/og.png",
       "https://dragdrivecodes.space/favicon.ico",
       "https://dragdrivecodes.space/this-page-does-not-exist")
foreach ($u in $H) { $r = curl.exe -s -o NUL -w "%{http_code}" $u; "$r  $u" }
```

期望：前 8 条 `200`，最后一条 **`404`**（且返回的是你站内的 404 页面，不是 Cloudflare 的默认页）。

### 6.2 内容对得上

```powershell
curl.exe -s https://dragdrivecodes.space/ | Select-String "Drag Drive Simulator Codes"
curl.exe -s https://dragdrivecodes.space/sitemap.xml | Select-String "dragdrivecodes.space"
curl.exe -s https://dragdrivecodes.space/robots.txt | Select-String "Sitemap:"
```

三条都要有输出；sitemap 里若出现 `dragdrivecodes.com` 说明部署的是旧产物。

### 6.3 响应头（验证 `_headers` 生效）

```powershell
curl.exe -sI https://dragdrivecodes.space/ | Select-String "x-frame-options|x-content-type|referrer-policy|permissions-policy"
```

四条都应出现。若一条都没有 → `dist/_headers` 没被上传，回去检查第 1 步。

### 6.4 www 跳转

```powershell
curl.exe -sI https://www.dragdrivecodes.space/ | Select-String "HTTP/|location"
```

期望 `301` + `location: https://dragdrivecodes.space/`。若 www 直接 200 或超时 → www 的自定义域没加，或 `_redirects` 没生效。

### 6.5 手工点一遍

- 手机开无痕模式访问首页，点一次 **Copy code**，确认变成 `Copied` 且剪贴板里有码。
- 点一张卡片的 **Report a problem with this code**，确认弹出的邮件草稿里收件人是 `hello@dragdrivecodes.space`（**这个邮箱此时还没开通收信，见第 7 步**）。
- 浏览器标签页应显示 DD 徽章图标。

### 6.6 收尾

- 【控制台】Speed → Optimization 里确认没有开启会改写 HTML 的选项（Rocket Loader 之类，本站不需要）。
- 到 Google Search Console 添加属性 `https://dragdrivecodes.space/` → 验证（DNS TXT 最省事）→ 提交 `sitemap.xml`。

---

## 7. 别忘了这两件事

1. **邮箱**：`data/site.json` 的 `contact_email` 现在是 `hello@dragdrivecodes.space`，但**没有任何邮箱在收信**。要么在 Cloudflare Email Routing / 你的邮箱服务里真的开通这个地址，要么改成你能收信的地址后重新 `python build.py` 再部署。
2. **`ads.txt`**：目前是纯注释占位。AdSense 审核通过后，把 `google.com, pub-XXXX, DIRECT, f08c47fec0942fa0` 那行填进 `build.py` 里的 `ads.txt` 写盘段落，重建再部署。

---

## 8. 回滚

- 路线 B：重新上传上一个版本的 `dist/`（建议每次部署前把 `dist` 复制一份留档）。
- 路线 A：Cloudflare 项目 → Deployments → 找到上一个成功部署 → `Rollback`。
- DNS 出问题：把 NS 改回注册商原来的值即可，证书和站点都还在。
