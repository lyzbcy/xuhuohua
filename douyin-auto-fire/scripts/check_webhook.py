#!/usr/bin/env python3
"""Webhook 配置测试脚本。

用于测试 Webhook URL、Headers 和 Template 配置是否正确。
"""
import argparse
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_settings
from app.models import TargetResult
from app.notifier import send_webhook_notification


async def test_webhook():
    """测试 Webhook 通知发送。"""
    try:
        settings = load_settings()
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return 1

    if not settings.webhook_url:
        print("❌ 未配置 WEBHOOK_URL，请先设置环境变量")
        print("\n示例：")
        print('  export WEBHOOK_URL="https://example.com/webhook"')
        print('  export WEBHOOK_TEMPLATE=\'{"text": "测试消息"}\'  # 可选')
        return 1

    print(f"📡 Webhook URL: {settings.webhook_url}")
    if settings.webhook_headers:
        print(f"📋 自定义 Headers: {len(settings.webhook_headers)} 个")
    if settings.webhook_template:
        print(f"📝 自定义模板: 已配置")
    print()

    # 创建测试数据
    test_results = [
        TargetResult(target="好友01", status="success", sent=2),
        TargetResult(target="好友02", status="success", sent=1),
    ]

    print("🚀 发送测试通知...")
    try:
        await send_webhook_notification(
            webhook_url=settings.webhook_url,
            task_id="webhook-test",
            dry_run=True,
            results=test_results,
            screenshots=[],
            headers=settings.webhook_headers,
            template=settings.webhook_template,
        )
        print("✅ Webhook 通知发送成功！")
        print("\n请检查你的 Webhook 接收端是否收到了测试消息。")
        return 0
    except Exception as e:
        print(f"❌ Webhook 通知发送失败: {e}")
        print("\n请检查：")
        print("  1. WEBHOOK_URL 是否正确")
        print("  2. 网络连接是否正常")
        print("  3. WEBHOOK_HEADERS 格式是否正确（如果配置了）")
        print("  4. WEBHOOK_TEMPLATE 格式是否正确（如果配置了）")
        return 1


def main():
    """主入口。"""
    parser = argparse.ArgumentParser(
        description="测试 Webhook 配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基础测试
  python scripts/check_webhook.py

  # 使用自定义 .env 文件
  python scripts/check_webhook.py --env-file .env.local

环境变量：
  WEBHOOK_URL          Webhook 接收端 URL（必需）
  WEBHOOK_HEADERS      自定义请求头（可选）
  WEBHOOK_TEMPLATE     自定义 JSON 模板（可选）

详细文档：
  docs/webhook.md
  docs/webhook-examples.env
        """,
    )
    parser.add_argument(
        "--env-file",
        help="自定义 .env 文件路径",
        default=None,
    )
    args = parser.parse_args()

    if args.env_file:
        import os
        from dotenv import load_dotenv

        load_dotenv(args.env_file)
        print(f"📂 已加载环境变量文件: {args.env_file}\n")

    return asyncio.run(test_webhook())


if __name__ == "__main__":
    sys.exit(main())
