# 中文插件库

社区中文版插件的独立公开来源，不是上游官方发行。商店只下载安装明确选择的完整 VSIX，保留官方命令和配置标识，诊断正文及用户内容不作翻译。

## 目录与安装包

源码树只包含审核的翻译、构建配方、来源锁、商品元数据和许可证；完整 VSIX 只放在对应固定 tag 的 Release，不放入 Git 历史。
只有固定 Release 发布并重新下载验包成功后才发布 catalog.json；本导出树没有预先承诺可下载的目录。

## 独立重建

使用 source-lock.json 指定的 CPython 和 zlib 版本：

```sh
python3 -I -B scripts/rebuild-public-products.py --validate-only
python3 -I -B scripts/product-release-check.py --output ../chinese-extensions-rebuild-UNIQUE
```

输出位置必须不存在。工具只读取本公开树，正常验证 HTTPS，从固定官方版本地址下载并校验完整字节，处理 HTTP gzip 编码；再在新临时目录使用显式 --source、独立输出目录和 fresh runpy globals 构建两次。两次构建在同一个隔离解释器内执行，不是两个子进程；每次都恢复 argv、环境、工作目录和模块搜索路径。任何输入、运行时或输出 SHA 不符立即停止。不读取原管理器工作区、私人凭据或本机历史证据。
重建仅复制 source-lock.json 锁定的文件；正式目录 catalog.json 必须匹配这些商品与发行字节，根 .git 仅作不读取的版本控制元数据，不作为构建输入。
product-release-report.json 只证明相应输入的字节可复现，不代表 Windows、真实登录或公网安装通过。各商品声明的限制见 products/ 与许可证清单。

翻译维护采用新旧文案比较，沿用未改译文并审核新增变化；安装仍使用完整包，不自动替换用户已安装版本。下载临时安装包在安装并验证后删除，目录可以缓存。
