# 图片工作台本地验收

本地 iPhone 17 Pro / iOS 26.1 模拟器，语言 zh-Hans。示例图片来自现有旅行素材，仅 DEBUG 预览使用；实际入口展示用户所选照片。原型图与运行截图的照片内容不同，不作为像素级 1:1 相似度证明。

## 已执行

- 后端相关 54 项测试通过，PCM 文档和 iOS 能力矩阵一致性检查通过。
- iOS `build-for-testing` 成功；6 项原生测试 + 1 项完整 UI 流程通过。
- 原生测试验证实际像素、裁剪坐标、透明度、编码尺寸、两款中文字体、修复变化、私有贴图、撤销重做与草稿编码。
- 本地真实 API：上传原图/结果 → `media.save_edit` → 验证归属与来源 → 私有作品文件 → 系统相册。
- UI 点击实际保存按钮，确认单图已存入相册，再批量处理五张，结果为“已完成 5 张”。
- Chat 桥接测试：完整 studio 配方走 `media.process` / `image_studio_v1` 设备动作和回执；`media.save_edit` 可经既有 Chat bridge 调用。

## 复现入口

在本任务 worktree 中运行：

```sh
python3 tests/fixtures/image_studio_server.py
```

该服务仅监听 127.0.0.1:8897，使用临时存储、固定测试身份与 fixture token，不连接生产数据库。

```sh
python3 -m pytest tests/test_generated_artifact_capabilities.py tests/test_image_studio.py tests/test_image_processing.py tests/test_ios_capability_matrix.py tests/test_capability_gateway.py tests/test_pcm_semantic_capabilities.py -q
python3 scripts/generate_product_capability_manual.py --check
python3 scripts/generate_ios_capability_matrix.py --check
xcodegen generate --spec ios/project.yml
```

在 Xcode 的测试 Scheme Environment Variables 或生成的 xctestrun 对两个测试 target 设置：

```text
IMAGE_STUDIO_LIVE=1
AI_LAB_E2E_BASE_URL=http://127.0.0.1:8897
AI_LAB_E2E_TOKEN=image-studio-local-fixture
AI_LAB_E2E_DISABLE_ANIMATIONS=1
```

App 宿主启动参数使用 `-imageWorkbenchPreview`。只运行 `ImageStudioTests` 与 `ImageStudioUITests`，并在专用模拟器授予 `photos-add` 权限。未设置 `IMAGE_STUDIO_LIVE=1` 时跳过依赖本地服务的测试，像素/配方测试仍可独立执行。当前机器已准备好的 xctestrun 路径为 `/private/tmp/image-studio-v4-build/Build/Products/ImageStudioAcceptance.xctestrun`。

## 实际截图

- [01 编辑首页](screenshots/01-editor.png)
- [02 文字](screenshots/02-text.png)
- [03 图层](screenshots/03-layers.png)
- [04 调色与滤镜](screenshots/04-color.png)
- [05 修复](screenshots/05-repair.png)
- [06 保存](screenshots/06-save.png)
- [07 批量](screenshots/07-batch.png)

## 验收边界

没有提交、push、部署或生产验证。Vision 主体识别复用现有 iOS 能力；真实相机照片的识别效果、低内存真机性能和发布包体积未在本次模拟器流程中量测。照片按原始比例完整显示，系统控件按当前 iOS 渲染；不承诺设计图像素逐点一致。最大单图 12MB / 24MP、批量 20 张且输入合计 60MB；输出尺寸滑杆用于缩小。污点修复、抠图和图片贴图只作用于当前样张，批量可同步文字、滤镜调色、尺寸质量及构图。
