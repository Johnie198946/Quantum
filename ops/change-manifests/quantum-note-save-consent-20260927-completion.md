# 阅读回答未经点击自动创建笔记修复

task_id: quantum-note-save-consent-20260927
status: TESTED
branch: main
worktree: /Users/dengzhaoyu/Desktop/TepVis/Quantum-2.0
head/local_commit: 基线 b07e2cc4fd6c0bcd299990ec58d474761134e577；修复待提交
remote_sha: 开工fetch origin/main与HEAD一致；待推送后ls-remote核验
server_before: 本次客户端修复未读取服务器
server_after: 不适用，无服务端变更
health_check: 不适用，无服务端部署
functional_check: 保存授权源代码回归1项通过，修复前失败；阅读选词流式回答UI通过，通用问答键盘及连续3次追问UI通过
rollback_point: 基线源码及shared文件原稿已保存在/private/tmp/quantum-note-save-consent-20260927；不涉及服务器回滚
manifest: ops/change-manifests/quantum-note-save-consent-20260927-completion.md
remaining_risks: 已安装Build66仍包含问题，需新iOS构建；真机镜像锁定中，未完成真机写入复验

## 问题与证据

用户授权测试已安装Build66，指出未点击保存却出现大量笔记。通过computer-use技能/iPhone镜像只读进入阅读与记录，看到QA note A/B及带章节名称的摘录；没有删除、修改或创建用户笔记。随后镜像锁定，已请求用户自行解锁，没有尝试取得密码。

核对Build66对应b74a5288与当前主线，均存在两条明确自动写入链：
1. SettingsView.swift中的ReadingSelectionQuestionSheet.submit在回答completed后直接saveAnswer → saveQuestionAnswer → persistExcerpt → ReaderAnnotationEntry.save → KnowledgeNoteStore.createNote → syncKnowledgeNote。每次新回答会新建章节摘录，而非等用户点击“记到笔记”。
2. 继续学调用ReaderQuestionSheet时automaticallySaveAnswer=true，submit完成立即onSaveAnswer → saveLearningAnnotation；自动保存失败还阻止继续追问。仅打开并自动提交初始问题也能触发。

普通Chat的note_draft事件仅新增确认卡，不在接收时createNote；云端restore会恢复已有笔记。并未声称已逐条证明所有历史笔记来源，更未批量清理。

## 最小修复

复用两个组件原有保存按钮，移除回答完成时的写入及自动保存配置/重试状态；通用保存按钮在回答结束后显示，原账号校验保留。传输不完整保留明确提示。没有新服务、数据库、配置层或依赖；不改变已保存笔记。

修改文件：
- ios/AIPlatformApp/Views/Settings/SettingsView.swift
- ios/AIPlatformApp/Views/Chat/Components/ChatMessageStreamView.swift：仅删除automaticallySaveAnswer:true一行，其余并行清理改动保留
- tests/test_ios_note_save_consent.py
- 本manifest

## 隔离与验证

main基线b07e2cc4，唯一canonical worktree；origin=https://github.com/Johnie198946/Quantum.git，source=https://github.com/Johnie198946/ai-lab-platform.git。开工存在并行清理UI、AGENTS、多个manifest/receipts dirty，完整盘点在/private/tmp/quantum-note-save-consent-20260927/inventory.txt。已向清理任务协调真机使用及单行shared hunk，保留其余更改。沿用此前用户推送授权，仅提交本任务差异。

源代码回归检查覆盖两个stream consumer不调用笔记写入、显式按钮保留、继续学不再能启用自动保存。对开工原稿运行失败、修复后通过。pytest 1 passed，4个既有Pydantic警告。
阅读选词流式回答UI：testSelectionQuestionStreamsProgressAndAnswer通过。ReaderFixtureUITests的键盘收起与连续3次追问两项通过；共3条UI流程通过。git diff --check通过。
日志/xcresult：/private/tmp/quantum-note-save-consent-20260927/。

本修复必须进入下一版iOS包；后端部署不能改变已安装Build66的客户端自动保存逻辑。已有用户笔记不自动删除，历史疑似自动保存笔记须另行确认后处理。
