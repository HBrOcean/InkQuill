# 发布到 GitHub 指南

把 InkQuill 发布到 GitHub，让云端自动打出 **Windows / macOS / Linux** 三个可执行文件，
以后每次更新只要推一个新 tag，成品就自动出现——别人（和你自己）直接下载就能用，
**不用装 Python**。

---

## 0. 先搞清楚我们要做什么

```
① 把代码传到 GitHub          →  ② 打一个 tag（如 v1.2）        →  ③ 坐等云打包
                                 （这一步会触发自动构建）           （GitHub 的机器帮你打三平台）

④ 到 Releases 下载 inkquill-windows-x64.exe  →  双击就用 ✅
```

第 ③ 步用的是仓库里已经写好的 `.github/workflows/build.yml`，你**不用改任何配置**。

> 打 tag 会同时触发两件事：构建三个平台的成品 → 自动挂到 Release 页面供下载。

---

## 1. 准备工作

1. 注册 / 登录 **GitHub**：<https://github.com>（你的账号是 `HBrOcean`）
2. 选一种上传方式（下面三种任选其一）：
   - **方式 A：GitHub Desktop** —— 图形界面，最适合新手 ⭐推荐
   - **方式 B：命令行 Git** —— 灵活，打 tag 最直接
   - **方式 C：网页上传** —— 不用装任何软件，但要留意隐藏文件

---

## 方式 A：GitHub Desktop（推荐）

### A-1. 安装并登录

1. 下载 GitHub Desktop：<https://desktop.github.com>，安装后打开
2. 用你的 GitHub 账号登录（File → Options → Accounts → Sign in）

### A-2. 把本项目加进来

1. 菜单 **File → Add local repository…**
2. 选择你解压出来的 **InkQuill 文件夹**
   - 如果提示「This directory does not appear to be a Git repository」，
     点 **create a repository** 再点 Create 即可
3. 此时左侧会显示改动列表

### A-3. 发布

1. 右上角点 **Publish repository**
2. Name 填 `InkQuill`，**取消勾选** "Keep this code private"（想公开就取消，想私有就保留）
3. 点 **Publish repository** → 代码就上传成功啦 🎉

### A-4. 打 tag（换到网页做，更简单）

打开 `https://github.com/HBrOcean/InkQuill/releases` →

1. 点 **Draft a new release**
2. **Choose a tag** → 输入 `v1.2` → 点 **Create new tag: v1.2 on publish**
3. Title 也填 `v1.2`，点 **Publish release**

搞定，云端开始打包（见下文「第 2 步」）。

---

## 方式 B：命令行 Git（Windows）

### B-1. 安装 Git

下载 <https://git-scm.com/download/win>，一路默认安装即可。

### B-2. 打开终端

进入 InkQuill 文件夹，在地址栏输入 `cmd` 回车；或在文件夹空白处右键 → **Open Git Bash here**。

### B-3. 提交并推送

> 本项目已经帮你初始化好 git 仓库并完成了首次提交，所以**不用再 `git init`**。

```bash
# 1. 先在网页上创建一个空仓库（见下方 B-4），拿到地址后再执行：
git remote add origin https://github.com/HBrOcean/InkQuill.git

# 2. 推送（第一次会让你登录，见「常见问题」）
git branch -M main
git push -u origin main

# 3. 打 tag 触发云打包
git tag v1.2
git push origin v1.2
```

### B-4. 先创建空仓库

浏览器打开 <https://github.com/new> ：

- **Repository name** 填 `InkQuill`
- 选择 **Public**（公开）
- ⚠️ **不要**勾选 "Add a README file"（我们自带 README，勾了会冲突）
- 点 **Create repository**

---

## 方式 C：网页上传（不装软件）

1. 先在 <https://github.com/new> 创建一个空仓库（同 B-4，注意别勾 README）
2. 进入空仓库页面，点 **uploading an existing file**
3. 把 **InkQuill 文件夹里的所有内容**拖进去，点 **Commit changes**
4. 打 tag：进入 **Releases → Draft a new release** → 新 tag 填 `v1.2` → Publish

> ⚠️ **注意隐藏文件**：`.github`、`.gitignore` 这类以点开头的文件/文件夹，
> 网页拖拽有时会漏掉。而云打包**必须依赖 `.github/workflows/build.yml`**，
> 所以上传后请到仓库首页确认能看到 `.github` 文件夹；看不到就改用方式 A/B。

---

## 2. 坐等云端打包

推完 tag 后：

1. 打开 `https://github.com/HBrOcean/InkQuill/actions`
2. 会看到一条正在运行的 **Build** 任务（三个平台并行）
3. 大约 **3~6 分钟**跑完，全部变成绿色 ✅

如果红了（失败），点进去看日志，把报错发我即可。

---

## 3. 下载成品

打包完成后，回到 **Releases** 页面：

`https://github.com/HBrOcean/InkQuill/releases`

| 下载文件 | 平台 | 用法 |
|:--|:--|:--|
| **`inkquill-windows-x64.exe`** | Windows | **双击直接用**，无需装 Python |
| `inkquill-macos.zip` | macOS | 解压得 `inkquill.app`，拖进「应用程序」 |
| `inkquill-linux-x64` | Linux | `chmod +x inkquill-linux-x64` 后双击/终端运行 |

> 也可以在 Actions 那次运行的页面底部 **Artifacts** 里下载同样的文件。

---

## 额外：设置仓库封面（社交预览图）

仓库里已经准备好三张图（都在 `assets/`）：

| 文件 | 用途 |
|:--|:--|
| `cover.jpg` | 原始封面图 |
| `cover_named.jpg` | README 顶部的封面（已带项目名，**推上去自动显示，不用设置**） |
| `social_preview.png` | 社交预览图（分享仓库链接时显示的大图） |

想让分享链接时显示大图，去设置一次即可：

1. 打开 `github.com/HBrOcean/InkQuill/settings`
2. 找到 **Social preview** → 点 **Edit**
3. 上传 `assets/social_preview.png` → 保存

## 4. 以后如何更新

改完代码后：

```bash
git add -A
git commit -m "修复了 xxx"
git push

git tag v1.3          # 换一个新版本号
git push origin v1.3  # 再次触发自动打包
```

---

## 常见问题

**Q：`git push` 时要求输入密码，但输密码报错？**
A：GitHub 早就不支持账号密码了，要用 **Personal Access Token（PAT）**：
Settings → Developer settings → Personal access tokens → Tokens (classic) →
Generate new token，勾选 `repo` 权限，复制生成的 token，
在提示输入 **password** 时**粘贴这个 token**（不是你的登录密码）。

**Q：更省事的登录方式？**
A：用 **GitHub Desktop**（方式 A）或配置 **SSH 密钥**，都能免去每次输 token。

**Q：Actions 页面没反应 / 没有任务？**
A：确认 tag 真的推上去了（`git ls-remote --tags origin` 能看到 `v1.2`）。
另外仓库 Settings → Actions → General 里，确认 Actions 是 **Allow all actions** 状态。

**Q：仓库是 Private（私有）会不会不能用 Actions？**
A：能用。私有仓库每月有免费额度（2000 分钟），公开仓库**不限时长**。本工具一次打包约用 10~20 分钟。

**Q：exe 被 Windows 拦截 / 报毒？**
A：这是未签名程序的常见现象。点「更多信息 → 仍要运行」即可；
想彻底解决需要购买代码签名证书（对学生来说没必要）。

**Q：tag 名字有什么要求？**
A：仓库里的工作流监听的是 `v*`（v 开头），所以用 `v1.0`、`v1.2`、`v2.0.1` 这类都行。

---

## 附：本地打包（不走 GitHub）

只想自己电脑上用，也可以直接打包：

- Windows：双击 `打包EXE.bat` → 生成 `dist\inkquill.exe`
- macOS / Linux：终端执行 `./build.sh` → 生成 `dist/inkquill.app` / `dist/inkquill`
