# 每日巡检脚本 · 东京 ECS 部署方案（只出方案，未连服务器、未装任何东西）

- 日期：2026-11-15
- 目标机器：阿里云**国内站账号**购买的**东京地域**节点（操作系统、Python 版本、是否有公网 IP 均未知，见 §0）
- 上游流程依据：`02-product/码源获取与更新机制.md`（码源清单、三级核验、节奏）
- 本文不含真实凭证、不连接任何主机；所有命令都会标明 **【服务器】** 或 **【本地】**

> **脚本状态（2026-11-16 核对）**：巡检脚本已实现并自测通过，路径 `04-site/scripts/patrol.py`（仅标准库，无需 pip）。本文 §4.4 的骨架已删除，实际参数以脚本 `--help` 为准：`--once`、`--dry-run`、`--snapshot-file`、`--base-dir`、`--codes-file`、`--universe`、`--keep`、`--alert`、`--no-notify`、`--exit-zero`、`--json`。退出码只有三个：**0 正常、10 有候选待确认、30 拉取/解析失败**。文档旧版写的「40 静默超 36h」在脚本里**不存在**：静默 >36h 只在成功运行里追加一条提醒并推 webhook，退出码不变。目录不可写属于未捕获异常，会以 Python 的 1 退出并打印 traceback，不是 40。

---

## 0. 先确认三件事（登录服务器后 30 秒）

**【服务器】**

```bash
cat /etc/os-release | head -3
python3 --version
timedatectl
```

| 要确认的 | 为什么 |
|---|---|
| 发行版 | 决定包管理（`apt` / `dnf`）、Python 默认版本、systemd 版本 |
| `python3 --version` | 本方案只用标准库，最低要求 **3.9+**（3.8 已 EOL，且 `zoneinfo` 需要 3.9） |
| `timedatectl` 输出里的 `Time zone` | **最关键**。阿里云国内站账号的海外节点，镜像时区可能是 `UTC` 也可能是 `Asia/Shanghai`，取决于你选的镜像，**不能假设**。所有定时表达式按这里的结果写 |

> 时区结论先记下来：若显示 `UTC` → 用 §3 的 UTC 表达式；若显示 `Asia/Shanghai` → 必须先改（见 §3.1），否则「每天 09:10」会变成北京时间 09:10，也就是东京时间 10:10、UTC 01:10。

---

## 1. 运行环境

| 项 | 结论 |
|---|---|
| Python | 3.9+，系统自带即可 |
| 第三方依赖 | **零**。只用 `urllib.request` / `json` / `re` / `difflib` / `pathlib` / `argparse` / `hashlib` / `datetime` |
| 虚拟环境 | 不需要（无依赖就没有隔离问题，也少一个每月要重建的 venv） |
| 网络出口 | 服务器需要能访问 `games.roblox.com`（东京节点通常可达；若不通，见 §6 的失败处理） |
| 磁盘 | 快照 + 报告都是几十 KB/天，预留 100 MB 足够 |

**为什么不装依赖**：这台机器只做"取快照 + 出清单"，不做构建。少一个包就少一次 `pip` 升级把脚本跑挂的机会。

---

## 2. 目录、用户与权限（一次建好，之后不用动）

**【服务器】**（需要 root 或 sudo）

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ddc
sudo install -d -m 0755 -o root -g root /opt/ddc-patrol
sudo install -d -m 0750 -o ddc  -g ddc  /var/lib/ddc-patrol
sudo install -d -m 0750 -o ddc  -g ddc  /var/lib/ddc-patrol/snapshots
sudo install -d -m 0750 -o ddc  -g ddc  /var/lib/ddc-patrol/reports
sudo install -d -m 0750 -o root -g ddc  /etc/ddc-patrol

# 把本地 data/codes.json 上传到 /tmp 后执行（见 §8），权限必须是 root:ddc 0640
sudo install -m 0640 -o root -g ddc /tmp/codes.json /etc/ddc-patrol/codes.json
```

| 路径 | 内容 | 权限 / 属主 | 为什么不放进仓库 |
|---|---|---|---|
| `/opt/ddc-patrol/patrol.py` | 脚本本体 | `0755 root:root` | 代码可以进仓库，但部署副本由你手动放，避免"服务器上跑的版本和仓库里不一致却没人发现" |
| `/opt/ddc-patrol/run-patrol.sh` | wrapper（固定 PATH / umask / `--codes-file`） | `0755 root:root` | unit 与 cron 共用同一套参数，排障时也跑同一条命令 |
| `/etc/ddc-patrol/patrol.env` | 只放 `DDC_WEBHOOK_URL` | **`0640 root:ddc`** | 这是密钥。unit 文件通常是 644 全局可读，**绝不能**把 URL 写进 unit |
| `/etc/ddc-patrol/codes.json` | 码表只读副本，用于集合差 | **`0640 root:ddc`** | 服务器不存站点源码；每次改完码表手动同步一份 |
| `/var/lib/ddc-patrol/snapshots/` | 每日原始 JSON | `0750 ddc:ddc` | 快照属于运行数据，不该 commit |
| `/var/lib/ddc-patrol/reports/` | 每日人读清单（md） | `0750 ddc:ddc` | 同上 |
| `/var/lib/ddc-patrol/state.json` | `last_success`、上次快照 sha | `0640 ddc:ddc` | 用于"连续失败/静默"判断 |

> `ddc` 是 `--system --nologin` 账号：不能登录、没有家目录、只用来跑这一个任务。就算脚本被投毒，能碰到的也只有上面两个目录。

---

## 3. 调度：systemd timer（推荐） vs cron

| | systemd timer | cron |
|---|---|---|
| 时区控制 | `OnCalendar` **可以显式带时区后缀**（`… UTC` / `… Asia/Tokyo`），与机器时区解耦 | 只能用机器本地时区，改时区会影响整机 |
| 漏跑补偿 | `Persistent=true`，关机期间错过的那次开机后补跑 | 没有 |
| 日志 | 自动进 journald，`journalctl -u` 直接查 | 要自己重定向，容易忘 |
| 失败告警 | `OnFailure=` 直接挂一个告警 unit | 只能靠 `MAILTO` 或包装脚本 |
| 环境变量 | `EnvironmentFile=` 精确控制 | crontab 里写明文（谁都能 `crontab -l`） |

**结论：用 systemd timer。** 只有当你的镜像没有 systemd（极少见）时才退回 cron，写法见 §3.4。

### 3.1 先把时区钉死

**【服务器】**

```bash
sudo timedatectl set-timezone UTC
timedatectl | grep "Time zone"
```

理由：站点的「Last checked」、sitemap 的 `lastmod`、快照文件名**本来就用 UTC**（`data/site.json` 的 `last_checked` 是 UTC 日期）。机器也统一 UTC，日志、文件名、cron 表达式就只有一套坐标，不会出现"报告日期和站点日期差一天"。

> 如果你坚持让机器显示 JST：`sudo timedatectl set-timezone Asia/Tokyo`。那么下面所有 `UTC` 后缀都要删掉或改成 `Asia/Tokyo`，并且把 `00:10` 改成 `09:10`。

### 3.2 要跑在几点

**每日 00:10 UTC**（= 东京 09:10 = 北京 08:10）。

- 00:10 UTC 在 UTC 日切之后 10 分钟，跑完正好给站点一个"新的一天"的最新快照，和 `last_checked` 的日期口径一致。
- 一天一次符合机制文档定的节奏；官方大版本更新当天可以手动多跑一次（`systemctl start ddc-patrol.service`），不需要改定时器。

### 3.3 单元文件（完整可用）

**先建 wrapper**：unit 里只调用 wrapper，参数集中在 wrapper 一处，手工排障时直接跑同一条命令。

**【服务器】** 新建 `/opt/ddc-patrol/run-patrol.sh`

```sh
#!/bin/sh
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONUNBUFFERED=1
umask 027

# 固定参数：单次运行、不因「有候选码」让 systemd 记 failed、用只读码表做集合差。
# 额外参数（如 --dry-run）会追加在后面，便于手工排障。
exec /usr/bin/python3 /opt/ddc-patrol/patrol.py \
  --once \
  --exit-zero \
  --codes-file /etc/ddc-patrol/codes.json \
  "$@"
```

**【服务器】**

```bash
sudo chown root:root /opt/ddc-patrol/run-patrol.sh
sudo chmod 0755 /opt/ddc-patrol/run-patrol.sh
```

> 注意 `--codes-file`：脚本默认按 `脚本目录/../data/codes.json` 找码表，服务器上没有这个路径。少了这个参数，`load_known()` 会打印 `codes file not found`，把官方描述里的所有候选都当成新码。

**【服务器】** 新建 `/etc/systemd/system/ddc-patrol.service`

```ini
[Unit]
Description=DragDriveCodes daily code patrol
Wants=network-online.target
After=network-online.target
OnFailure=ddc-patrol-alert@%n.service

[Service]
Type=oneshot
User=ddc
Group=ddc
WorkingDirectory=/var/lib/ddc-patrol
EnvironmentFile=/etc/ddc-patrol/patrol.env
ExecStart=/opt/ddc-patrol/run-patrol.sh
TimeoutStartSec=180
RuntimeMaxSec=300
UMask=0027
# 只允许写这两个目录，其余文件系统只读
ProtectSystem=strict
ReadWritePaths=/var/lib/ddc-patrol
PrivateTmp=true
NoNewPrivileges=true
```

**【服务器】** 新建 `/etc/systemd/system/ddc-patrol.timer`

```ini
[Unit]
Description=Run the code patrol once a day at 00:10 UTC

[Timer]
# 显式时区：与机器时区解耦。若机器改成 JST，这里改成 09:10:00 Asia/Tokyo
OnCalendar=*-*-* 00:10:00 UTC
Persistent=true
RandomizedDelaySec=120
AccuracySec=1min
Unit=ddc-patrol.service

[Install]
WantedBy=timers.target
```

**【服务器】** 新建 `/etc/systemd/system/ddc-patrol-alert@.service`（失败时的兜底告警）

```ini
[Unit]
Description=Alert for failed unit %i

[Service]
Type=oneshot
User=ddc
Group=ddc
EnvironmentFile=/etc/ddc-patrol/patrol.env
ExecStart=/usr/bin/python3 /opt/ddc-patrol/patrol.py --alert "%i failed"
```

### 3.4 等价的 cron 写法（仅备用）

**【服务器】** `sudo crontab -u ddc -e`

```cron
# 机器时区必须是 UTC（timedatectl 确认过）。00:10 UTC = 09:10 JST
# cron 不读 systemd 的 EnvironmentFile，必须自己 source；wrapper 负责 PATH 与 --codes-file
10 0 * * * set -a; . /etc/ddc-patrol/patrol.env; set +a; /opt/ddc-patrol/run-patrol.sh >> /var/lib/ddc-patrol/reports/cron.log 2>&1
```

cron 的坑：漏跑不补、日志要自己转、环境变量为空（所以 wrapper 里显式设了 `PATH`）、失败没有告警（需要额外加 `|| /opt/ddc-patrol/run-patrol.sh --alert "cron failed"`）。

---

## 4. 脚本要做什么

### 4.1 输入（只用公开接口，不需要任何账号）

| 源 | 请求 | 取什么 | 实现状态 |
|---|---|---|---|
| A2 · Roblox 公开 Games API | `GET https://games.roblox.com/v1/games?universeIds=7089588429` | `description`（官方码通常写在这里）、`updated`（**判断新旧必须看这个，不能只看 description**）、`name`、`playing`、`visits` | 已实现 |
| A1 · 官方游戏页（可选二路） | `GET https://www.roblox.com/games/131378148336503/` | 若 HTML 里能解析到描述就以它为准 | **未实现**：脚本不抓 HTML，正文由 JS 渲染、解析不稳定，当前只用 A2 |

官方没有公布这个接口的配额；**每天 1 次属于极低频率**，不需要 key。

### 4.2 处理流程

```
1. 抓 A2（最多 3 次，退避 2s/4s/8s，单次超时 25s），原始响应整段落盘：
   snapshots/2026-11-16T0010Z.json        ← 不加工，留证据
2. 取 data[0]；data 为空抛 ValueError → 退出码 30（换 universeId 或接口改结构都会走到这里）
3. 读 latest.json 作为上一版，比对 updated 与 description：
   - 首次运行（无 latest）→ 只建基线，疑似新码/失效都强制为 0，不告警
   - 有上一版但 description 完全相同（只有 updated 变了）→ 也报 0，避免每天重复刷同一条
4. 抽候选码：CODE_RE = [A-Z][A-Z0-9]{9,}(?:\.[0-9]+)*（允许 V1.2.0 这种带点版本号），
   再去掉 DENY 集合（DRAGDRIVESIMULATOR / BETAUPDATE 等），
   最后与 codes.json 的 active + unconfirmed + expired 做集合差
5. 疑似失效：description 变了以后，active 里的码这次没出现 → 标记，不自动改状态
6. 写 snapshots/yyyymmddThhmmZ.json + latest.json + reports/yyyy-mm-dd.md + state.json，
   并按 --keep（默认 90 天）清理旧快照
7. webhook 推一条摘要；成功运行时额外检查 state.json 的 last_success，超过 36h 追加静默提醒
```

> 为什么「description 没变就什么都不报」：官方经常只改缩略图或标题，`updated` 会动但描述不动。这种日子把同一批候选码再推一遍只会让人忽略告警。代价是**首次运行和描述未变的日子看不到 active 码是否还在描述里**，这是刻意取舍，不是漏算。

### 4.3 输出契约（人工照着做的那种清单）

`reports/2026-11-16.md` 的实际结构（由 `build_report()` 生成）：

````markdown
# Patrol 2026-11-16 00:10 UTC

- 体验：(TOWING x LIMITED UPDATE 🎃) Drag Drive Simulator
- updated：2026-11-15T21:11:25.64Z
- description sha256：71b3919eaa9e…
- 判定：有变化 / 仅时间戳变化 / 基线

## 变化摘要
- updated 变化：2026-11-14T… → 2026-11-15T…
- description 文本变化：有

## 基线候选（首次运行，仅供参考，未触发告警）
- `DRAGDRIVESIMULATORV1.2.0`

## 疑似新码（需人工确认，共 0 条）
（无）

## 疑似失效（需人工确认，共 0 条）
（无）

## 描述 diff
```diff
--- previous
+++ current
@@ …
```

## 原文快照
snapshots/2026-11-16T0010Z.json

> 本报告只做提示，不修改 codes.json，也不触发任何构建。确认后请手动改 `data/codes.json` → `python build.py` → 部署。
````

「基线候选」只在首次运行出现，不算告警；从第二次运行起只看「疑似新码 / 疑似失效」两节。

### 4.4 退出码（给 systemd 和监控用）

| 退出码 | 含义 |
|---|---|
| `0` | 拉取成功；无候选码，或本次没有可比的变化 |
| `10` | 拉取成功、有疑似新码或疑似失效 → 需要人看一眼 |
| `30` | 拉取/解析失败（网络、HTTP 非 200、`data[]` 为空、JSON 非法），3 次重试都失败 |

> 没有 40。配置/权限错误（目录不可写、env 文件缺失）是未捕获异常，Python 以 1 退出并打印 traceback。
>
> systemd 里 `10` 会被记成 `failed`（oneshot 非 0 即失败）。wrapper 统一加了 `--exit-zero`，让它只靠报告和 webhook 区分，unit 不需要 `SuccessExitStatus=`。

### 4.5 历史骨架（已删除）

旧版这里的 60 行「参考骨架」已移除：它与 `scripts/patrol.py` 的实际行为（正则、退出码、`--codes-file`、基线逻辑、静默告警）不一致，留着只会被误抄。部署时只用仓库里的 `04-site/scripts/patrol.py`。

---

## 5. 结果怎么送到你手上

| 方式 | 优点 | 缺点 | 建议 |
|---|---|---|---|
| **Webhook（Discord / 飞书机器人）** | 5 分钟接完，手机直接收推送，支持 markdown | URL 泄露=任何人可往你频道发消息；国内访问 Discord 需代理 | **主渠道** |
| 写文件（服务器上的 md） | 零依赖、全文可查、可当证据 | 要登录服务器才看得到，容易忘 | **必留**，作为权威记录 |
| 邮件（SMTP） | 谁都收得到 | 要配发信服务、授权码；容易进垃圾箱；阿里云海外节点 25 端口常被封，需用 465/587 | v1 不上，等 webhook 不够用时再加 |

### 5.1 Discord webhook（占位 URL，不要照抄）

**【服务器】** 把 URL 写进 env 文件（下一步），脚本里这样发：

```bash
curl -s -X POST "$DDC_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content":"Patrol 2026-11-15: 1 条疑似新码 `DRAGDRIVESIMULATORNOVEMBER26`"}'
```

### 5.2 飞书自定义机器人

```bash
curl -s -X POST "$DDC_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"Patrol 2026-11-15: 1 条疑似新码 DRAGDRIVESIMULATORNOVEMBER26"}}'
```

> 飞书机器人还可以加「签名校验」，那样 env 里要多一个 secret，并在脚本里算 HMAC。要加就一起加，别只存一半。

### 5.3 env 文件

**【服务器】**

```bash
sudo tee /etc/ddc-patrol/patrol.env >/dev/null <<'EOF'
DDC_WEBHOOK_URL=https://example.invalid/REPLACE_ME
EOF
sudo chown root:ddc /etc/ddc-patrol/patrol.env
sudo chmod 0640 /etc/ddc-patrol/patrol.env
```

> 上面是**占位值**，`example.invalid` 是保留域名，保证你忘了改也不会真发出去。
>
> **变量名是 `DDC_WEBHOOK_URL`**（D-D-C，DragDriveCodes 的首字母），不是 `DDD_`。脚本只读这一个名字，写成 `DDD_WEBHOOK_URL` 不会报错，只会打印 `notify: skipped (DDC_WEBHOOK_URL not set)`，等于静默漏掉所有告警。
>
> 旧版这里还有一个 `DDC_NOTIFY=1`，脚本从未读取，已删除。

---

## 6. 失败与连续失败的告警

三层，从下往上：

1. **单次网络失败**：脚本内部重试 3 次（2s/4s/8s）。仍失败 → 退出码 30。
2. **单次任务失败**：systemd `OnFailure=ddc-patrol-alert@%n.service` 立刻发一条「今天没跑成」。
3. **连续/静默失败**（最容易漏的）：因为 `Persistent=true` 只补跑一次，如果拉取连续 3 天都 403/超时，你只会看到 3 条告警，第 4 天开始可能就不看了。所以脚本每次**成功**时也要检查 `state.json` 里的 `last_success`：

   - 距今 > 36 小时 → 在成功消息里追加一行「⚠️ 上次成功是 X 天前」；
   - 注意这条提醒只有**成功运行时**才会发。如果任务本身每天都失败，靠的是第 2 层的 `OnFailure`，而不是这条。
   - `--heartbeat` **未实现**（脚本没有这个参数）。若确实需要「每周日无论有没有变化都发一句」，用现成的 `--alert` 加一个独立 timer 即可，不需要改脚本：`ExecStart=/opt/ddc-patrol/run-patrol.sh --alert "weekly heartbeat"`。

查看状态：

**【服务器】**

```bash
systemctl status ddc-patrol.timer
systemctl list-timers ddc-patrol.timer --all
journalctl -u ddc-patrol.service -n 50 --no-pager
journalctl -u ddc-patrol.service --since "7 days ago" | grep -c "fetch failed"
```

---

## 7. 首次上线怎么验证能跑通（按顺序，每步都有"应该看到什么"）

**【服务器】**，全部以 `ddc` 身份跑，避免用 root 跑出 root 属主的文件：

| # | 命令 | 应该看到 |
|---|---|---|
| 1 | `sudo -u ddc python3 -m py_compile /opt/ddc-patrol/patrol.py` | 无输出 = 语法通过 |
| 2 | `sudo -u ddc /opt/ddc-patrol/run-patrol.sh --dry-run` | 打印本次快照摘要，**不写** `state.json`；`snapshots/` 里不新增文件 |
| 3 | `sudo -u ddc /opt/ddc-patrol/run-patrol.sh` | 退出码 0（wrapper 带 `--exit-zero`）；`reports/<今天>.md` 生成；`snapshots/` 有新 json |
| 4 | `ls -l /var/lib/ddc-patrol/reports/` | 文件属主是 `ddc`，权限 640 |
| 5 | `sudo systemctl daemon-reload && sudo systemctl start ddc-patrol.service` | `systemctl status` 显示 `inactive (dead)` 且 `Result=success`（oneshot 正常结束就是 dead） |
| 6 | `journalctl -u ddc-patrol.service -n 20` | 有你脚本打印的摘要，没有 traceback；且不应出现 `codes file not found` |
| 7 | `sudo systemctl enable --now ddc-patrol.timer` | `Created symlink … timers.target.wants/` |
| 8 | `systemctl list-timers ddc-patrol.timer` | `NEXT` 列是**明天 00:10 UTC**（换算成你本地时间是次日 08:10 北京时间） |
| 9 | `systemctl show ddc-patrol.timer -p NextElapseUSecRealtime` | 一个具体时间戳，用 `date -u -d @<秒>` 核对是否 00:10 UTC |
| 10 | 故障演练：`sudo -u ddc /opt/ddc-patrol/run-patrol.sh --snapshot-file /nonexistent.json` | 退出码 30（`--exit-zero` 不影响失败路径）；webhook 收到一条失败消息；`state.json` 的 `last_success` **没变** |
| 11 | `sudo systemctl stop ddc-patrol.timer`（演练结束）→ 再 `start` | 恢复 |

第 8、9 步就是防"时区跑偏"的验收点：**如果 `NEXT` 显示的不是你想要的时刻，先回去改 §3.3 的 `OnCalendar`，不要改机器时区来回试。**

---

## 8. 和站点构建怎么衔接（服务器不做构建）

```
巡检（服务器）→ reports/*.md + webhook
        ↓ 人工确认（你）
改 04-site/data/codes.json（本地）
        ↓
本地 python build.py → 校验断言 → dist/
        ↓
部署（Cloudflare Pages）
```

**服务器上不装 git、不存站点源码、不跑 build.py**：

- 避免两处代码漂移（服务器上的 `codes.json` 和仓库里的不一致，是最难查的一类 bug）；
- 避免 Pillow / Python 版本在服务器上又装一遍；
- 服务器权限收紧后（`ProtectSystem=strict`），本来也写不了别处。

巡检脚本只需要一份 `codes.json` 的**只读副本**用于集合差：`/etc/ddc-patrol/codes.json`（`0640 root:ddc`），每次改完码表由你手动 `scp` 一份过去。想省这一步，就让脚本只输出候选码、由你在本地对照 `codes.json` 判断。

---

## 9. 需要你确认/提供的东西（我这边都没有）

1. **公网 IP**（或内网跳板路径）与 **SSH 端口**。
2. **SSH 登录用户**（root 还是 sudo 用户）与**认证方式**：密钥文件路径，或密码（密码不要直接发在聊天里，用临时口令或你自己登录后粘贴命令）。
3. **`timedatectl` 的实际输出**（决定 §3 用哪套时间表达式；本方案默认 UTC）。
4. **是否有 systemd**（极老的 Alibaba Cloud Linux 2 镜像才有例外）。输出 `systemctl --version` 即可确认。
5. **告警渠道**：飞书 / Discord / 只要服务器上的 md。选飞书的话需要一个自定义机器人的 webhook URL（以及是否启用签名校验）。
6. **是否允许服务器出网到 `games.roblox.com`**（安全组 / 代理限制需要放行）。
7. **`codes.json` 同步方式**：接受每次改完码表手动 `scp` 一份到 `/etc/ddc-patrol/codes.json`，还是希望脚本只输出候选、由你在本地对照。

以上任一项未确认，我都不会写「已部署」「已配置」。
