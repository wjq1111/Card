# Texas Holdem Online

Python 联机德州扑克项目，服务端和客户端都使用 Python。

- 服务端：`grpcio` 官方 gRPC Python 服务
- 客户端：`pygame` 桌面/移动适配客户端骨架
- 通信协议：`proto/poker.proto`

## 目录

- `proto/`: gRPC 协议定义
- `server/`: 房间、座位、牌局状态和 gRPC 服务端
- `client/`: pygame 客户端
- `shared/`: 扑克牌和公共领域模型
- `tools/`: 生成 protobuf Python 文件的工具

## 环境

建议使用 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\generate_grpc.py
```

## 启动

先启动服务端：

```powershell
python -m server.main
```

再启动客户端：

```powershell
python -m client.main
```

默认连接 `119.45.157.13:50051`。

## 当前范围

这个版本是正式 Python 技术路线的立项骨架，不是 Web demo。

- 支持 gRPC 双向流
- 支持创建/加入房间
- 支持玩家入座、准备、开局
- 服务端集中维护牌局状态
- pygame 绘制移动端优先牌桌界面

## 下一步

1. 完整下注轮状态机：小盲、大盲、跟注、加注、弃牌、全下、边池。
2. 服务端牌型评估和摊牌结算。
3. 客户端交互按钮、筹码动画、手牌/公共牌表现。
4. 断线重连、心跳、房间恢复。
5. Android/iOS 打包路线评估，pygame 可先走桌面和部分移动封装，若移动发行要求高，后续需要单独验证 Kivy/BeeWare 或原生壳方案。
