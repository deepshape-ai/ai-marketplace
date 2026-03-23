# ai-marketplace

Deepshape Agent 技能插件库。

## 安装方式

### Claude Code Marketplace

```bash
/plugin marketplace add https://github.com/deepshape-ai/ai-marketplace.git
/plugin install <skill-name>@deepshape-marketplace
```

### 手动安装

```bash
git clone https://github.com/deepshape-ai/ai-marketplace.git

# OpenCode
cp -r ai-marketplace/plugins/<skill-name>/skills/<skill-name> ~/.config/opencode/skills/

# Claude Code
cp -r ai-marketplace/plugins/<skill-name>/skills/<skill-name> ~/.claude/skills/
```

## 可用插件

| 插件 | 版本 | 描述 |
|------|------|------|
| fragments | 2.0.0 | Memos 全生命周期管理 + Daily Log |
| draw-io | 1.0.0 | 架构图绘制 |

## 前置要求

fragments 需要 Memos 实例（服务 URL + PAT Token），首次使用时自动引导配置。

draw-io 需要主机安装 drawio cli


