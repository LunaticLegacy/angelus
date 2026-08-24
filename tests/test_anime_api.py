"""anime API 集成测试：FastAPI TestClient + MockVideoProvider（默认 mock，无真实 API）。"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from angelus import storage, webapp


def _make_client() -> TestClient:
    return TestClient(webapp.app)


def _seed_project(client: TestClient) -> dict[str, str]:
    """创建 项目→剧集→场景→镜头 链，返回各 id。"""
    pid = client.post("/api/anime/projects", json={"name": "集成测试", "series_brief": "都市"}).json()["id"]
    eid = client.post(f"/api/anime/projects/{pid}/episodes", json={"title": "第一集", "order": 1}).json()["id"]
    sid = client.post(f"/api/anime/projects/{pid}/episodes/{eid}/scenes", json={"title": "开场", "order": 1}).json()["id"]
    shot_id = client.post(
        f"/api/anime/projects/{pid}/scenes/{sid}/shots",
        json={"prompt": "主角登场", "order": 1, "duration_seconds": 3.0},
    ).json()["id"]
    return {"project": pid, "episode": eid, "scene": sid, "shot": shot_id}


class TestProjectsApi:
    def test_crud_flow(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                # create
                r = client.post("/api/anime/projects", json={"name": "P1", "series_brief": "B"})
                assert r.status_code == 200
                pid = r.json()["id"]
                assert r.json()["name"] == "P1"
                # list
                r = client.get("/api/anime/projects")
                assert r.status_code == 200
                assert any(p["id"] == pid for p in r.json()["projects"])
                # get
                r = client.get(f"/api/anime/projects/{pid}")
                assert r.status_code == 200
                # update
                r = client.put(f"/api/anime/projects/{pid}", json={"name": "P1-改"})
                assert r.json()["name"] == "P1-改"
                # delete
                r = client.delete(f"/api/anime/projects/{pid}")
                assert r.status_code == 200
                r = client.get(f"/api/anime/projects/{pid}")
                assert r.status_code == 404
            finally:
                storage.WORKSPACE_ROOT = orig

    def test_create_requires_name(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                r = client.post("/api/anime/projects", json={})
                assert r.status_code == 422
            finally:
                storage.WORKSPACE_ROOT = orig


class TestHierarchyApi:
    def test_episode_scene_shot_chain(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                ids = _seed_project(client)
                # 层级列表
                eps = client.get(f"/api/anime/projects/{ids['project']}/episodes").json()["episodes"]
                assert len(eps) == 1
                scenes = client.get(f"/api/anime/projects/{ids['project']}/episodes/{ids['episode']}/scenes").json()["scenes"]
                assert len(scenes) == 1
                shots = client.get(f"/api/anime/projects/{ids['project']}/scenes/{ids['scene']}/shots").json()["shots"]
                assert len(shots) == 1
                # 级联删除场景
                r = client.delete(f"/api/anime/projects/{ids['project']}/scenes/{ids['scene']}")
                assert r.status_code == 200
                shots = client.get(f"/api/anime/projects/{ids['project']}/scenes/{ids['scene']}/shots")
                assert shots.status_code == 404
            finally:
                storage.WORKSPACE_ROOT = orig


class TestGenerationFlow:
    def test_generate_job_succeeds_and_records_asset(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                ids = _seed_project(client)
                # READY
                r = client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/transition",
                    json={"status": "READY"},
                )
                assert r.json()["status"] == "READY"
                # generate
                r = client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/generate",
                    json={"provider": "mock"},
                )
                assert r.status_code == 200
                job = r.json()["job"]
                assert job["status"] in ("PENDING", "QUEUED")
                # 等待终态
                for _ in range(100):
                    jr = client.get(f"/api/anime/projects/{ids['project']}/jobs/{job['id']}").json()
                    if jr["status"] in ("SUCCEEDED", "FAILED"):
                        break
                    time.sleep(0.05)
                assert jr["status"] == "SUCCEEDED"
                assert jr["result_asset_id"] is not None
                # 镜头应 GENERATED 并回写 asset
                shot = client.get(f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}").json()
                assert shot["status"] == "GENERATED"
                assert shot["asset_id"] == jr["result_asset_id"]
                # 资产包
                assets = client.get(f"/api/anime/projects/{ids['project']}/export/assets").json()
                assert assets["asset_count"] == 1
            finally:
                storage.WORKSPACE_ROOT = orig

    def test_illegal_transition_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                ids = _seed_project(client)
                r = client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/transition",
                    json={"status": "APPROVED"},
                )
                assert r.status_code == 409
            finally:
                storage.WORKSPACE_ROOT = orig


class TestQaAndExport:
    def test_qa_pass_and_final_cut(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                ids = _seed_project(client)
                client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/transition",
                    json={"status": "READY"},
                )
                job = client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/generate",
                    json={"provider": "mock"},
                ).json()["job"]
                for _ in range(100):
                    jr = client.get(f"/api/anime/projects/{ids['project']}/jobs/{job['id']}").json()
                    if jr["status"] in ("SUCCEEDED", "FAILED"):
                        break
                    time.sleep(0.05)
                # 结构 QA（无 gate）应 PASS
                r = client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/qa",
                    json={"run_gate": False},
                )
                assert r.status_code == 200
                assert r.json()["verdict"] == "PASS"
                # 镜头应 QA_PASSED
                shot = client.get(f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}").json()
                assert shot["status"] == "QA_PASSED"
                # APPROVE
                client.post(
                    f"/api/anime/projects/{ids['project']}/shots/{ids['shot']}/transition",
                    json={"status": "APPROVED"},
                )
                # final-cut 应包含 1 个镜头
                fc = client.get(f"/api/anime/projects/{ids['project']}/export/final-cut").json()
                assert fc["shot_count"] == 1
                assert fc["total_duration_seconds"] == 3.0
                # 剧本导出
                script = client.get(f"/api/anime/projects/{ids['project']}/export/script").json()
                assert "主角登场" in script["markdown"]
                # 字幕导出
                sub = client.get(
                    f"/api/anime/projects/{ids['project']}/export/subtitles",
                    params={"episode_id": ids["episode"], "fmt": "srt"},
                ).json()
                assert sub["content"].startswith("1\n")
            finally:
                storage.WORKSPACE_ROOT = orig


class TestProvidersApi:
    def test_list_providers_mock_only(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                client = _make_client()
                r = client.get("/api/anime/providers")
                assert r.status_code == 200
                names = [p["name"] for p in r.json()["providers"]]
                assert "mock" in names
                # 默认不暴露真实 provider（无 opt-in 环境变量）
                assert all("key" not in str(p).lower() for p in r.json()["providers"])
            finally:
                storage.WORKSPACE_ROOT = orig


class TestStorageIsolation:
    """anime 领域存储必须跟随 WORKSPACE_ROOT 隔离，且不与会话目录撞名。"""

    def test_anime_root_follows_workspace_root(self) -> None:
        import angelus.anime.storage as astore
        from angelus.anime.models import DramaProject

        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                root = astore.anime_root()
                assert str(Path(d)) in str(root), "anime_root must follow WORKSPACE_ROOT"
                assert root.name == "anime-studio", "must not collide with 'anime' session dir"
                p = DramaProject.create(name="隔离验证", series_brief="iso")
                astore.upsert_project(p.to_dict())
                assert (root / "projects.json").exists()
                assert (Path(d) / "anime-studio" / "projects.json").exists()
                # 旧名目录不应出现
                assert not (Path(d) / "anime" / "projects.json").exists()
                projs = astore.list_projects()
                assert len(projs) == 1 and projs[0]["name"] == "隔离验证"
            finally:
                storage.WORKSPACE_ROOT = orig

    def test_events_isolated_per_workspace(self) -> None:
        import angelus.anime.storage as astore

        with tempfile.TemporaryDirectory() as d:
            orig = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(d)
            try:
                ev = astore.append_event("proj_iso001", {"type": "anime.project.created"})
                assert ev["seq"] == 1
                assert astore.current_event_seq("proj_iso001") == 1
                events = list(astore.iter_events("proj_iso001", after=0))
                assert len(events) == 1
                # 事件落在隔离目录
                assert (Path(d) / "anime-studio" / "proj_iso001" / "events.ndjson").exists()
            finally:
                storage.WORKSPACE_ROOT = orig
