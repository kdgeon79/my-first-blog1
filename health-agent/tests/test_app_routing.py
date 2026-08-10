from app import CORRECT_RE, GOAL_RE


def test_goal_regex():
    assert GOAL_RE.match("목표").group(1) is None
    assert GOAL_RE.match("목표 2000").group(1) == "2000"
    assert GOAL_RE.match("목표2000").group(1) == "2000"  # 공백 없이도 인식
    assert GOAL_RE.match("목표 1800kcal").group(1) == "1800"
    assert GOAL_RE.match("목표를 세우자") is None  # 일반 문장은 식사 기록으로


def test_correct_regex():
    assert CORRECT_RE.match("수정 김밥 한 줄").group(1) == "김밥 한 줄"
    assert CORRECT_RE.match("수정: 김밥").group(1) == "김밥"
    assert CORRECT_RE.match("수정") is None  # 빈 수정은 별도 안내 처리
