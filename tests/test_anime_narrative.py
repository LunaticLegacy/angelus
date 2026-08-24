"""剧情编排迁移测试：outline / gate / foreshadowing / character / audience。"""

from __future__ import annotations

from angelus.anime.narrative import (
    Arc,
    AudienceInformation,
    CharacterState,
    CharacterStateStore,
    Foreshadowing,
    build_global_outline,
    build_series_brief,
    infer_scene_count,
    overdue_foreshadowing,
    parse_foreshadowing_csv,
    run_gate,
    serialize_foreshadowing_csv,
    valid_foreshadowing_ids,
)
from angelus.anime.states import GateVerdict


class TestOutline:
    def test_infer_scene_count(self) -> None:
        assert infer_scene_count(1000) == 2
        assert infer_scene_count(2000) == 3
        assert infer_scene_count(4000) == 4
        assert infer_scene_count(9000) == 5

    def test_build_global_outline(self) -> None:
        brief = build_series_brief("逆袭", "草根逆袭", genre="都市", target_audience="18-35")
        arc = Arc(id="arc1", project_id="p1", title="第一弧", order=1, summary="开局")
        outline = build_global_outline(brief, [arc])
        assert outline["arc_count"] == 1
        assert outline["arcs"][0]["title"] == "第一弧"


class TestGate:
    def test_placeholder_fails(self) -> None:
        result = run_gate(text="这里{{待补}}", episode_outline="大纲", scene_titles=["场景1"], storyboard_content="分镜内容足够长")
        assert result.verdict == GateVerdict.FAIL
        assert any(c.name == "placeholders" and c.verdict == GateVerdict.FAIL for c in result.checks)

    def test_clean_passes(self) -> None:
        result = run_gate(
            text="完整剧本内容",
            episode_outline="第一集大纲",
            scene_titles=["第一集大纲"],
            storyboard_content="镜头1：主角登场，镜头2：冲突爆发，镜头3：反转揭晓，镜头4：高潮收尾",
            used_foreshadowing_ids=["F001"],
            valid_foreshadowing_ids={"F001"},
            overdue_foreshadowing_ids=[],
            character_updates=["主角"],
        )
        assert result.verdict == GateVerdict.PASS

    def test_overdue_foreshadowing_warns(self) -> None:
        result = run_gate(
            text="内容",
            episode_outline="大纲",
            scene_titles=["大纲"],
            storyboard_content="分镜内容足够长",
            overdue_foreshadowing_ids=["F002"],
        )
        assert result.verdict == GateVerdict.WARN


class TestForeshadowing:
    CSV = (
        "id,主线,伏笔内容,首次埋设章节,计划回收章节,实际回收章节,状态,关联人物,备注\n"
        "F001,主线A,神秘玉佩,1,5,,埋设中,主角,\n"
        "F002,主线B,旧照片,2,3,,回收中,配角,\n"
    )

    def test_parse_and_serialize(self) -> None:
        items = parse_foreshadowing_csv(self.CSV)
        assert len(items) == 2
        assert items[0].id == "F001"
        assert items[0].status == "埋设中"
        text = serialize_foreshadowing_csv(items)
        assert "F001" in text and "神秘玉佩" in text

    def test_overdue(self) -> None:
        items = parse_foreshadowing_csv(self.CSV)
        # 当前第 6 章：F001 计划 5 回收逾期，F002 计划 3 回收逾期
        overdue = overdue_foreshadowing(items, "6")
        assert "F001" in overdue and "F002" in overdue

    def test_valid_ids(self) -> None:
        items = parse_foreshadowing_csv(self.CSV)
        assert valid_foreshadowing_ids(items) == {"F001", "F002"}


class TestCharacter:
    def test_store_upsert_and_apply(self) -> None:
        store = CharacterStateStore()
        state = CharacterState(id="c1", project_id="p1", name="主角", role="主角")
        store.upsert("p1", state)
        assert store.get("p1", "c1").name == "主角"
        updated = store.apply_updates("p1", [{"id": "c1", "location": "天台", "status": "alive"}])
        assert updated == ["主角"]
        assert store.get("p1", "c1").location == "天台"


class TestAudience:
    def test_audience_information(self) -> None:
        info = AudienceInformation(target_audience="18-35", age_rating="16+", platform="竖屏短剧")
        data = info.to_dict()
        assert data["platform"] == "竖屏短剧"
        assert data["age_rating"] == "16+"
