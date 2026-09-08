"""一键演示：从样例数据到看板可用的全链路。

流程：登录 → 上传数据集 → 等待导入 → 批量推理 → 弱标签训练 → 发布模型。
需先启动基础设施与四个本地服务（make init && make backend/nlp/frontend/worker），
或使用 scripts/dev_start.ps1。完成后打开前端即可查看看板数据。

用法：
  python scripts/demo.py [--file data/Appliances.sample30000.jsonl] [--skip-train]
环境变量：
  BACKEND_URL     默认 http://localhost:8000
  ADMIN_EMAIL     默认 admin@reviewlens.dev
  ADMIN_PASSWORD  未设置时交互式输入（getpass）
"""
import argparse
import getpass
import os
import sys
import time
from pathlib import Path

import httpx

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@reviewlens.dev")

# 轮询参数
POLL_INTERVAL = 3.0
IMPORT_TIMEOUT = 600.0
INFERENCE_TIMEOUT = 900.0
TRAINING_TIMEOUT = 900.0


def _die(msg: str) -> None:
    print(f"[demo] ✗ {msg}")
    sys.exit(1)


def _unwrap(resp: httpx.Response) -> dict:
    """校验响应约定 {"code": 0, "data": ...} 并返回 data。"""
    if resp.status_code >= 400:
        detail = resp.json().get("detail") if _is_json(resp) else resp.text
        _die(f"HTTP {resp.status_code}: {detail}")
    body = resp.json()
    if body.get("code") != 0:
        _die(f"业务错误: {body}")
    return body.get("data", {})


def _is_json(resp: httpx.Response) -> bool:
    return "application/json" in resp.headers.get("content-type", "")


def _poll(label: str, check, timeout: float) -> dict:
    """通用轮询：check() 返回 (done, payload)。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        done, payload = check()
        if done:
            return payload
        print(f"[demo]   等待{label}... ")
        time.sleep(POLL_INTERVAL)
    _die(f"{label}超时（{timeout:.0f}s）")


def login(client: httpx.Client) -> str:
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password = getpass.getpass(f"[demo] 请输入 {ADMIN_EMAIL} 的密码: ")
    resp = client.post("/api/auth/login", json={"email": ADMIN_EMAIL, "password": password})
    if resp.status_code == 401:
        _die("登录失败（401）。请确认管理员账号密码（make init 会打印随机密码）。")
    token = _unwrap(resp)["access_token"]
    print(f"[demo] ✓ 已登录 {ADMIN_EMAIL}")
    return token


def upload_dataset(client: httpx.Client, file_path: Path) -> str:
    print(f"[demo] 上传数据集 {file_path} ...")
    with file_path.open("rb") as fh:
        resp = client.post(
            "/api/v1/datasets/imports",
            files={"file": (file_path.name, fh)},
            timeout=300.0,
        )
    data = _unwrap(resp)
    version = data["dataset_version"]
    tag = "已存在，复用" if data.get("reused") else "已受理"
    print(f"[demo] ✓ 数据集{tag}: {version}")
    return version


def wait_import(client: httpx.Client, version: str) -> int:
    def check():
        ds = _unwrap(client.get(f"/api/v1/datasets/{version}"))
        status = ds.get("status")
        if status == "completed":
            return True, ds
        if status == "failed":
            _die(f"导入失败: {ds.get('error_message')}")
        return False, ds

    ds = _poll("导入", check, IMPORT_TIMEOUT)
    valid = ds.get("valid_rows", 0)
    print(f"[demo] ✓ 导入完成：有效 {valid} 行 / 拒绝 {ds.get('rejected_rows', 0)} 行")
    return valid


def wait_inference(client: httpx.Client, version: str, valid_rows: int) -> None:
    if valid_rows == 0:
        print("[demo] 数据集无有效评论，跳过推理")
        return
    resp = client.post("/api/v1/predictions/batch", json={"dataset_version": version})
    _unwrap(resp)
    print("[demo] ✓ 批量推理已入队")

    target = max(int(valid_rows * 0.999), 1)  # 容忍个别评论无情感结果

    def check():
        preds = _unwrap(
            client.get("/api/v1/predictions", params={"dataset_version": version, "page_size": 1})
        )
        total = preds.get("total", 0)
        return total >= target, total

    _poll("推理", check, INFERENCE_TIMEOUT)
    print(f"[demo] ✓ 推理完成：{valid_rows} 条评论已出情感结果")


def run_training_and_publish(client: httpx.Client, version: str) -> None:
    resp = client.post("/api/v1/analysis-runs", json={"dataset_version": version})
    run = _unwrap(resp)
    run_id = run["id"]
    print(f"[demo] ✓ 训练运行已创建: {run_id}")

    def check():
        rec = _unwrap(client.get(f"/api/v1/analysis-runs/{run_id}"))
        status = rec.get("status")
        if status == "succeeded":
            return True, rec
        if status == "failed":
            _die(f"训练失败: {rec.get('error_message')}")
        return False, rec

    rec = _poll("训练", check, TRAINING_TIMEOUT)
    print(
        f"[demo] ✓ 训练完成: {rec['model_version']} "
        f"macro_f1={rec.get('macro_f1')} test={rec.get('test_samples')} 样本"
    )

    resp = client.post(f"/api/v1/analysis-runs/{run_id}/publish")
    if resp.status_code == 400:
        detail = resp.json().get("detail", "")
        print(
            f"[demo] ⚠ 未通过发布门槛：{detail}\n"
            "[demo]   （弱标签基线的正常现象；训练记录与指标已入库，"
            "完成人工审核提升质量后可再训练发布）"
        )
        return
    _unwrap(resp)
    current = _unwrap(client.get("/api/v1/models/current"))
    print(f"[demo] ✓ 已发布生产模型: {current.get('model_version')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReviewLens 一键演示")
    root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--file",
        type=Path,
        default=root / "data" / "Appliances.sample30000.jsonl",
        help="评论 JSONL 文件（默认样例数据）",
    )
    parser.add_argument(
        "--skip-train", action="store_true", help="只做导入+推理，不训练发布"
    )
    args = parser.parse_args()

    if not args.file.exists():
        _die(f"数据文件不存在: {args.file}")

    with httpx.Client(base_url=BACKEND_URL, timeout=60.0) as client:
        client.headers["Authorization"] = f"Bearer {login(client)}"
        version = upload_dataset(client, args.file)
        valid_rows = wait_import(client, version)
        wait_inference(client, version, valid_rows)
        if args.skip_train:
            print("[demo] 已按要求跳过训练发布")
        else:
            run_training_and_publish(client, version)

    print(
        "\n[demo] ★ 演示数据就绪！打开前端查看看板：\n"
        "  开发环境  http://localhost:5173\n"
        "  生产部署  http://localhost/\n"
        "  「洞察看板」选择该数据集即可查看情感分布、属性差评率与趋势下钻。"
    )


if __name__ == "__main__":
    main()
