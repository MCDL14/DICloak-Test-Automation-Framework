# 测试数据目录

`test_data/` 用于存放本地自动化用例需要读取或生成的非代码文件。真实测试数据文件通常包含本机路径、导入导出结果或业务数据，已在 `.gitignore` 中忽略；仓库只保留目录结构和 `.gitkeep`。

## 目录说明

- `test_data/import/`：批量导入环境等用例使用的 xlsx 文件。
- `test_data/export/`：环境导出、成员导出等用例生成的文件输出目录。
- `test_data/bookmarks/`：书签覆盖、书签追加等用例使用的书签文件。
- `test_data/members/`：成员导出校验用的预期 xlsx 文件。
- `test_data/extensions/`：本地扩展包安装用例使用的 zip 文件。
- `test_data/Tools/`：抓包工具等外部工具的本地启动文件。

## 配置关系

运行环境配置写在：

```text
config/config.yaml
```

用例测试数据写在：

```text
config/test_data.yaml
```

仓库中的模板文件是：

```text
config/config.example.yaml
config/test_data.example.yaml
```

`config/config.yaml` 通过 `test_data_file` 指向测试数据配置文件。测试数据中的路径可以使用绝对路径，也可以使用相对项目根目录的路径，例如：

```yaml
test_data_file: config/test_data.yaml
```

```yaml
test_data:
  batch_import:
    file_dir: "test_data/import"
    file_name: "自动化-导入环境.xlsx"
  batch_export:
    export_dir: "test_data/export"
    export_file_name: "批量导出环境记录-DICloak.xlsx"
```

## 当前已使用的数据

环境管理 P0 用例当前会使用以下类型的数据：

1. 内核完整性校验预置环境名称和筛选关键字。
2. 自动化临时数据命名前缀；具体环境名、标签名和批量创建前缀由 `core/test_names.py` 按本次运行 ID 自动生成。
3. 批量导入环境 xlsx 文件。
4. 导出环境的输出目录和文件名。
5. 多分组环境用例的分组名称。
6. 创建带标签环境、批量创建带标签环境、批量编辑环境标签、编辑环境标签、筛选标签时需要选择或筛选的预置标签名称。
7. 编辑固定打开网址用例的预置环境名称和目标 URL。

后续代理管理、扩展管理、环境分组管理、成员管理、全局设置等模块新增用例时，只把跨机器路径、外部文件、预置业务数据和少量流程参数写入 `config/test_data.yaml`。用例自己创建、修改、删除的临时数据，应优先使用统一命名工具自动生成。

## 提交规则

不要提交以下内容：

1. 真实账号、密码、飞书 webhook。
2. 真实导入、导出、成员、书签、扩展包、抓包工具文件。
3. 自动化运行过程中生成的导出文件、日志、截图、报告。

可以提交以下内容：

1. 空目录占位文件 `.gitkeep`。
2. 不含敏感信息的模板文件。
3. 用例需要的公开示例说明文档。
