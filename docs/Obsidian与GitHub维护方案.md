# Obsidian编辑、GitHub同步与公开发布

## 已建立的本地结构

本项目可作为现有Obsidian库内的一个子文件夹，无需新建嵌套库，也不需要安装插件或修改现有库配置。

```text
Obsidian中的知识库笔记（编辑主本）
        ↓ 导出并校验
skill知识JSON + 索引 + 年代阅读版 + 网页预览
        ↓ 本地查看改动、提交版本
独立GitHub项目仓库（Formangarden524/create-funny-meme-cards）
        ↓ 发布配置
GitHub Pages公开网站 / 发布包下载（尚未配置）
```

Obsidian把库及子目录中的笔记存为本地Markdown，并会反映外部文本修改。因此这一结构不依赖专用数据库或Obsidian专属插件。为兼顾GitHub，内部导航使用标准Markdown链接，属性采用平面YAML，避免嵌套属性的显示限制。

依据：[Obsidian数据存储](https://obsidian.md/help/data-storage)、[属性](https://obsidian.md/help/properties)、[内部链接](https://obsidian.md/help/links)。

## 单一编辑主本

- 编辑：知识库/条目、知识库/来源、知识库/待核线索。
- 生成：知识库首页及索引、knowledge.json、轻量索引、年代阅读版、来源清单、网页数据。
- 开发说明：README、skill规则、预览界面、数据契约由项目维护者另行修改。
- 个人运行数据：独立于公共资料，不能用“已经收藏”冒充“已经生成或使用”。

普通笔记编辑后执行tools/build_from_obsidian.py即可导出。此工具不联网、不推送、不生成图片、不写个人使用历史。当前依赖列在tools/requirements.txt。

## GitHub怎么接

只以本项目目录建立独立Git仓库；不要把包含其他资料的整个Obsidian库上传。项目已增加对.obsidian、个人本地配置、私人资料和运行输出的忽略规则。

建议先采用人工确认的同步节奏：编辑笔记 → 导出 → 校验 → 看差异 → 提交 → 推送。记录提交信息说明本次补了哪些资料、修改了什么判断。多人修改时先拉取并处理冲突，避免两台设备同时改同一篇笔记。

当前公开仓库为https://github.com/Formangarden524/create-funny-meme-cards，本项目目录为独立Git仓库。后续修改仍需导出、校验、提交、推送；不会因Obsidian保存而自动上传。未开启自动备份或定时同步。

## 怎样发布给别人

1. GitHub仓库用于查看资料、提Issue、下载skill和发布版本包。
2. GitHub Pages用于让读者直接浏览可搜索的年代知识网页。
3. 已补上秋哥署名、仓库链接、MIT许可与第三方素材范围。

现有预览页可以作为网站起点；正式发布时应生成网站入口index.html并核对站内链接。普通GitHub仓库中的HTML文件不会自动成为在线网站。

GitHub Pages支持从选定分支的根目录或/docs目录发布，也支持Actions构建。为避免将维护文档误当网站，建议后续使用Actions只发布生成的网站目录；当前未创建启用中的发布工作流。

依据：[GitHub Pages发布源说明](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)。推送后是否上线还取决于发布配置和部署结果，不能把推送成功等同于网站已更新。

## 后续持续完善

- 新材料先收进待核线索；核查后进入正式条目。
- 保留已知与未知、年度见证与首创断言的区别。
- 根据读者和使用反馈改释义、场景与漫画构思，修订用Git保留版本。
- skill使用历史与热梗定时采集是另外的功能，尚未因为部署到Obsidian而自动具备。
