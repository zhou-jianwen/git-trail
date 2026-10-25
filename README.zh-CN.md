# Git Trail

**把一个代码仓库的历史，装进一张离线网页。**

Git Trail 将本地 Git 提交历史生成可搜索、可交互的时间线。输出只有一个 HTML 文件，直接用浏览器打开即可，无需服务器、账号、前端构建流程或额外的 Python 运行依赖。

[English](README.md) · [MIT 许可证](LICENSE)

## 快速开始

需要 **Python 3.10+**，以及已加入 `PATH` 的 **Git 2.31+**。

```sh
git clone https://github.com/zhou-jianwen/git-trail.git
cd git-trail
python -m git_trail /path/to/your/repository -o trail.html --open
```

也可以从源码目录安装命令：

```sh
python -m pip install .
git-trail /path/to/your/repository -o trail.html
```

生成的文件包含样式、脚本和提交数据，可以直接打开，也可以离线查看。上述安装方式使用本地源码；项目尚未发布到 PyPI。

想先体验界面，可以打开源码中的 [examples/demo.html](examples/demo.html)，其中的提交历史为明确标注的虚构样例。修改模板后，可运行 `python examples/make_demo.py` 重新生成。

## 能做什么

- 按提交标题、作者名字和哈希搜索。
- 按作者和日期筛选，并一键重置。
- 浏览提交活跃度和分组时间线，查看本地分支、标签标记。
- 复制完整提交哈希，配合熟悉的 Git 工具使用。
- 在电脑或手机上阅读同一个文件。

页面记录的是指定工作树**当前 `HEAD` 可达的提交**。它不会拉取远端，不包含未提交改动，也不展示完整分支关系图。空仓库会生成空时间线。日期按 UTC 显示，贡献者按作者名字分组。

## 命令参数

```text
git-trail [repository] [-o OUTPUT] [--limit N] [--force] [--open] [--version]
```

| 参数 | 说明 |
| --- | --- |
| `repository` | 本地仓库路径，默认为当前目录。 |
| `-o OUTPUT` | 输出 HTML 路径，默认为 `git-trail.html`。 |
| `--limit N` | 最多导出 N 条提交；默认 500，范围为 1–10,000。 |
| `--force` | 覆盖已有的、未被 Git 跟踪的输出文件。 |
| `--open` | 生成后用默认浏览器打开。 |
| `--version` | 显示版本号。 |

如果历史超过导出上限，页面会标明。页面中的数量和活跃度统计只对应已导出的提交。

```sh
# 导出更多历史；不需要自动打开浏览器。
git-trail ../my-project --limit 2000 -o project-history.html

# 更新已经存在的报告。
git-trail ../my-project -o project-history.html --force
```

即使使用 `--force`，Git Trail 也会拒绝覆盖已被 Git 跟踪的文件、向 Git 元数据目录写入，或将符号链接用作输出文件。

## 文件里包含什么

导出文件包含提交标题、作者名字、时间戳、提交及父提交哈希、仓库名称，以及本地分支和标签名称。它**不导出**源文件、补丁、作者邮箱或远端地址。提交标题和名字仍可能含有私人信息，分享前请检查报告内容。

生成过程只读取本地 Git 历史。生成的页面不发送网络请求，不包含统计追踪、外部字体或 CDN 依赖。

## 开发

```sh
python -m unittest discover -s tests -v
python -m pip install .
git-trail --version
```

测试会创建临时 Git 仓库，验证真实的历史读取和命令行行为。GitHub Actions 配置覆盖 Linux、macOS、Windows，以及 Python 3.10 和 3.13，并检查安装后的包能否正常生成页面。

另有浏览器任务验证筛选、分页、复制哈希、恶意文本处理、手机布局和零外部请求。本地运行方式（仅开发测试需要 Node.js 18+）：

```sh
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
node tests/browser-smoke.cjs examples/demo.html
```

也可设置 `GIT_TRAIL_BROWSER`，指定已有的 Chromium、Chrome 或 Edge 可执行文件。测试截图保存在系统临时目录中。

Git Trail 专注于便于阅读的历史快照，不承担 Git 客户端、实时监控或源码浏览器的功能。

## 许可证

[MIT](LICENSE) © 2026 Git Trail contributors。
